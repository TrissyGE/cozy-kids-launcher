import getpass
import os
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
        self.assertNotIn("pgrep", source)
        self.assertNotIn('kill "$(cat "$PIDFILE"', source)

    def test_second_launcher_exits_without_starting_another_browser(self):
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
            environment["FAKE_BROWSER_INVOCATIONS"] = str(invocations)

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


if __name__ == "__main__":
    unittest.main()
