import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import translation_data


class TranslationDataTests(unittest.TestCase):
    def test_partial_translation_keeps_default_messages(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "en.json").write_text('{"title": "Cozy Kids", "count": "{count} apps"}', encoding="utf-8")
            (root / "de.json").write_text('{"count": "{count} Apps"}', encoding="utf-8")
            with patch.object(translation_data, "TRANSLATION_ROOT", root):
                self.assertEqual(
                    translation_data.load_translations("de"),
                    {"title": "Cozy Kids", "count": "{count} Apps"},
                )

    def test_invalid_translation_reports_the_affected_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "en.json").write_text('{"count": "{count} apps"}', encoding="utf-8")
            for translated, message in [
                ('{"count": "Apps"}', "placeholders differ for count"),
                ('{"cout": "{count} Apps"}', "unknown translation key cout"),
                ('{"count": "A", "count": "B"}', "Duplicate translation key: count"),
                (json.dumps({"count": "{count}\nApps"}), "count must contain single-line text"),
            ]:
                with self.subTest(translated=translated):
                    (root / "de.json").write_text(translated, encoding="utf-8")
                    with patch.object(translation_data, "TRANSLATION_ROOT", root):
                        with self.assertRaisesRegex(ValueError, message):
                            translation_data.load_translations("de")
