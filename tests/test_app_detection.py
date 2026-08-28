import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import app_detection


class DesktopApplicationDetectionTests(unittest.TestCase):
    def test_desktop_entry_keeps_command_and_removes_field_codes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            executable = Path(temp_dir) / "paint-app"
            executable.touch()
            entry = Path(temp_dir) / "paint.desktop"
            entry.write_text(
                "[Desktop Entry]\n"
                "Name=Paint\n"
                "TryExec=paint-app\n"
                "Exec=paint-app --open %U --caption %c\n",
                encoding="utf-8",
            )

            detected = app_detection.parse_desktop_file(
                entry,
                environ={"PATH": temp_dir},
            )

        self.assertEqual(
            detected,
            {"name": "Paint", "exec": "paint-app --open  --caption"},
        )

    def test_hidden_and_unavailable_desktop_entries_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hidden = Path(temp_dir) / "hidden.desktop"
            hidden.write_text(
                "[Desktop Entry]\nName=Hidden\nNoDisplay=true\nExec=hidden-app\n",
                encoding="utf-8",
            )
            unavailable = Path(temp_dir) / "missing.desktop"
            unavailable.write_text(
                "[Desktop Entry]\nName=Missing\nTryExec=missing-app\n"
                "Exec=missing-app\n",
                encoding="utf-8",
            )

            self.assertIsNone(app_detection.parse_desktop_file(hidden))
            self.assertIsNone(
                app_detection.parse_desktop_file(
                    unavailable,
                    environ={"PATH": temp_dir},
                )
            )

    def test_scan_is_stable_and_deduplicates_launch_commands(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            applications = Path(temp_dir) / "applications"
            applications.mkdir()
            (applications / "zeta.desktop").write_text(
                "[Desktop Entry]\nName=Zeta\nExec=shared-app %U\n",
                encoding="utf-8",
            )
            (applications / "alpha.desktop").write_text(
                "[Desktop Entry]\nName=Alpha\nExec=alpha-app\n",
                encoding="utf-8",
            )
            (applications / "duplicate.desktop").write_text(
                "[Desktop Entry]\nName=Duplicate\nExec=shared-app %F\n",
                encoding="utf-8",
            )
            (applications / "ignored.txt").write_text(
                "Name=Ignored\nExec=ignored-app\n",
                encoding="utf-8",
            )

            detected = app_detection.scan_apps(
                temp_dir,
                application_dirs=[applications],
            )

        self.assertEqual(
            detected,
            [
                {"name": "Alpha", "exec": "alpha-app"},
                {"name": "Duplicate", "exec": "shared-app"},
            ],
        )


class BrowserDetectionTests(unittest.TestCase):
    def test_configured_browser_is_preferred_before_fallbacks(self):
        installed = {"preferred-browser", "firefox"}

        detected = app_detection.find_browser(
            {"browser": "preferred-browser"},
            candidates=("firefox", "preferred-browser"),
            which=lambda name: f"/usr/bin/{name}" if name in installed else None,
        )

        self.assertEqual(detected, "preferred-browser")

    def test_browser_status_payload_preserves_candidate_order(self):
        statuses = app_detection.browser_statuses(
            candidates=("firefox", "chromium"),
            which=lambda name: "/usr/bin/firefox" if name == "firefox" else None,
        )

        self.assertEqual(
            statuses,
            [
                {"name": "firefox", "installed": True},
                {"name": "chromium", "installed": False},
            ],
        )

    def test_browser_family_accepts_executable_paths(self):
        self.assertEqual(
            app_detection.browser_family("/usr/bin/google-chrome"),
            "chromium",
        )
        self.assertEqual(app_detection.browser_family("/usr/bin/firefox"), "firefox")
