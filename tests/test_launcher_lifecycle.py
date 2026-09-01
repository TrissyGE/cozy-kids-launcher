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
import urllib.request
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import process_state
import lifecycle_state


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


@unittest.skipUnless(
    os.name == "posix" and shutil.which("flock"),
    "Linux flock integration required",
)
class LauncherLifecycleTests(unittest.TestCase):
    def wait_for_lifecycle(self, path, state, reason=None, timeout=12):
        deadline = time.monotonic() + timeout
        last = None
        while time.monotonic() < deadline:
            try:
                last = lifecycle_state.read_lifecycle_state(path)
            except (OSError, ValueError, json.JSONDecodeError):
                time.sleep(0.05)
                continue
            if last["state"] == state and (
                reason is None or last["reason"] == reason
            ):
                return last
            time.sleep(0.05)
        self.fail(
            f"Lifecycle did not reach {state}/{reason}; last state was {last}"
        )

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

    def test_chromium_fullscreen_mode_has_a_scoped_f11_assist_and_safe_fallback(self):
        source = (REPOSITORY_ROOT / "src" / "launcher.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('CHROMIUM_FULLSCREEN_SWITCH="--start-fullscreen"', source)
        self.assertIn('CHROMIUM_FULLSCREEN_SWITCH="--kiosk"', source)
        self.assertIn('CHROMIUM_FLAGS+=(--ozone-platform=x11)', source)
        self.assertIn(
            '"$BROWSER_CMD" "${CHROMIUM_FLAGS[@]}" '
            '"$CHROMIUM_FULLSCREEN_SWITCH" "$URL"',
            source,
        )
        self.assertIn(
            'xdotool search --onlyvisible --pid "$BROWSER_CHILD_PID" \\\n'
            '          --name "Cozy Kids Launcher"',
            source,
        )
        self.assertIn('settling_window_id="$window_id"', source)
        self.assertIn("a transient full-size rectangle", source)
        self.assertIn('xdotool key --window "$window_id" F11', source)
        self.assertIn('confirm_chromium_fullscreen', source)
        self.assertNotIn(
            '--disable-session-crashed-bubble --fullscreen "$URL"',
            source,
        )

    def test_snap_firefox_uses_its_confined_common_profile(self):
        source = (REPOSITORY_ROOT / "src" / "launcher.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('command -v snap >/dev/null 2>&1', source)
        self.assertIn('snap list firefox >/dev/null 2>&1', source)
        self.assertIn(
            'FIREFOX_PROFILE="$HOME/snap/firefox/common/{{APP_ID}}-profile"',
            source,
        )
        self.assertIn(
            'FIREFOX_PROFILE="$HOME/.cache/{{APP_ID}}/firefox-profile"',
            source,
        )
        self.assertIn('if [[ "$BROWSER_BIN" == "firefox" ]]', source)
        self.assertNotIn('if [[ "$BROWSER_FAMILY" == "firefox" ]] \\\n+  && command -v snap', source)

    def test_firefox_profile_suppresses_remote_survey_messages(self):
        source = (REPOSITORY_ROOT / "src" / "launcher.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("configure_firefox_profile()", source)
        self.assertIn(
            "managed_preference = "
            "'user_pref(\"app.normandy.enabled\", false);'",
            source,
        )
        self.assertIn(
            'else\n    configure_firefox_profile\n  fi\n  case "$LAUNCH_MODE"',
            source,
        )
        self.assertIn("os.replace(temporary, path)", source)

    def test_chromium_launches_without_keyring_or_crash_restore_prompts(self):
        source = (REPOSITORY_ROOT / "src" / "launcher.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("CHROMIUM_FLAGS=(", source)
        self.assertEqual(source.count("--password-store=basic"), 1)
        self.assertEqual(source.count("--hide-crash-restore-bubble"), 1)
        self.assertEqual(source.count("--disable-translate"), 1)
        self.assertEqual(source.count("--disable-features=Translate"), 1)
        self.assertEqual(source.count('"${CHROMIUM_FLAGS[@]}"'), 3)
        self.assertIn("configure_chromium_profile()", source)
        self.assertIn('translate["enabled"] = False', source)
        self.assertIn("os.replace(temporary, path)", source)

    def test_explicit_chromium_display_modes_drop_cached_window_placement(self):
        source = (REPOSITORY_ROOT / "src" / "launcher.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn(
            'python3 - "$preferences" "$LAUNCH_MODE"',
            source,
        )
        self.assertIn(
            'if launch_mode in ("fullscreen", "kiosk"):',
            source,
        )
        self.assertIn('browser.pop("window_placement", None)', source)
        self.assertIn("ordinary window mode keeps user geometry", source)

    def test_desktop_autostart_waits_for_the_compositor_after_locking(self):
        source = (REPOSITORY_ROOT / "src" / "launcher.sh").read_text(
            encoding="utf-8"
        )
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        lock_index = source.index("flock -n 9")
        delay_index = source.index('if [[ "${1:-}" == "--autostart" ]]')
        self.assertLess(lock_index, delay_index)
        self.assertIn("sleep 12", source[delay_index:delay_index + 240])
        self.assertIn("Exec=$RUNTIME_BIN --autostart", installer)

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
            environment["COZY_KIDS_RECOVERY_BACKOFF_SECONDS"] = "1"
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
            firefox_profile = cache / "firefox-profile"
            firefox_profile.mkdir(parents=True)
            firefox_preferences = firefox_profile / "user.js"
            firefox_preferences.write_text(
                'user_pref("browser.shell.checkDefaultBrowser", false);\n'
                'user_pref("app.normandy.enabled", true);\n',
                encoding="utf-8",
            )
            lifecycle_file = cache / "lifecycle.json"
            first = subprocess.Popen(
                [str(launcher)],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            tile_supervisor = None
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

                self.assertEqual(
                    self.wait_for_lifecycle(
                        lifecycle_file,
                        "running",
                        "ready",
                    )["state"],
                    "running",
                )
                self.assertEqual(
                    firefox_preferences.read_text(encoding="utf-8").splitlines(),
                    [
                        'user_pref("browser.shell.checkDefaultBrowser", false);',
                        'user_pref("app.normandy.enabled", false);',
                    ],
                )

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
                recovering = self.wait_for_lifecycle(
                    lifecycle_file,
                    "recovering",
                    "server-failed",
                )
                self.assertEqual(recovering["attempt"], 1)
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

                recovered = self.wait_for_lifecycle(
                    lifecycle_file,
                    "running",
                    "recovered",
                )
                self.assertEqual(recovered["attempt"], 1)

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

                tile_record = cache / "tile-process.pid"
                supervisor_script = app_root / "process_supervisor.py"
                tile_supervisor = subprocess.Popen(
                    [
                        sys.executable,
                        str(supervisor_script),
                        "--record",
                        str(tile_record),
                        "--marker",
                        str(supervisor_script),
                        "--",
                        sys.executable,
                        "-c",
                        "import time; time.sleep(30)",
                    ],
                    env=environment,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                tile_owned = lambda: process_state.owned_process_alive(
                    str(tile_record),
                    "tile-process",
                    str(supervisor_script),
                )
                deadline = time.monotonic() + 5
                while not tile_owned() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(tile_owned())

                os.kill(recovered_server["pid"], signal.SIGKILL)
                self.assertEqual(first.wait(timeout=10), 1)
                failed = self.wait_for_lifecycle(
                    lifecycle_file,
                    "failed",
                    "recovery-exhausted",
                )
                self.assertNotIn("attempt", failed)
                self.assertEqual(tile_supervisor.wait(timeout=5), 0)
            finally:
                if first.poll() is None:
                    first.terminate()
                first.wait(timeout=10)
                if tile_supervisor is not None and tile_supervisor.poll() is None:
                    tile_supervisor.terminate()
                    tile_supervisor.wait(timeout=5)

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

    def test_start_update_shutdown_and_logout_states_clean_up_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            home = root / "home"
            bin_dir = root / "bin"
            home.mkdir()
            bin_dir.mkdir()
            browser_invocations = root / "browser-invocations.txt"
            poweroff_invocations = root / "poweroff-invocations.txt"
            fake_browser = bin_dir / "fake-browser"
            fake_browser.write_text(
                "#!/usr/bin/env bash\n"
                "set -eu\n"
                "echo \"$$\" >> \"$FAKE_BROWSER_INVOCATIONS\"\n"
                "trap 'exit 0' HUP INT TERM\n"
                "while true; do sleep 1; done\n",
                encoding="utf-8",
            )
            fake_browser.chmod(0o755)
            fake_systemctl = bin_dir / "systemctl"
            fake_systemctl.write_text(
                "#!/usr/bin/env bash\n"
                "set -eu\n"
                "echo \"$*\" >> \"$FAKE_POWEROFF_INVOCATIONS\"\n",
                encoding="utf-8",
            )
            fake_systemctl.chmod(0o755)
            environment = dict(os.environ)
            environment["PATH"] = f"{bin_dir}{os.pathsep}{environment['PATH']}"
            environment["HOME"] = str(home)
            environment["COZY_KIDS_PORT"] = str(free_port())
            environment["FAKE_BROWSER_INVOCATIONS"] = str(browser_invocations)
            environment["FAKE_POWEROFF_INVOCATIONS"] = str(poweroff_invocations)
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
            launcher_path = home / ".local" / "bin" / "cozy-kids-launcher"
            cache = home / ".cache" / "cozy-kids-launcher"
            lifecycle_file = cache / "lifecycle.json"
            launcher = subprocess.Popen(
                [str(launcher_path)],
                env=environment,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            restarted = None
            failed_update = None
            try:
                self.wait_for_lifecycle(lifecycle_file, "running", "ready")
                self.assertTrue(
                    process_state.owned_process_alive(
                        str(cache / "server.pid"),
                        "server",
                    )
                )
                self.assertTrue(
                    process_state.owned_process_alive(
                        str(cache / "browser.pid"),
                        "browser",
                    )
                )

                update_gate = root / "continue-update"
                update_invoked = root / "update-invoked"
                trigger = app_root / "update-trigger.sh"
                trigger.write_text(
                    "#!/usr/bin/env bash\n"
                    "set -eu\n"
                    f"touch {update_invoked}\n"
                    f"while [[ ! -f {update_gate} ]]; do sleep 0.05; done\n",
                    encoding="utf-8",
                )
                updating = self.wait_for_lifecycle(
                    lifecycle_file,
                    "updating",
                    "update-requested",
                )
                self.assertEqual(updating["reason"], "update-requested")
                deadline = time.monotonic() + 5
                while not update_invoked.is_file() and time.monotonic() < deadline:
                    time.sleep(0.05)
                self.assertTrue(update_invoked.is_file())
                update_gate.touch()
                self.wait_for_lifecycle(
                    lifecycle_file,
                    "running",
                    "update-complete",
                    timeout=15,
                )
                self.assertGreaterEqual(
                    len(browser_invocations.read_text(encoding="utf-8").splitlines()),
                    2,
                )

                request = urllib.request.Request(
                    f"http://127.0.0.1:{environment['COZY_KIDS_PORT']}/shutdown",
                    data=b"",
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    self.assertEqual(response.status, 200)
                    self.assertEqual(
                        json.loads(response.read().decode("utf-8"))["status"],
                        "ok",
                    )
                os.kill(launcher.pid, signal.SIGTERM)
                self.assertEqual(launcher.wait(timeout=10), 0)
                self.wait_for_lifecycle(lifecycle_file, "stopped", "shutdown")
                self.assertEqual(
                    poweroff_invocations.read_text(encoding="utf-8").splitlines(),
                    ["poweroff"],
                )

                restarted = subprocess.Popen(
                    [str(launcher_path)],
                    env=environment,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.wait_for_lifecycle(lifecycle_file, "running", "ready")
                os.kill(restarted.pid, signal.SIGTERM)
                self.assertEqual(restarted.wait(timeout=10), 0)
                self.wait_for_lifecycle(lifecycle_file, "stopped", "logout")

                failed_update = subprocess.Popen(
                    [str(launcher_path)],
                    env=environment,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                self.wait_for_lifecycle(lifecycle_file, "running", "ready")
                trigger.write_text(
                    "#!/usr/bin/env bash\nexit 7\n",
                    encoding="utf-8",
                )
                self.wait_for_lifecycle(
                    lifecycle_file,
                    "failed",
                    "update-failed",
                )
                self.assertEqual(failed_update.wait(timeout=10), 7)
                self.assertFalse(trigger.exists())
            finally:
                if launcher.poll() is None:
                    launcher.terminate()
                    launcher.wait(timeout=10)
                if restarted is not None and restarted.poll() is None:
                    restarted.terminate()
                    restarted.wait(timeout=10)
                if failed_update is not None and failed_update.poll() is None:
                    failed_update.terminate()
                    failed_update.wait(timeout=10)

            for record, role in (
                ("server.pid", "server"),
                ("browser.pid", "browser"),
                ("tile-process.pid", "tile-process"),
                ("overlay.pid", "overlay"),
                ("watchdog.pid", "watchdog"),
            ):
                self.assertFalse(
                    process_state.owned_process_alive(str(cache / record), role),
                    record,
                )


if __name__ == "__main__":
    unittest.main()
