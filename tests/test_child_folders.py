import copy
from pathlib import Path
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from config_validation import public_config, validate_stored_config
from profile_config import active_config, add_profile, select_profile


def config():
    return {"configVersion": 1, "tiles": [
        {"id": "paint", "label": "Paint", "cmd": ["tuxpaint"], "visible": True, "folderId": "creative"},
        {"id": "hidden", "label": "Hidden", "cmd": ["kturtle"], "visible": False, "folderId": "creative"},
    ], "folders": [{"id": "creative", "label": "Creative", "emoji": "🎨"}], "pinHash": ""}


class ChildFolderTests(unittest.TestCase):
    def test_legacy_profile_migration_retains_folder_and_tile_identity(self):
        original = config()
        migrated = validate_stored_config(original)
        self.assertEqual(migrated["configVersion"], 2)
        self.assertEqual(migrated["profiles"][0]["folders"], original["folders"])
        self.assertEqual(migrated["profiles"][0]["tiles"][0]["cmd"], ["tuxpaint"])
        child = public_config(migrated)
        self.assertEqual(child["folders"], original["folders"])
        self.assertEqual(child["tiles"][0]["id"], "paint")
        self.assertFalse(child["tiles"][1]["visible"])

    def test_profile_duplication_copies_folder_structure_without_shared_mutable_state(self):
        migrated = validate_stored_config(config())
        duplicated, identifier = add_profile(migrated, "Second", "🌟", source_profile_id="default")
        selected = active_config(select_profile(duplicated, identifier))
        self.assertEqual(selected["folders"], migrated["profiles"][0]["folders"])
        duplicated["profiles"][1]["folders"][0]["label"] = "Different name"
        self.assertEqual(duplicated["profiles"][0]["folders"][0]["label"], "Creative")
        self.assertNotIn("folders", duplicated)

    def test_references_are_validated_in_the_owning_profile(self):
        migrated = validate_stored_config(config())
        other = copy.deepcopy(migrated["profiles"][0])
        other.update(id="other", name="Other", folders=[])
        migrated["profiles"].append(other)
        with self.assertRaisesRegex(ValueError, "folderId"):
            validate_stored_config(migrated)

    def test_malformed_or_unbounded_folders_and_orphan_references_are_rejected(self):
        cases = [None, {}, [None], [{"id": "../escape", "label": "Bad"}],
                 [{"id": "same", "label": "A"}, {"id": "same", "label": "B"}],
                 [{"id": "blank", "label": " "}], [{"id": "long", "label": "x" * 81}],
                 [{"id": str(index), "label": "Folder"} for index in range(21)]]
        for folders in cases:
            with self.subTest(folders=folders):
                candidate = config()
                candidate["folders"] = folders
                with self.assertRaises(ValueError):
                    validate_stored_config(candidate)
        for invalid in (True, [], "unknown", None):
            candidate = config()
            candidate["tiles"][0]["folderId"] = invalid
            with self.subTest(reference=invalid), self.assertRaises(ValueError):
                validate_stored_config(candidate)

    def test_old_config_without_folders_still_validates(self):
        candidate = config()
        del candidate["folders"]
        for tile in candidate["tiles"]:
            tile.pop("folderId")
        result = validate_stored_config(candidate)
        self.assertNotIn("folders", result["profiles"][0])


if __name__ == "__main__":
    unittest.main()
