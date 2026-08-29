import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "linux" / "desktop_smoke.py"
SPEC = importlib.util.spec_from_file_location("desktop_smoke", MODULE_PATH)
desktop_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(desktop_smoke)


def subprocess_result(returncode=0, stdout="", stderr=""):
    return desktop_smoke.subprocess.CompletedProcess(
        args=(),
        returncode=returncode,
        stdout=stdout,
        stderr=stderr,
    )


class DesktopDetectionTests(unittest.TestCase):
    def test_desktop_aliases_are_normalized(self):
        examples = {
            "GNOME": "gnome",
            "ubuntu:GNOME": "gnome",
            "KDE": "kde",
            "KDE:Plasma": "kde",
            "XFCE": "xfce",
            "XFCE4": "xfce",
            "sway": "unknown",
        }
        for value, expected in examples.items():
            with self.subTest(value=value):
                self.assertEqual(desktop_smoke.canonical_desktop(value), expected)

    def test_session_detection_prefers_the_declared_session(self):
        self.assertEqual(
            desktop_smoke.detected_session({
                "XDG_SESSION_TYPE": "wayland",
                "DISPLAY": ":0",
            }),
            "wayland",
        )
        self.assertEqual(
            desktop_smoke.detected_session({"DISPLAY": ":0"}),
            "x11",
        )
        self.assertEqual(desktop_smoke.detected_session({}), "unknown")

    def test_full_matching_desktop_environment_is_accepted(self):
        environment = {
            "XDG_CURRENT_DESKTOP": "ubuntu:GNOME",
            "XDG_SESSION_TYPE": "wayland",
            "WAYLAND_DISPLAY": "wayland-0",
            "DBUS_SESSION_BUS_ADDRESS": "unix:path=/run/user/1000/bus",
        }
        self.assertEqual(
            desktop_smoke.environment_errors(
                "gnome",
                "wayland",
                environment,
                wsl=False,
            ),
            [],
        )

    def test_wsl_and_mismatched_sessions_are_refused(self):
        environment = {
            "XDG_CURRENT_DESKTOP": "KDE",
            "XDG_SESSION_TYPE": "x11",
            "DISPLAY": ":0",
        }
        errors = desktop_smoke.environment_errors(
            "gnome",
            "wayland",
            environment,
            wsl=True,
        )
        self.assertTrue(any("WSL" in error for error in errors))
        self.assertTrue(any("expected gnome" in error for error in errors))
        self.assertTrue(any("expected wayland" in error for error in errors))
        self.assertTrue(any("DBUS_SESSION_BUS_ADDRESS" in error for error in errors))
        self.assertTrue(any("WAYLAND_DISPLAY" in error for error in errors))

    def test_wsl_detection_handles_environment_and_kernel_markers(self):
        self.assertTrue(
            desktop_smoke.is_wsl(
                proc_version="Linux version generic",
                environment={"WSL_DISTRO_NAME": "Ubuntu"},
            )
        )
        self.assertTrue(
            desktop_smoke.is_wsl(
                proc_version="Linux version 6.6.87.2-microsoft-standard-WSL2",
                environment={},
            )
        )
        self.assertFalse(
            desktop_smoke.is_wsl(
                proc_version="Linux version 6.8.0-generic",
                environment={},
            )
        )

    def test_distribution_identity_exposes_only_id_and_version(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            release = Path(temp_dir) / "os-release"
            release.write_text(
                'NAME="Example Linux"\nID=example\nVERSION_ID="42"\nSECRET=value\n',
                encoding="utf-8",
            )
            self.assertEqual(
                desktop_smoke.distribution_identity(release),
                {"id": "example", "version": "42"},
            )


class X11WindowDetectionTests(unittest.TestCase):
    def test_ewmh_window_is_detected_with_wmctrl(self):
        result = subprocess_result(stdout="0x01 host Cozy Kids Launcher\n")
        with patch.object(desktop_smoke.subprocess, "run", return_value=result) as run:
            self.assertTrue(desktop_smoke.x11_window_present("Cozy Kids Launcher"))
        run.assert_called_once_with(
            ["wmctrl", "-l"],
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_override_redirect_window_falls_back_to_xdotool(self):
        wmctrl = subprocess_result(stdout="0x01 host Cozy Kids Launcher\n")
        xdotool = subprocess_result(stdout="4194307\n")
        with patch.object(
            desktop_smoke.subprocess,
            "run",
            side_effect=(wmctrl, xdotool),
        ):
            self.assertTrue(desktop_smoke.x11_window_present("App Overlay"))

    def test_missing_window_is_reported(self):
        missing = subprocess_result(returncode=1)
        with patch.object(
            desktop_smoke.subprocess,
            "run",
            side_effect=(subprocess_result(), missing),
        ):
            self.assertFalse(desktop_smoke.x11_window_present("App Overlay"))

    def test_window_ids_ignore_invalid_xdotool_output(self):
        result = subprocess_result(stdout="4194307\nnot-a-window\n0x400004\n")
        with patch.object(
            desktop_smoke.subprocess,
            "run",
            return_value=result,
        ) as run:
            self.assertEqual(
                desktop_smoke.x11_window_ids("App Overlay"),
                [4194307, 0x400004],
            )
        run.assert_called_once_with(
            ["xdotool", "search", "--name", "App Overlay"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )

    def test_active_window_and_overlay_click_use_explicit_ids(self):
        active = subprocess_result(stdout="4194307\n")
        clicked = subprocess_result()
        with patch.object(
            desktop_smoke.subprocess,
            "run",
            side_effect=(active, clicked),
        ) as run:
            self.assertEqual(desktop_smoke.x11_active_window_id(), 4194307)
            desktop_smoke.x11_click_overlay_close(0x400004)

        self.assertEqual(
            run.call_args_list[1].args[0],
            [
                "xdotool",
                "mousemove",
                "--window",
                str(0x400004),
                "28",
                "32",
                "click",
                "1",
            ],
        )

    def test_active_window_match_refreshes_window_ids(self):
        with (
            patch.object(
                desktop_smoke,
                "x11_active_window_id",
                return_value=0x3A00004,
            ),
            patch.object(
                desktop_smoke,
                "x11_window_ids",
                return_value=[0x3A00004],
            ) as window_ids,
        ):
            self.assertTrue(
                desktop_smoke.x11_window_is_active("Cozy Kids Launcher")
            )

        window_ids.assert_called_once_with("Cozy Kids Launcher")

    def test_active_window_match_rejects_a_replaced_nonmatching_window(self):
        with (
            patch.object(
                desktop_smoke,
                "x11_active_window_id",
                return_value=0x3A00004,
            ),
            patch.object(
                desktop_smoke,
                "x11_window_ids",
                return_value=[0x3800004],
            ),
        ):
            self.assertFalse(
                desktop_smoke.x11_window_is_active("Cozy Kids Launcher")
            )


class BrowserModeTests(unittest.TestCase):
    def test_browser_command_waits_for_wrapper_exec(self):
        self.assertFalse(
            desktop_smoke.browser_command_ready(
                ["bash", "/usr/local/bin/google-chrome", "--kiosk"],
                "google-chrome",
            )
        )
        self.assertTrue(
            desktop_smoke.browser_command_ready(
                ["/opt/google/chrome/chrome", "--kiosk"],
                "google-chrome",
            )
        )
        self.assertTrue(
            desktop_smoke.browser_command_ready(
                ["/usr/lib/firefox/firefox-bin", "--fullscreen"],
                "firefox",
            )
        )

    def test_chromium_rewritten_process_title_keeps_mode_contract(self):
        command = [
            "/opt/google/chrome/chrome --user-data-dir=/tmp/profile "
            "--kiosk http://127.0.0.1:1234/index.html"
        ]
        self.assertTrue(
            desktop_smoke.browser_command_ready(command, "google-chrome")
        )
        self.assertEqual(
            desktop_smoke.verify_browser_mode(
                command,
                "google-chrome",
                "kiosk",
            ),
            "kiosk (--kiosk)",
        )

    def test_chromium_and_firefox_use_their_existing_mode_switches(self):
        examples = (
            ("google-chrome", "window", ["google-chrome"], "window"),
            (
                "google-chrome",
                "fullscreen",
                ["google-chrome", "--start-fullscreen"],
                "fullscreen (--start-fullscreen)",
            ),
            (
                "firefox",
                "fullscreen",
                ["firefox", "--fullscreen"],
                "fullscreen (--fullscreen)",
            ),
            (
                "firefox",
                "kiosk",
                ["firefox", "--kiosk"],
                "kiosk (--kiosk)",
            ),
        )
        for browser, mode, command, expected in examples:
            with self.subTest(browser=browser, mode=mode):
                details = desktop_smoke.verify_browser_mode(
                    command,
                    browser,
                    mode,
                )
                self.assertIn(expected, details)

    def test_missing_or_conflicting_mode_switches_fail(self):
        with self.assertRaisesRegex(RuntimeError, "missing browser switch"):
            desktop_smoke.verify_browser_mode(
                ["google-chrome"],
                "google-chrome",
                "kiosk",
            )
        with self.assertRaisesRegex(RuntimeError, "conflicting browser flags"):
            desktop_smoke.verify_browser_mode(
                ["google-chrome", "--kiosk", "--start-fullscreen"],
                "google-chrome",
                "kiosk",
            )


class DesktopReportTests(unittest.TestCase):
    def test_manual_display_check_covers_the_reported_launch_mode(self):
        self.assertEqual(
            desktop_smoke.MANUAL_CHECKS[1],
            "The selected browser mode fits the display without a black screen",
        )

    def test_report_keeps_manual_checks_pending_after_automation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = desktop_smoke.SmokeReport("xfce", "x11", temp_dir)
            report.pass_check("installer")
            report.manual_check("focus", "window manager observation")
            report.complete()

            data = json.loads(report.path.read_text(encoding="utf-8"))
            self.assertEqual(data["schemaVersion"], 1)
            self.assertEqual(data["launchMode"], "window")
            self.assertEqual(data["outcome"], "automation-passed-manual-pending")
            self.assertTrue(data["manualChecks"])
            self.assertTrue(
                all(check["status"] == "pending" for check in data["manualChecks"])
            )
            statuses = [check["status"] for check in data["automatedChecks"]]
            self.assertEqual(statuses, ["passed", "manual-required"])

    def test_interactive_manual_checks_control_the_final_outcome(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = desktop_smoke.SmokeReport("gnome", "wayland", temp_dir)
            answers = iter(["y"] * len(desktop_smoke.MANUAL_CHECKS))
            with redirect_stdout(io.StringIO()):
                report.collect_manual_checks(lambda _: next(answers))
            report.complete()
            self.assertEqual(report.data["outcome"], "passed")

        with tempfile.TemporaryDirectory() as temp_dir:
            report = desktop_smoke.SmokeReport("kde", "x11", temp_dir)
            answers = iter(
                ["n"] + ["s"] * (len(desktop_smoke.MANUAL_CHECKS) - 1)
            )
            with redirect_stdout(io.StringIO()):
                report.collect_manual_checks(lambda _: next(answers))
            report.complete()
            self.assertEqual(report.data["outcome"], "failed")

    @unittest.skipUnless(os.name == "posix", "Linux /proc process record required")
    def test_live_process_record_rejects_wrong_roles_and_start_times(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "record.json"
            record = {
                "pid": os.getpid(),
                "startTime": desktop_smoke.process_start_time(os.getpid()),
                "role": "browser",
            }
            record_path.write_text(json.dumps(record), encoding="utf-8")
            self.assertEqual(
                desktop_smoke.live_process_record(record_path, "browser")["pid"],
                os.getpid(),
            )
            self.assertIsNone(
                desktop_smoke.live_process_record(record_path, "server")
            )
            record["startTime"] += 1
            record_path.write_text(json.dumps(record), encoding="utf-8")
            self.assertIsNone(
                desktop_smoke.live_process_record(record_path, "browser")
            )


if __name__ == "__main__":
    unittest.main()
