from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from daily_budget import DailyBudget


class DailyBudgetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "budget.json"
        self.monotonic = 1.0
        self.local_time = datetime(2026, 11, 3, 16)
        self.budget = self.open_budget()

    def open_budget(self):
        return DailyBudget(self.path, clock=lambda: self.monotonic, wall=lambda: self.local_time)

    def test_combines_native_sessions_across_restarts_without_charging_idle_time(self):
        self.budget.begin("child", "paint", 1, alive=lambda: True)
        self.monotonic += 21
        self.budget.tick("child", 1)
        self.budget.finish()
        self.monotonic += 300
        self.budget = self.open_budget()
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 39)
        self.assertEqual(self.budget.status("other", 1)["remainingSeconds"], 60)
        self.budget.begin("child", "game", 1, alive=lambda: True)
        self.monotonic += 39
        self.assertTrue(self.budget.tick("child", 1))
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 0)

    def test_checkpoint_reservation_survives_unclean_exit_and_suspend_does_not_spend(self):
        self.budget.begin("child", "paint", 1, alive=lambda: True)
        self.local_time += timedelta(hours=2)
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 60)
        restarted = self.open_budget()
        self.assertEqual(restarted.status("child", 1)["remainingSeconds"], 58)

    def test_local_day_advances_but_backdating_does_not_refill_usage(self):
        self.budget.begin("child", "game", 1, alive=lambda: True)
        self.monotonic += 60
        self.budget.finish()
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 0)
        self.local_time -= timedelta(days=1)
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 0)
        self.local_time += timedelta(days=2)
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 60)
        self.budget.begin("child", "game", 1, alive=lambda: True)
        self.monotonic += 5
        self.budget.finish()
        self.local_time -= timedelta(days=1)
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 55)

    def test_embedded_heartbeat_and_finish_require_the_exact_session(self):
        token = self.budget.begin("child", "web", 1)
        self.assertFalse(self.budget.heartbeat(token, "other", finished=True))
        self.assertFalse(self.budget.heartbeat("ñ", "child"))
        self.assertFalse(self.budget.matches(token, "child", "other-tile"))
        self.monotonic += 4
        self.assertTrue(self.budget.heartbeat(token, "child", finished=True))
        self.assertFalse(self.budget.heartbeat(token, "child"))
        self.assertEqual(self.budget.status("child", 1)["remainingSeconds"], 56)
        self.budget.begin("child", "web", 1)
        self.monotonic += 16
        self.assertFalse(self.budget.tick("child", 1))
        self.assertIsNone(self.budget.session)

    def test_extensions_are_bounded_and_invalid_storage_does_not_refill(self):
        for count in range(1, 5):
            self.assertEqual(self.budget.extend("child", 1)["remainingSeconds"], 60 + count * 900)
        with self.assertRaisesRegex(ValueError, "limit"):
            self.budget.extend("child", 1)
        self.path.write_text("{broken", encoding="utf-8")
        self.assertEqual(self.budget.status("child", 1),
                         {"enabled": True, "remainingSeconds": 0, "unavailable": True})
