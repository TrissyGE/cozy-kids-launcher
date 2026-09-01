import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import config_store
import config_validation
import profile_config


def legacy_config():
    return {
        "configVersion": 1,
        "language": "en",
        "pinHash": "",
        "title": "Hello Kiddo",
        "theme": "rosa",
        "layoutMode": "gross",
        "currentPage": 0,
        "timerMinutes": 30,
        "timerWarningMinutes": 5,
        "tiles": [{
            "id": "paint",
            "label": "Paint",
            "emoji": "🎨",
            "cmd": ["tuxpaint"],
            "visible": True,
        }],
    }


class ProfileConfigTests(unittest.TestCase):
    def test_schema_one_becomes_a_complete_default_profile(self):
        stored, migrated = config_store.migrate_config(legacy_config())

        self.assertTrue(migrated)
        self.assertEqual(stored["configVersion"], 2)
        self.assertEqual(stored["activeProfileId"], "default")
        self.assertEqual(stored["profiles"][0]["title"], "Hello Kiddo")
        self.assertEqual(stored["profiles"][0]["tiles"][0]["id"], "paint")
        self.assertNotIn("tiles", stored)

    def test_active_projection_preserves_the_existing_runtime_contract(self):
        stored = config_validation.validate_stored_config(legacy_config())
        runtime = profile_config.active_config(stored)

        self.assertEqual(runtime["title"], "Hello Kiddo")
        self.assertEqual(runtime["tiles"][0]["cmd"], ["tuxpaint"])
        self.assertEqual(
            runtime["profiles"],
            [{"id": "default", "name": "Kiddo", "avatar": "🌈"}],
        )

    def test_profiles_keep_tiles_themes_favorites_and_limits_independent(self):
        stored = config_validation.validate_stored_config(legacy_config())
        stored, second_id = profile_config.add_profile(
            stored,
            "Alex",
            "🚀",
            profile_id="alex",
        )
        stored = config_validation.validate_stored_config(stored)
        stored = profile_config.select_profile(stored, second_id)
        alex = profile_config.active_config(stored)
        alex["theme"] = "blau"
        alex["tiles"][0]["label"] = "Alex Paint"
        alex["favorites"] = ["paint"]
        alex["appLimits"] = {"paint": 20}
        alex["weeklySchedule"] = {
            "enabled": True,
            "days": {"monday": [{"start": "08:00", "end": "18:00"}]},
        }
        alex["appAvailability"] = {
            "paint": {
                "enabled": True,
                "days": {"monday": [{"start": "09:00", "end": "12:00"}]},
            },
        }
        stored = profile_config.merge_active_config(stored, alex)
        stored = config_validation.validate_stored_config(stored)

        default = profile_config.active_config(
            profile_config.select_profile(stored, "default")
        )
        alex = profile_config.active_config(stored)
        self.assertEqual(default["theme"], "rosa")
        self.assertEqual(default["tiles"][0]["label"], "Paint")
        self.assertEqual(default["favorites"], [])
        self.assertEqual(alex["theme"], "blau")
        self.assertEqual(alex["favorites"], ["paint"])
        self.assertEqual(alex["appLimits"], {"paint": 20})
        self.assertTrue(alex["weeklySchedule"]["enabled"])
        self.assertIn("paint", alex["appAvailability"])

    def test_active_and_last_profile_deletion_is_rejected(self):
        stored = config_validation.validate_stored_config(legacy_config())
        with self.assertRaisesRegex(ValueError, "active profile"):
            profile_config.remove_profile(stored, "default")

        stored, _ = profile_config.add_profile(
            stored,
            "Alex",
            profile_id="alex",
        )
        stored = profile_config.remove_profile(stored, "alex")
        self.assertEqual(len(stored["profiles"]), 1)

    def test_profile_collections_and_limits_are_bounded(self):
        stored = config_validation.validate_stored_config(legacy_config())
        stored["profiles"][0]["favorites"] = ["bad id"]
        with self.assertRaisesRegex(ValueError, "favorites"):
            config_validation.validate_stored_config(stored)

        stored = config_validation.validate_stored_config(legacy_config())
        stored["profiles"][0]["appLimits"] = {"paint": 181}
        with self.assertRaisesRegex(ValueError, "appLimits.paint"):
            config_validation.validate_stored_config(stored)

        stored = config_validation.validate_stored_config(legacy_config())
        stored["tiles"] = []
        with self.assertRaisesRegex(ValueError, "inside profiles"):
            config_validation.validate_stored_config(stored)


if __name__ == "__main__":
    unittest.main()
