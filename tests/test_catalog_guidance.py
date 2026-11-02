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
                datetime.date.fromisoformat(info["reviewed"])
                self.assertTrue(set(info.get("input", [])) <= {"mouse", "keyboard", "touch"})
                for prefix in ("age", "network"):
                    self.assertEqual(bool(info.get(prefix + "_de")), bool(info.get(prefix + "_en")))


if __name__ == "__main__":
    unittest.main()
