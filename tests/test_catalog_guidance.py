import datetime
import json
from pathlib import Path
import unittest
from urllib.parse import urlsplit


class CatalogGuidanceTests(unittest.TestCase):
    def test_guidance_is_bilingual_sourced_and_explicit_about_review_scope(self):
        path = Path(__file__).resolve().parents[1] / "src" / "recommendations.json"
        entries = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(entries), len({entry["id"] for entry in entries}))
        for entry in entries:
            info = entry.get("guidance")
            if not info:
                continue
            with self.subTest(app=entry["id"]):
                self.assertIn(info["offline"], ("yes", "partial", "no"))
                self.assertEqual(urlsplit(info["source"]).scheme, "https")
                self.assertTrue(urlsplit(info["source"]).hostname)
                self.assertIsNone(urlsplit(info["source"]).username)
                self.assertIsNone(urlsplit(info["source"]).password)
                datetime.date.fromisoformat(info["reviewed"])
                self.assertTrue(set(info.get("input", [])) <= {"mouse", "keyboard", "touch"})
                for prefix in ("age", "network"):
                    self.assertEqual(bool(info.get(prefix + "_de")), bool(info.get(prefix + "_en")))
                references = info.get("references", [])
                self.assertIsInstance(references, list)
                self.assertLessEqual(len(references), 4)
                urls = {info["source"]}
                for reference in references:
                    url = urlsplit(reference["url"])
                    self.assertEqual(url.scheme, "https")
                    self.assertTrue(url.hostname)
                    self.assertIsNone(url.username)
                    self.assertIsNone(url.password)
                    self.assertNotIn(reference["url"], urls)
                    urls.add(reference["url"])
                    for language in ("de", "en"):
                        self.assertTrue(reference["label_" + language].strip())


if __name__ == "__main__":
    unittest.main()
