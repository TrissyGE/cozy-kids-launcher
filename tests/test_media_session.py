import sys
import unittest
from pathlib import Path
from unittest import mock


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import media_session


class FakeProcess:
    def __init__(self):
        self.returncode = 0
        self._polls = iter((None, 0, 0))

    def poll(self):
        return next(self._polls, 0)


class MediaSessionTests(unittest.TestCase):
    def tearDown(self):
        media_session._termination_signal = None

    def test_rc_parser_ignores_status_noise_and_uses_the_last_integer(self):
        payload = (
            b"status change: ( play state: 3 )\r\n"
            b"file:///home/kid/Videos/private.mp4\r\n"
            b"> 17\r\n"
        )
        self.assertEqual(media_session.parse_rc_integer(payload), 17)
        self.assertIsNone(media_session.parse_rc_integer(b"play state: 3\n"))

    def test_controlled_vlc_command_uses_private_rc_and_disables_global_history(self):
        command = media_session.controlled_vlc_command(
            ["vlc", "--fullscreen", "/home/kid/Videos/Film.mp4"],
            start_seconds=25,
        )
        self.assertEqual(command[0], "vlc")
        self.assertIn("--extraintf=oldrc", command)
        self.assertIn("--rc-fake-tty", command)
        self.assertIn("--no-one-instance", command)
        self.assertIn("--no-media-library", command)
        self.assertIn("--no-qt-recentplay", command)
        self.assertIn("--qt-continue=0", command)
        self.assertIn("--start-time=25", command)
        self.assertEqual(command[-1], "/home/kid/Videos/Film.mp4")
        with self.assertRaisesRegex(ValueError, "VLC"):
            media_session.controlled_vlc_command(["mpv", "Film.mp4"])

    def test_monitor_loads_samples_and_saves_one_path_free_position(self):
        process = FakeProcess()
        remote = mock.Mock()
        remote.query.side_effect = [21, 120]
        with mock.patch.object(
            media_session,
            "load_resume_position",
            return_value=15,
        ) as load, mock.patch.object(
            media_session.subprocess,
            "Popen",
            return_value=process,
        ) as popen, mock.patch.object(
            media_session,
            "VlcRemote",
            return_value=remote,
        ), mock.patch.object(
            media_session.time,
            "monotonic",
            side_effect=[0, 1, 1.1],
        ), mock.patch.object(
            media_session.time,
            "sleep",
        ), mock.patch.object(
            media_session,
            "save_resume_position",
        ) as save:
            result = media_session.monitor_vlc(
                ["vlc", "--fullscreen", "/videos/Film.mp4"],
                "/state/resume",
                "default",
                "1" * 24,
                "/videos/Film.mp4",
            )

        self.assertEqual(result, 0)
        load.assert_called_once_with(
            "/state/resume",
            "default",
            "1" * 24,
            "/videos/Film.mp4",
        )
        launched = popen.call_args.args[0]
        self.assertIn("--start-time=15", launched)
        self.assertIn("--extraintf=oldrc", launched)
        save.assert_called_once_with(
            "/state/resume",
            "default",
            "1" * 24,
            "/videos/Film.mp4",
            21,
            120,
        )


if __name__ == "__main__":
    unittest.main()
