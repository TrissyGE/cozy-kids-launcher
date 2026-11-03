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


    def test_runtime_locale_tracks_saved_language_and_uses_default_on_invalid_config(self):
        from runtime_locale import saved_locale

        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.json"
            for language in ("de", "es", "fr", "en"):
                config.write_text(json.dumps({"language": language}), encoding="utf-8")
                self.assertEqual(saved_locale(config)["timer_minutes"],
                                 translation_data.load_translations(language)["timer_minutes"])
            config.write_text("{", encoding="utf-8")
            self.assertEqual(saved_locale(config)["timer_minutes"],
                             translation_data.load_translations("en")["timer_minutes"])

    def test_wrapper_escapes_html_and_script_contexts(self):
        from runtime_locale import render_browser_wrapper

        value = '</script><img src=x onerror="alert(1)">'
        with patch("runtime_locale.runtime_locale", return_value=("en", {"example": value})):
            page = render_browser_wrapper('<p>{{html_example}}</p><script>const text={{js_example}};</script>', "en")
        self.assertIn('&lt;/script&gt;&lt;img src=x onerror=&quot;alert(1)&quot;&gt;', page)
        self.assertNotIn("<img", page)
        self.assertEqual(page.count("</script>"), 1)


    def test_direction_defaults_to_ltr_and_respects_registry_metadata(self):
        from language_registry import REGISTRY, language_direction
        from runtime_locale import render_browser_wrapper

        self.assertEqual(language_direction("en"), "ltr")
        self.assertEqual(language_direction("unknown"), "ltr")
        with patch.dict(REGISTRY, {"languages": [{"code": "en", "direction": "rtl"}]}):
            self.assertEqual(language_direction("en"), "rtl")
            page = render_browser_wrapper('<html lang="{{html_language}}" dir="{{html_direction}}">', "en")
            self.assertEqual(page, '<html lang="en" dir="rtl">')
