from datetime import datetime
import re
import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import schedule_rules


TILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")


def schedule(enabled=True, day="monday", start="08:00", end="18:00"):
    return {
        "enabled": enabled,
        "days": {day: [{"start": start, "end": end}]},
    }


class ScheduleValidationTests(unittest.TestCase):
    def test_schedule_is_normalized_in_weekday_order(self):
        value = {
            "enabled": True,
            "days": {
                "tuesday": [{"start": "12:00", "end": "13:00"}],
                "monday": [{"start": "08:00", "end": "09:00"}],
            },
        }

        normalized = schedule_rules.validate_schedule(value)

        self.assertEqual(list(normalized["days"]), ["monday", "tuesday"])

    def test_end_of_day_can_be_expressed_without_allowing_it_as_a_start(self):
        normalized = schedule_rules.validate_schedule(
            schedule(start="18:00", end="24:00")
        )
        self.assertEqual(normalized["days"]["monday"][0]["end"], "24:00")

        with self.assertRaisesRegex(ValueError, "HH:MM"):
            schedule_rules.validate_schedule(
                schedule(start="24:00", end="24:00")
            )

    def test_invalid_times_overlaps_and_unknown_fields_are_rejected(self):
        invalid = (
            {"enabled": True, "days": {"holiday": []}},
            schedule(start="18:00", end="08:00"),
            schedule(start="8:00", end="18:00"),
            {
                "enabled": True,
                "days": {"monday": [
                    {"start": "08:00", "end": "12:00"},
                    {"start": "11:00", "end": "13:00"},
                ]},
            },
            {"enabled": True, "days": {}, "timezone": "remote"},
        )
        for value in invalid:
            with self.subTest(value=value), self.assertRaises(ValueError):
                schedule_rules.validate_schedule(value)

    def test_per_app_rules_are_bounded_and_use_safe_tile_ids(self):
        normalized = schedule_rules.validate_app_availability(
            {"paint": schedule()},
            TILE_ID_PATTERN,
            2,
        )
        self.assertIn("paint", normalized)

        with self.assertRaisesRegex(ValueError, "invalid tile id"):
            schedule_rules.validate_app_availability(
                {"../paint": schedule()},
                TILE_ID_PATTERN,
                2,
            )
        with self.assertRaisesRegex(ValueError, "bounded"):
            schedule_rules.validate_app_availability(
                {"paint": schedule(), "games": schedule(), "web": schedule()},
                TILE_ID_PATTERN,
                2,
            )


class ScheduleEvaluationTests(unittest.TestCase):
    monday_morning = datetime(2026, 8, 31, 9, 30)
    monday_evening = datetime(2026, 8, 31, 19, 0)

    def test_missing_and_disabled_schedules_remain_unrestricted(self):
        self.assertTrue(schedule_rules.schedule_is_open(None, self.monday_evening))
        self.assertTrue(
            schedule_rules.schedule_is_open(
                schedule(enabled=False),
                self.monday_evening,
            )
        )

    def test_enabled_schedule_uses_local_weekday_and_end_exclusive_window(self):
        rule = schedule()
        self.assertTrue(schedule_rules.schedule_is_open(rule, self.monday_morning))
        self.assertFalse(schedule_rules.schedule_is_open(rule, self.monday_evening))
        self.assertFalse(
            schedule_rules.schedule_is_open(
                rule,
                datetime(2026, 8, 31, 18, 0),
            )
        )

    def test_profile_rule_takes_precedence_over_per_app_rule(self):
        config = {
            "weeklySchedule": schedule(start="10:00", end="18:00"),
            "appAvailability": {"paint": schedule(start="08:00", end="12:00")},
        }
        self.assertEqual(
            schedule_rules.tile_availability(
                config,
                "paint",
                when=self.monday_morning,
            ),
            {"allowed": False, "reason": "profile_schedule"},
        )

    def test_summary_lists_only_currently_blocked_tiles(self):
        config = {
            "weeklySchedule": {"enabled": False, "days": {}},
            "appAvailability": {
                "paint": schedule(start="10:00", end="18:00"),
            },
            "tiles": [{"id": "paint"}, {"id": "games"}],
        }
        self.assertEqual(
            schedule_rules.availability_summary(
                config,
                when=self.monday_morning,
            ),
            {"profileAllowed": True, "blockedTileIds": ["paint"]},
        )


if __name__ == "__main__":
    unittest.main()
