import subprocess
import sys
import threading
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import speech_feedback


class FakeProcess:
    def __init__(self, running=False):
        self.running = running
        self.terminated = False
        self.killed = False
        self.waited = threading.Event()

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def kill(self):
        self.killed = True
        self.running = False

    def wait(self, timeout=None):
        self.waited.set()
        if self.running:
            raise subprocess.TimeoutExpired("speech", timeout)
        return 0


class SpeechFeedbackTests(unittest.TestCase):
    def test_engine_detection_is_allowlisted_and_ordered(self):
        calls = []

        def which(name):
            calls.append(name)
            return f"/usr/bin/{name}" if name == "espeak-ng" else None

        self.assertEqual(
            speech_feedback.find_speech_engine(which),
            ("espeak-ng", "/usr/bin/espeak-ng"),
        )
        self.assertEqual(calls, ["spd-say", "espeak-ng"])

    def test_commands_are_argv_only_and_languages_are_bounded(self):
        self.assertEqual(
            speech_feedback.speech_command(
                "spd-say",
                "/usr/bin/spd-say",
                "  Hallo\n Welt  ",
                "de",
            ),
            ["/usr/bin/spd-say", "-w", "-l", "de", "Hallo Welt"],
        )
        self.assertEqual(
            speech_feedback.speech_command(
                "espeak-ng",
                "/usr/bin/espeak-ng",
                "Paint; touch /tmp/nope",
                "unsupported",
            ),
            [
                "/usr/bin/espeak-ng",
                "-v",
                "en",
                "Paint; touch /tmp/nope",
            ],
        )

    def test_text_rejects_empty_control_only_and_oversized_values(self):
        for value in ("", "\x00\n", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                speech_feedback.normalize_speech_text(value)
        with self.assertRaisesRegex(ValueError, "too long"):
            speech_feedback.normalize_speech_text(
                "a" * (speech_feedback.MAX_SPEECH_TEXT_LENGTH + 1)
            )

    def test_missing_or_failed_engine_is_nonfatal(self):
        feedback = speech_feedback.SpeechFeedback(which=lambda _name: None)
        self.assertFalse(feedback.available())
        self.assertEqual(feedback.speak("Paint"), "unavailable")

        def fail_popen(*_args, **_kwargs):
            raise OSError("not executable")

        feedback = speech_feedback.SpeechFeedback(
            which=lambda name: f"/usr/bin/{name}" if name == "espeak" else None,
            popen=fail_popen,
        )
        self.assertEqual(feedback.speak("Paint"), "unavailable")

    def test_speak_rate_limits_and_replaces_only_its_owned_process(self):
        commands = []
        first = FakeProcess(running=True)
        second = FakeProcess(running=False)
        processes = iter((first, second))
        times = iter((10.0, 10.1, 11.0))

        def popen(command, **kwargs):
            commands.append((command, kwargs))
            return next(processes)

        feedback = speech_feedback.SpeechFeedback(
            which=lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None,
            popen=popen,
            monotonic=lambda: next(times),
        )
        self.assertEqual(feedback.speak("Paint", "en"), "spoken")
        self.assertEqual(feedback.speak("Music", "en"), "rate_limited")
        self.assertEqual(feedback.speak("Musik", "de"), "spoken")
        self.assertTrue(first.terminated)
        self.assertEqual(len(commands), 2)
        self.assertEqual(commands[0][0][-1], "Paint")
        self.assertTrue(commands[0][1]["start_new_session"])
        self.assertIs(commands[0][1]["stdin"], subprocess.DEVNULL)
        second.waited.wait(timeout=1)


if __name__ == "__main__":
    unittest.main()
