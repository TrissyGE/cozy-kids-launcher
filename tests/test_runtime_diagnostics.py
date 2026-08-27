import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import runtime_diagnostics


class RuntimeDiagnosticsTests(unittest.TestCase):
    def test_structured_events_rotate_and_keep_private_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "state" / "runtime.jsonl"
            logger = runtime_diagnostics.RuntimeEventLogger(
                str(path),
                max_bytes=220,
                backup_count=2,
            )
            try:
                for _ in range(20):
                    logger.event(
                        "update.checked",
                        source="release",
                        updateAvailable=False,
                        version="0.5.0",
                    )
            finally:
                logger.close()

            self.assertTrue(path.is_file())
            self.assertTrue(Path(f"{path}.1").is_file())
            self.assertFalse(Path(f"{path}.3").exists())
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)
            for log_file in path.parent.glob("runtime.jsonl*"):
                if os.name == "posix":
                    self.assertEqual(stat.S_IMODE(log_file.stat().st_mode), 0o600)
                for line in log_file.read_text(encoding="utf-8").splitlines():
                    event = json.loads(line)
                    self.assertEqual(event["event"], "update.checked")
                    self.assertNotIn("message", event)

    def test_logger_rejects_fields_outside_the_privacy_contract(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = runtime_diagnostics.RuntimeEventLogger(
                str(Path(temp_dir) / "runtime.jsonl")
            )
            try:
                with self.assertRaisesRegex(ValueError, "privacy contract"):
                    logger.event("config.saved", title="Private family title")
                with self.assertRaisesRegex(ValueError, "Unknown runtime event"):
                    logger.event("private.family.event")
            finally:
                logger.close()

    def test_recovery_attempt_is_bounded_and_privacy_safe(self):
        event = runtime_diagnostics.sanitize_event(
            "launcher.recovered",
            details={"attempt": 2},
        )

        self.assertEqual(event["details"], {"attempt": 2})
        with self.assertRaisesRegex(ValueError, "Unsafe runtime event detail"):
            runtime_diagnostics.sanitize_event(
                "launcher.recovered",
                details={"attempt": "private"},
            )

    def test_config_restore_event_contains_only_the_schema_version(self):
        event = runtime_diagnostics.sanitize_event(
            "config.restored",
            details={"configVersion": 1},
        )

        self.assertEqual(event["details"], {"configVersion": 1})
        with self.assertRaisesRegex(ValueError, "privacy contract"):
            runtime_diagnostics.sanitize_event(
                "config.restored",
                details={"title": "Private family title"},
            )

    def test_lifecycle_diagnostics_accept_only_contract_values(self):
        diagnostics = runtime_diagnostics.build_diagnostics(
            "missing.log",
            app_version="0.5.0",
            config_readable=True,
            lifecycle={"state": "recovering", "reason": "server-failed", "attempt": 2},
        )
        self.assertEqual(
            diagnostics["lifecycle"],
            {"state": "recovering", "reason": "server-failed", "attempt": 2},
        )

        private_value = "Family-Surname"
        diagnostics = runtime_diagnostics.build_diagnostics(
            "missing.log",
            app_version="0.5.0",
            config_readable=True,
            lifecycle={"state": "running", "reason": private_value, "attempt": 99},
        )
        self.assertEqual(
            diagnostics["lifecycle"],
            {"state": "unknown", "reason": "unknown", "attempt": None},
        )
        self.assertNotIn(private_value, json.dumps(diagnostics))

    def test_runtime_logging_failure_cannot_break_the_launcher(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            logger = runtime_diagnostics.configure_runtime_logging(
                str(Path(temp_dir) / "runtime.jsonl")
            )
            try:
                self.assertFalse(
                    runtime_diagnostics.log_runtime_event(
                        "config.saved",
                        title="Private family title",
                    )
                )
                with mock.patch.object(
                    logger,
                    "event",
                    side_effect=OSError("disk full"),
                ):
                    self.assertFalse(
                        runtime_diagnostics.log_runtime_event("server.stopped")
                    )
            finally:
                runtime_diagnostics.close_runtime_logging()

    def test_diagnostics_drop_unknown_or_private_log_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runtime.jsonl"
            private_value = "Family Secret 1234"
            private_pin = "1234567890"
            entries = [
                {
                    "timestamp": "2026-08-26T10:00:00Z",
                    "level": "info",
                    "event": "config.saved",
                    "details": {"title": private_value},
                },
                {
                    "timestamp": "2026-08-26T10:00:01Z",
                    "level": "info",
                    "event": private_value,
                },
                {
                    "timestamp": private_pin,
                    "level": "error",
                    "event": "server.crashed",
                    "details": {"exceptionType": private_value},
                },
                {
                    "timestamp": "2026-08-26T10:00:03Z",
                    "level": "info",
                    "event": "server.started",
                    "details": {"version": "0.5.0"},
                },
            ]
            path.write_text(
                "".join(json.dumps(entry) + "\n" for entry in entries),
                encoding="utf-8",
            )

            diagnostics = runtime_diagnostics.build_diagnostics(
                str(path),
                app_version="0.5.0",
                config_readable=True,
                config_version=1,
            )

            serialized = json.dumps(diagnostics)
            self.assertNotIn(private_value, serialized)
            self.assertNotIn(private_pin, serialized)
            self.assertEqual(
                [event["event"] for event in diagnostics["events"]],
                ["server.crashed", "server.started"],
            )
            self.assertIn("OtherError", serialized)
            self.assertFalse(
                diagnostics["privacy"]["includesConfigurationValues"]
            )
            self.assertFalse(diagnostics["privacy"]["includesCredentials"])


if __name__ == "__main__":
    unittest.main()
