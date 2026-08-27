import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import lifecycle_state


class LifecycleStateTests(unittest.TestCase):
    def test_start_update_and_stop_follow_the_explicit_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache" / "lifecycle.json"
            lifecycle_state.begin_lifecycle(path, "initial-start")
            lifecycle_state.transition_lifecycle(path, "running", "ready")
            lifecycle_state.transition_lifecycle(
                path,
                "updating",
                "update-requested",
            )
            lifecycle_state.transition_lifecycle(
                path,
                "starting",
                "update-complete",
            )
            lifecycle_state.transition_lifecycle(
                path,
                "running",
                "update-complete",
            )
            lifecycle_state.transition_lifecycle(path, "stopping", "logout")
            stopped = lifecycle_state.transition_lifecycle(
                path,
                "stopped",
                "logout",
            )

            self.assertEqual(stopped["state"], "stopped")
            self.assertEqual(stopped["reason"], "logout")
            self.assertNotIn("pid", stopped)
            self.assertNotIn("path", stopped)

    def test_invalid_transition_does_not_replace_previous_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "lifecycle.json"
            lifecycle_state.begin_lifecycle(path)
            lifecycle_state.transition_lifecycle(path, "running", "ready")

            with self.assertRaisesRegex(ValueError, "running -> stopped"):
                lifecycle_state.transition_lifecycle(
                    path,
                    "stopped",
                    "session-ended",
                )

            self.assertEqual(
                lifecycle_state.read_lifecycle_state(path)["state"],
                "running",
            )

    def test_new_run_replaces_state_left_by_an_unclean_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "lifecycle.json"
            lifecycle_state.begin_lifecycle(path)
            lifecycle_state.transition_lifecycle(path, "running", "ready")

            restarted = lifecycle_state.begin_lifecycle(path, "initial-start")

            self.assertEqual(restarted["state"], "starting")
            self.assertEqual(restarted["reason"], "initial-start")

    def test_untrusted_json_types_are_rejected_as_invalid_state(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "lifecycle.json"
            path.write_text(
                '{"schemaVersion":1,"state":[],"reason":"ready","updatedAt":"now"}',
                encoding="utf-8",
            )

            with self.assertRaisesRegex(ValueError, "state or reason"):
                lifecycle_state.read_lifecycle_state(path)

    def test_recovery_attempt_and_private_permissions_are_bounded(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache" / "lifecycle.json"
            lifecycle_state.begin_lifecycle(
                path,
                now=datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc),
            )
            recovering = lifecycle_state.transition_lifecycle(
                path,
                "recovering",
                "startup-failed",
                attempt=2,
                now=datetime(2026, 8, 27, 8, 0, tzinfo=timezone.utc),
            )

            self.assertEqual(recovering["attempt"], 2)
            self.assertEqual(recovering["updatedAt"], "2026-08-27T08:00:00Z")
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

            with self.assertRaisesRegex(ValueError, "recovery attempt"):
                lifecycle_state.transition_lifecycle(
                    path,
                    "starting",
                    "recovery",
                    attempt=11,
                )

    def test_shutdown_request_is_consumed_once_and_expires(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "lifecycle-request.json"
            lifecycle_state.write_lifecycle_request(path, "shutdown", now=100)

            self.assertEqual(
                lifecycle_state.consume_lifecycle_request(path, now=120),
                "shutdown",
            )
            self.assertIsNone(
                lifecycle_state.consume_lifecycle_request(path, now=120)
            )

            lifecycle_state.write_lifecycle_request(path, "parent-exit", now=100)
            self.assertIsNone(
                lifecycle_state.consume_lifecycle_request(path, now=200)
            )
            self.assertFalse(path.exists())


if __name__ == "__main__":
    unittest.main()
