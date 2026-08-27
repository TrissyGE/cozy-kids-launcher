import importlib.util
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPOSITORY_ROOT / "scripts" / "linux" / "desktop_smoke.py"
SPEC = importlib.util.spec_from_file_location("desktop_smoke", MODULE_PATH)
desktop_smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(desktop_smoke)


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


class DesktopReportTests(unittest.TestCase):
    def test_report_keeps_manual_checks_pending_after_automation(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            report = desktop_smoke.SmokeReport("xfce", "x11", temp_dir)
            report.pass_check("installer")
            report.manual_check("focus", "window manager observation")
            report.complete()

            data = json.loads(report.path.read_text(encoding="utf-8"))
            self.assertEqual(data["schemaVersion"], 1)
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
