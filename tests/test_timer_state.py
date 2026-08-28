import json
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import timer_state


class TimerStorageTests(unittest.TestCase):
    def test_round_trip_keeps_the_existing_json_shape(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache" / "timer.json"
            expected = {"end_time": 1900, "totalMinutes": 15}

            timer_state.save_timer(path, expected)

            self.assertEqual(timer_state.load_timer(path), expected)
            self.assertEqual(
                json.loads(path.read_text(encoding="utf-8")),
                expected,
            )

    def test_missing_and_invalid_state_load_as_inactive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "timer.json"
            self.assertIsNone(timer_state.load_timer(path))

            path.write_text("not-json", encoding="utf-8")
            self.assertIsNone(timer_state.load_timer(path))

    def test_clear_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "timer.json"
            timer_state.save_timer(path, {"end_time": 1900})

            timer_state.clear_timer(path)
            timer_state.clear_timer(path)

            self.assertFalse(path.exists())


class TimerStatusTests(unittest.TestCase):
    def test_inactive_status_contract_is_stable(self):
        self.assertEqual(
            timer_state.timer_status(None, {}, now=1000),
            {
                "active": False,
                "expired": False,
                "warning": False,
                "remainingSeconds": 0,
                "totalMinutes": 0,
            },
        )

    def test_active_warning_and_expired_boundaries_are_preserved(self):
        config = {"timerWarningMinutes": 5}
        active = timer_state.timer_status(
            {"end_time": 1601, "totalMinutes": 15},
            config,
            now=1000,
        )
        warning = timer_state.timer_status(
            {"end_time": 1300, "totalMinutes": 15},
            config,
            now=1000,
        )
        expired = timer_state.timer_status(
            {"end_time": 1000, "totalMinutes": 15},
            config,
            now=1000,
        )

        self.assertFalse(active["warning"])
        self.assertEqual(active["remainingSeconds"], 601)
        self.assertTrue(warning["warning"])
        self.assertEqual(warning["remainingSeconds"], 300)
        self.assertEqual(
            expired,
            {
                "active": True,
                "expired": True,
                "warning": False,
                "remainingSeconds": 0,
                "totalMinutes": 15,
            },
        )
