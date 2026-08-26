import getpass
import json
import os
import signal
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import process_state


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@unittest.skipUnless(
    os.name == "posix" and shutil.which("flock"),
    "Linux flock integration required",
)
class LauncherLifecycleTests(unittest.TestCase):
    def test_launcher_does_not_guess_or_kill_global_browser_pids(self):
        source = (REPOSITORY_ROOT / "src" / "launcher.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("flock -n 9", source)
        self.assertIn('process_alive "$BROWSER_PIDFILE" browser', source)
        self.assertIn('process_alive "$PIDFILE" server', source)
        self.assertIn("RECOVERY_MAX_ATTEMPTS", source)
        self.assertNotIn("pgrep", source)
        self.assertNotIn('kill "$(cat "$PIDFILE"', source)

    def test_singleton_recovers_server_once_and_stops_after_retry_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            home = root / "home"
            bin_dir = root / "bin"
            home.mkdir()
            bin_dir.mkdir()
            invocations = root / "browser-invocations.txt"
            fake_browser = bin_dir / "fake-browser"
            fake_browser.write_text(
                "#!/usr/bin/env bash\n"
                "set -eu\n"
                "echo \"$$\" >> \"$FAKE_BROWSER_INVOCATIONS\"\n"
                "if [[ -e /proc/$$/fd/9 ]]; then echo inherited >> \"$FAKE_BROWSER_INVOCATIONS\"; fi\n"
                "trap 'exit 0' HUP INT TERM\n"
                "while true; do sleep 1; done\n",
                encoding="utf-8",
            )
            fake_browser.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
            environment["HOME"] = str(home)
            environment["COZY_KIDS_PORT"] = str(free_port())
            environment["COZY_KIDS_RECOVERY_MAX_ATTEMPTS"] = "1"
            environment["COZY_KIDS_RECOVERY_BACKOFF_SECONDS"] = "0"
            environment["COZY_KIDS_RECOVERY_WINDOW_SECONDS"] = "60"
            environment["FAKE_BROWSER_INVOCATIONS"] = str(invocations)
            environment.pop("DISPLAY", None)
            environment.pop("WAYLAND_DISPLAY", None)

            subprocess.run(
                [
                    "bash",
                    str(REPOSITORY_ROOT / "scripts" / "install.sh"),
                    "--user",
                    getpass.getuser(),
                    "--home",
                    str(home),
                    "--lang",
                    "en",
                    "--browser",
                    "fake-browser",
                    "--launch-mode",
                    "window",
                    "--force",
                ],
                cwd=REPOSITORY_ROOT,
                env=environment,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            app_root = home / ".local" / "share" / "cozy-kids-launcher"
            (app_root / "timer_watchdog.py").unlink()
            launcher = home / ".local" / "bin" / "cozy-kids-launcher"
            installed_launcher = launcher.read_text(encoding="utf-8")
            self.assertIn("could not restart after several attempts", installed_launcher)
            self.assertNotIn("{{RUNTIME_FAILURE_", installed_launcher)
            cache = home / ".cache" / "cozy-kids-launcher"
            first = subprocess.Popen(
                [str(launcher)],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    if invocations.is_file() and process_state.owned_process_alive(
                        str(cache / "server.pid"),
                        "server",
                    ):
                        break
                    if first.poll() is not None:
                        self.fail("First launcher exited before opening its browser")
                    time.sleep(0.1)
                else:
                    self.fail("First launcher did not become ready")

                second = subprocess.run(
                    [str(launcher)],
                    env=environment,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                    check=False,
                )
                time.sleep(0.2)

                self.assertEqual(second.returncode, 0)
                server_record = process_state.read_process_record(cache / "server.pid")
                browser_record = process_state.read_process_record(cache / "browser.pid")
                self.assertEqual(
                    invocations.read_text(encoding="utf-8").splitlines(),
                    [str(browser_record["pid"])],
                )
                self.assertFalse(Path(f"/proc/{server_record['pid']}/fd/9").exists())
                self.assertFalse(Path(f"/proc/{browser_record['pid']}/fd/9").exists())

                os.kill(server_record["pid"], signal.SIGKILL)
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    recovered_server = process_state.owned_process(
                        str(cache / "server.pid"),
                        "server",
                    )
                    recovered_browser = process_state.owned_process(
                        str(cache / "browser.pid"),
                        "browser",
                    )
                    invocation_lines = (
                        invocations.read_text(encoding="utf-8").splitlines()
                        if invocations.is_file()
                        else []
                    )
                    if (
                        recovered_server
                        and recovered_server["startTime"] != server_record["startTime"]
                        and recovered_browser
                        and len(invocation_lines) == 2
                    ):
                        break
                    if first.poll() is not None:
                        self.fail("Launcher exited instead of recovering its server")
                    time.sleep(0.1)
                else:
                    self.fail("Launcher did not recover its server and browser")

                self.assertNotEqual(
                    process_state.process_start_time(browser_record["pid"]),
                    browser_record["startTime"],
                )
                self.assertEqual(
                    invocation_lines,
                    [str(browser_record["pid"]), str(recovered_browser["pid"])],
                )
                runtime_log = (
                    home
                    / ".local"
                    / "state"
                    / "cozy-kids-launcher"
                    / "runtime.jsonl"
                )
                deadline = time.monotonic() + 5
                while time.monotonic() < deadline:
                    events = [
                        json.loads(line)
                        for line in runtime_log.read_text(
                            encoding="utf-8"
                        ).splitlines()
                    ]
                    if any(
                        event.get("event") == "launcher.recovered"
                        and event.get("details", {}).get("attempt") == 1
                        for event in events
                    ):
                        break
                    time.sleep(0.1)
                else:
                    self.fail("Successful recovery was not recorded in diagnostics")

                os.kill(recovered_server["pid"], signal.SIGKILL)
                self.assertEqual(first.wait(timeout=10), 1)
            finally:
                if first.poll() is None:
                    first.terminate()
                first.wait(timeout=10)

            self.assertFalse(
                process_state.owned_process_alive(str(cache / "browser.pid"), "browser")
            )
            self.assertFalse(
                process_state.owned_process_alive(str(cache / "server.pid"), "server")
            )
            self.assertEqual(
                invocations.read_text(encoding="utf-8").splitlines(),
                [str(browser_record["pid"]), str(recovered_browser["pid"])],
            )


if __name__ == "__main__":
    unittest.main()
