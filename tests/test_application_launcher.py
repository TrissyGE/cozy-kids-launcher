import os
import subprocess
import sys
import tempfile
import threading
import unittest
import warnings
from pathlib import Path
from unittest import mock


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import application_launcher
import process_state


class LaunchActionTests(unittest.TestCase):
    def test_legacy_actions_share_one_normalized_model(self):
        self.assertEqual(
            application_launcher.resolve_tile_action(
                {"cmd": ["special:filme-musik"]}
            ),
            {"type": "media"},
        )
        self.assertEqual(
            application_launcher.resolve_tile_action(
                {"cmd": ["special:browser:https://example.com/kids"]}
            ),
            {
                "type": "web",
                "mode": "embedded",
                "url": "https://example.com/kids",
            },
        )
        self.assertEqual(
            application_launcher.resolve_tile_action(
                {"cmd": ["xdg-open", "https://example.com/kids"]}
            ),
            {
                "type": "web",
                "mode": "external",
                "url": "https://example.com/kids",
            },
        )

    def test_app_string_is_split_without_a_shell(self):
        self.assertEqual(
            application_launcher.resolve_tile_action(
                {"cmd": ['paint-app --title "Kids mode"']}
            ),
            {
                "type": "app",
                "argv": ["paint-app", "--title", "Kids mode"],
            },
        )

    def test_non_http_urls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid browser URL"):
            application_launcher.resolve_tile_action(
                {"cmd": ["special:browser:file:///etc/passwd"]}
            )
        with self.assertRaisesRegex(ValueError, "Invalid browser URL"):
            application_launcher.resolve_tile_action(
                {"cmd": ["special:browser:https://parent:secret@example.com"]}
            )

    def test_external_browser_profiles_remain_isolated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            chromium = application_launcher.external_browser_command(
                "google-chrome",
                "https://example.com/kids",
                temp_dir,
            )
            firefox = application_launcher.external_browser_command(
                "firefox",
                "https://example.com/kids",
                temp_dir,
            )

            self.assertIn(
                f"--user-data-dir={Path(temp_dir) / 'external-chromium-profile'}",
                chromium,
            )
            self.assertIn("--app=https://example.com/kids", chromium)
            firefox_profile = Path(temp_dir) / "external-firefox-profile"
            self.assertTrue(firefox_profile.is_dir())
            self.assertEqual(
                firefox,
                [
                    "firefox",
                    "--no-remote",
                    "--profile",
                    str(firefox_profile),
                    "--kiosk",
                    "https://example.com/kids",
                ],
            )

    def test_legacy_kde_wrapper_is_removed(self):
        self.assertEqual(
            application_launcher.direct_app_command(
                ["kstart", "--fullscreen", "kturtle", "--demo"]
            ),
            ["kturtle", "--demo"],
        )


class FakeProcess:
    def __init__(self, poll_result=None):
        self.poll_result = poll_result
        self.terminated = False
        self.wait_timeouts = []

    def poll(self):
        return self.poll_result

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        self.wait_timeouts.append(timeout)
        return 0


class ApplicationLauncherTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        self.supervisor = root / "process_supervisor.py"
        self.overlay = root / "overlay.py"
        self.supervisor.touch()
        self.overlay.touch()
        self.tile_record = root / "tile-process.pid"
        self.overlay_record = root / "overlay.pid"
        self.activity_file = root / "activity.json"
        self.lock = threading.Lock()
        self.launcher = application_launcher.ApplicationLauncher(
            self.tile_record,
            self.overlay_record,
            self.supervisor,
            self.overlay,
            activity_file=self.activity_file,
            lock=self.lock,
            python_executable="/usr/bin/python3",
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_reset_stops_overlay_before_the_owned_tile(self):
        with mock.patch.object(
            application_launcher,
            "terminate_owned_process",
        ) as terminate:
            self.launcher.reset_active_tile()

        self.assertEqual(
            terminate.call_args_list,
            [
                mock.call(
                    str(self.overlay_record),
                    "overlay",
                    str(self.overlay),
                ),
                mock.call(
                    str(self.tile_record),
                    "tile-process",
                    str(self.supervisor),
                ),
            ],
        )

    def test_launch_supervises_argv_and_starts_the_overlay(self):
        supervisor_process = FakeProcess()
        overlay_process = FakeProcess()
        with mock.patch.object(
            application_launcher,
            "terminate_owned_process",
        ), mock.patch.object(
            application_launcher,
            "owned_process_alive",
            side_effect=[True, True],
        ), mock.patch.object(
            application_launcher.subprocess,
            "Popen",
            side_effect=[supervisor_process, overlay_process],
        ) as popen:
            result = self.launcher.launch_owned_tile(
                ["paint-app", "--kids"],
                "local",
                tile_id="paint",
            )

        self.assertIs(result, supervisor_process)
        self.assertEqual(popen.call_count, 2)
        self.assertEqual(
            popen.call_args_list[0].args[0],
            [
                "/usr/bin/python3",
                str(self.supervisor),
                "--record",
                str(self.tile_record),
                "--marker",
                str(self.supervisor),
                "--",
                "paint-app",
                "--kids",
            ],
        )
        self.assertEqual(
            popen.call_args_list[0].kwargs["start_new_session"],
            os.name == "posix",
        )
        self.assertEqual(
            popen.call_args_list[1].args[0],
            [
                "/usr/bin/python3",
                str(self.overlay),
                "--mode",
                "local",
                "--label",
                "Home",
                "--tile-id",
                "paint",
            ],
        )
        for call in popen.call_args_list:
            self.assertIs(call.kwargs["stdout"], subprocess.DEVNULL)
            self.assertIs(call.kwargs["stderr"], subprocess.DEVNULL)

    def test_failed_ownership_terminates_the_started_supervisor(self):
        process = FakeProcess(poll_result=1)
        with mock.patch.object(
            application_launcher,
            "terminate_owned_process",
        ), mock.patch.object(
            application_launcher,
            "owned_process_alive",
            return_value=False,
        ), mock.patch.object(
            application_launcher.subprocess,
            "Popen",
            return_value=process,
        ) as popen:
            with self.assertRaisesRegex(
                OSError,
                "ownership could not be established",
            ):
                self.launcher.launch_owned_tile(["paint-app"], "local")

        self.assertEqual(popen.call_count, 1)
        self.assertTrue(process.terminated)
        self.assertEqual(process.wait_timeouts, [1])

    def test_opt_in_activity_is_passed_to_the_owned_supervisor(self):
        supervisor_process = FakeProcess()
        overlay_process = FakeProcess()
        with mock.patch.object(
            application_launcher,
            "terminate_owned_process",
        ), mock.patch.object(
            application_launcher,
            "owned_process_alive",
            side_effect=[True, True],
        ), mock.patch.object(
            application_launcher.subprocess,
            "Popen",
            side_effect=[supervisor_process, overlay_process],
        ) as popen:
            self.launcher.launch_owned_tile(
                ["paint-app"],
                "local",
                tile_id="paint",
                profile_id="default",
                track_activity=True,
            )

        self.assertEqual(
            popen.call_args_list[0].args[0],
            [
                "/usr/bin/python3",
                str(self.supervisor),
                "--record",
                str(self.tile_record),
                "--marker",
                str(self.supervisor),
                "--activity-file",
                str(self.activity_file),
                "--activity-profile",
                "default",
                "--activity-tile",
                "paint",
                "--",
                "paint-app",
            ],
        )

    def test_missing_supervisor_never_starts_an_unowned_process(self):
        self.supervisor.unlink()
        with mock.patch.object(
            application_launcher.subprocess,
            "Popen",
        ) as popen:
            with self.assertRaisesRegex(OSError, "supervisor is unavailable"):
                self.launcher.launch_owned_tile(["paint-app"], "local")
        popen.assert_not_called()

    @unittest.skipUnless(os.name == "posix", "Linux process ownership required")
    def test_real_supervisor_and_overlay_are_stopped_by_owned_records(self):
        source_root = SOURCE_ROOT
        self.supervisor = source_root / "process_supervisor.py"
        self.overlay.write_text(
            "import os, sys, time\n"
            f"sys.path.insert(0, {str(source_root)!r})\n"
            "from process_state import write_process_record\n"
            f"write_process_record({str(self.overlay_record)!r}, os.getpid(), "
            "'overlay', marker=os.path.abspath(__file__))\n"
            "time.sleep(30)\n",
            encoding="utf-8",
        )
        self.launcher = application_launcher.ApplicationLauncher(
            self.tile_record,
            self.overlay_record,
            self.supervisor,
            self.overlay,
            lock=self.lock,
            python_executable=sys.executable,
        )

        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                process = self.launcher.launch_owned_tile(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    "local",
                )
            self.assertIsNone(process.poll())
            self.assertTrue(
                process_state.owned_process_alive(
                    str(self.tile_record),
                    "tile-process",
                    str(self.supervisor),
                )
            )
            self.assertTrue(
                process_state.owned_process_alive(
                    str(self.overlay_record),
                    "overlay",
                    str(self.overlay),
                )
            )

            self.launcher.reset_active_tile()

            process.wait(timeout=5)
            self.assertFalse(self.tile_record.exists())
            self.assertFalse(self.overlay_record.exists())
        finally:
            self.launcher.reset_active_tile()
