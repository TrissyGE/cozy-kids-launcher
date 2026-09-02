"""Bounded local Linux speech feedback without shell or network access."""

import shutil
import subprocess
import threading
import time
import unicodedata


SPEECH_ENGINES = ("spd-say", "espeak-ng", "espeak")
SUPPORTED_LANGUAGES = {"de", "en"}
MAX_SPEECH_TEXT_LENGTH = 200
MIN_SPEECH_INTERVAL_SECONDS = 0.2
MAX_SPEECH_DURATION_SECONDS = 20


def normalize_speech_text(value):
    """Return one short printable utterance or reject unsafe input."""
    if not isinstance(value, str):
        raise ValueError("Speech text must be a string")
    printable = "".join(
        character
        for character in value
        if not unicodedata.category(character).startswith("C")
    )
    normalized = " ".join(printable.split())
    if not normalized:
        raise ValueError("Speech text must not be empty")
    if len(normalized) > MAX_SPEECH_TEXT_LENGTH:
        raise ValueError("Speech text is too long")
    return normalized


def find_speech_engine(which=shutil.which):
    """Return an allowlisted engine name and resolved executable path."""
    for name in SPEECH_ENGINES:
        path = which(name)
        if path:
            return name, path
    return None


def speech_command(engine, executable, text, language):
    """Build an argv-only command for one known local speech engine."""
    normalized = normalize_speech_text(text)
    voice = language if language in SUPPORTED_LANGUAGES else "en"
    if engine == "spd-say":
        return [executable, "-w", "-l", voice, normalized]
    if engine in ("espeak-ng", "espeak"):
        return [executable, "-v", voice, normalized]
    raise ValueError("Unsupported speech engine")


class SpeechFeedback:
    """Own and replace at most one short-lived local speech process."""

    def __init__(self, which=shutil.which, popen=subprocess.Popen, monotonic=time.monotonic):
        self._which = which
        self._popen = popen
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._process = None
        self._last_started = float("-inf")

    def available(self):
        return find_speech_engine(self._which) is not None

    @staticmethod
    def _stop_process(process):
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=0.5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        except OSError:
            pass

    def _reap(self, process):
        try:
            process.wait(timeout=MAX_SPEECH_DURATION_SECONDS)
        except subprocess.TimeoutExpired:
            self._stop_process(process)
        except OSError:
            pass
        finally:
            with self._lock:
                if self._process is process:
                    self._process = None

    def speak(self, text, language="en"):
        normalized = normalize_speech_text(text)
        engine = find_speech_engine(self._which)
        if engine is None:
            return "unavailable"
        name, executable = engine
        command = speech_command(name, executable, normalized, language)
        with self._lock:
            now = self._monotonic()
            if now - self._last_started < MIN_SPEECH_INTERVAL_SECONDS:
                return "rate_limited"
            self._stop_process(self._process)
            try:
                process = self._popen(
                    command,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
            except OSError:
                self._process = None
                return "unavailable"
            self._process = process
            self._last_started = now
            threading.Thread(target=self._reap, args=(process,), daemon=True).start()
        return "spoken"

    def close(self):
        with self._lock:
            process = self._process
            self._process = None
        self._stop_process(process)
