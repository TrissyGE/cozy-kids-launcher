import copy
import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import config_validation
import parent_auth


def base_config():
    return {
        "configVersion": 1,
        "language": "en",
        "layoutMode": "gross",
        "pinHash": "",
        "currentPage": 0,
        "timerMinutes": 0,
        "timerWarningMinutes": 5,
        "autoScanDone": True,
        "tiles": [
            {
                "id": "paint",
                "label": "Paint",
                "emoji": "🎨",
                "cmd": ["paint-app"],
                "visible": True,
            }
        ],
    }


class ConfigValidationTests(unittest.TestCase):
    def test_future_compatible_keys_survive_while_pin_state_stays_server_owned(self):
        data = base_config()
        data["futureCompatibleKey"] = {"kept": True}
        data["pinHash"] = "attacker-controlled"
        data["pinConfigured"] = False

        validated = config_validation.validate_config(
            data,
            existing_pin_hash="0123456789abcdef",
        )

        self.assertEqual(validated["futureCompatibleKey"], {"kept": True})
        self.assertEqual(validated["pinHash"], "0123456789abcdef")
        self.assertNotIn("pinConfigured", validated)

    def test_imported_pin_hash_must_use_a_supported_format(self):
        data = base_config()
        data["pinHash"] = parent_auth.hash_pin("1234", salt="00" * 16)
        validated = config_validation.validate_config(data, allow_pin_hash=True)
        self.assertEqual(validated["pinHash"], data["pinHash"])

        data["pinHash"] = "attacker-controlled"
        with self.assertRaisesRegex(ValueError, "unsupported format"):
            config_validation.validate_config(data, allow_pin_hash=True)

    def test_tile_identifiers_commands_and_visibility_are_bounded(self):
        data = base_config()
        data["tiles"].append(copy.deepcopy(data["tiles"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate tile id"):
            config_validation.validate_config(data)

        data = base_config()
        data["tiles"][0]["id"] = "../paint"
        with self.assertRaisesRegex(ValueError, "invalid characters"):
            config_validation.validate_config(data)

        data = base_config()
        data["tiles"][0]["visible"] = "yes"
        with self.assertRaisesRegex(ValueError, "must be a boolean"):
            config_validation.validate_config(data)

        data = base_config()
        data["tiles"][0]["browserAllowedOrigins"] = [
            "https://Media.Example/path",
            "https://media.example",
        ]
        validated = config_validation.validate_config(data)
        self.assertEqual(
            validated["tiles"][0]["browserAllowedOrigins"],
            ["https://media.example"],
        )

        data["tiles"][0]["browserAllowedOrigins"] = ["file:///etc/passwd"]
        with self.assertRaisesRegex(ValueError, "browserAllowedOrigins"):
            config_validation.validate_config(data)

    def test_collection_and_numeric_limits_reject_untrusted_types(self):
        data = base_config()
        data["tiles"] = [
            {"id": f"tile-{index}", "cmd": []}
            for index in range(config_validation.MAX_TILES + 1)
        ]
        with self.assertRaisesRegex(ValueError, "maximum"):
            config_validation.validate_config(data)

        for field, value in (
            ("currentPage", True),
            ("timerMinutes", 181),
            ("timerWarningMinutes", -1),
        ):
            with self.subTest(field=field, value=value):
                data = base_config()
                data[field] = value
                with self.assertRaisesRegex(ValueError, field):
                    config_validation.validate_config(data)

        data = base_config()
        data["setupCompleted"] = "yes"
        with self.assertRaisesRegex(ValueError, "setupCompleted must be a boolean"):
            config_validation.validate_config(data)

        data = base_config()
        data["activityTrackingEnabled"] = "yes"
        with self.assertRaisesRegex(ValueError, "activityTrackingEnabled must be a boolean"):
            config_validation.validate_config(data)

        for field in (
            "themeMotionEnabled",
            "themeTimeOfDayEnabled",
            "soundFeedbackEnabled",
            "speechFeedbackEnabled",
            "accessibilityLargeText",
            "accessibilityHighContrast",
            "accessibilityReducedMotion",
            "accessibilityKeyboardFocus",
        ):
            with self.subTest(field=field):
                data = base_config()
                data[field] = "yes"
                with self.assertRaisesRegex(ValueError, f"{field} must be a boolean"):
                    config_validation.validate_config(data)

        data = base_config()
        data["themeMotionEnabled"] = True
        data["themeTimeOfDayEnabled"] = False
        data["soundFeedbackEnabled"] = True
        data["speechFeedbackEnabled"] = False
        data["accessibilityLargeText"] = True
        data["accessibilityHighContrast"] = False
        data["accessibilityReducedMotion"] = True
        data["accessibilityKeyboardFocus"] = False
        validated = config_validation.validate_config(data)
        self.assertTrue(validated["themeMotionEnabled"])
        self.assertFalse(validated["themeTimeOfDayEnabled"])
        self.assertTrue(validated["soundFeedbackEnabled"])
        self.assertFalse(validated["speechFeedbackEnabled"])
        self.assertTrue(validated["accessibilityLargeText"])
        self.assertFalse(validated["accessibilityHighContrast"])
        self.assertTrue(validated["accessibilityReducedMotion"])
        self.assertFalse(validated["accessibilityKeyboardFocus"])

    def test_schedule_collections_are_bounded_and_validated(self):
        data = base_config()
        data["weeklySchedule"] = {
            "enabled": True,
            "days": {"monday": [{"start": "08:00", "end": "18:00"}]},
        }
        data["appAvailability"] = {
            "paint": {
                "enabled": True,
                "days": {"saturday": [{"start": "09:00", "end": "12:00"}]},
            },
        }
        validated = config_validation.validate_config(data)
        self.assertTrue(validated["weeklySchedule"]["enabled"])
        self.assertIn("paint", validated["appAvailability"])

        data["appAvailability"]["bad id"] = {"enabled": False, "days": {}}
        with self.assertRaisesRegex(ValueError, "invalid tile id"):
            config_validation.validate_config(data)

        data = base_config()
        data["weeklySchedule"] = {
            "enabled": True,
            "days": {"monday": [{"start": "18:00", "end": "08:00"}]},
        }
        with self.assertRaisesRegex(ValueError, "end after"):
            config_validation.validate_config(data)

    def test_public_projection_never_mutates_or_exposes_the_pin_hash(self):
        data = base_config()
        data["pinHash"] = "0123456789abcdef"

        public = config_validation.public_config(data)

        self.assertNotIn("pinHash", public)
        self.assertTrue(public["pinConfigured"])
        self.assertEqual(data["pinHash"], "0123456789abcdef")
