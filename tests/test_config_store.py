import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import config_store


class ConfigStoreTests(unittest.TestCase):
    def test_atomic_write_round_trip_keeps_unicode_and_a_final_newline(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            expected = {
                "configVersion": 1,
                "title": "Abenteuer 🌈",
                "tiles": [],
            }

            config_store.atomic_write_config(str(path), expected)

            self.assertEqual(config_store.read_config(str(path)), expected)
            self.assertTrue(path.read_bytes().endswith(b"\n"))
            self.assertFalse(list(path.parent.glob("config-*.json")))

    def test_failed_atomic_replace_preserves_the_previous_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "config.json"
            previous = {"configVersion": 1, "title": "Before", "tiles": []}
            path.write_text(json.dumps(previous), encoding="utf-8")

            with mock.patch.object(
                config_store.os,
                "replace",
                side_effect=OSError("simulated replacement failure"),
            ):
                with self.assertRaisesRegex(OSError, "replacement failure"):
                    config_store.atomic_write_config(
                        str(path),
                        {"configVersion": 1, "title": "After", "tiles": []},
                    )

            self.assertEqual(config_store.read_config(str(path)), previous)
            self.assertFalse(list(path.parent.glob("config-*.json")))


if __name__ == "__main__":
    unittest.main()
