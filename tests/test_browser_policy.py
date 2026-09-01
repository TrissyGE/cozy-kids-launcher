import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import browser_policy


class BrowserPolicyTests(unittest.TestCase):
    def test_web_origins_are_canonical_and_keep_non_default_ports(self):
        self.assertEqual(
            browser_policy.web_origin("HTTPS://Bücher.example:443/kids?q=1"),
            "https://xn--bcher-kva.example",
        )
        self.assertEqual(
            browser_policy.web_origin("http://127.0.0.1:8080/play"),
            "http://127.0.0.1:8080",
        )

    def test_unsafe_or_credentialed_web_urls_are_rejected(self):
        for value in (
            "file:///etc/passwd",
            "javascript:alert(1)",
            "https://parent:secret@example.com",
            "https://bad host.example",
            "https://example.com:99999",
        ):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "Invalid browser URL"):
                    browser_policy.web_origin(value)

    def test_extra_origins_are_bounded_canonical_and_deduplicated(self):
        self.assertEqual(
            browser_policy.normalize_browser_allowed_origins([
                "https://media.example/path",
                "https://MEDIA.example",
                "http://localhost:8080/start",
            ]),
            ["https://media.example", "http://localhost:8080"],
        )
        with self.assertRaisesRegex(ValueError, "at most"):
            browser_policy.normalize_browser_allowed_origins(
                [f"https://site-{index}.example" for index in range(21)]
            )

    def test_start_origin_is_always_allowed_without_duplication(self):
        self.assertEqual(
            browser_policy.allowed_frame_origins(
                {
                    "browserAllowedOrigins": [
                        "https://kids.example/other",
                        "https://media.example",
                    ]
                },
                "https://kids.example/start",
            ),
            ["https://kids.example", "https://media.example"],
        )

    def test_csp_contains_only_exact_validated_frame_sources(self):
        policy = browser_policy.embedded_browser_csp([
            "https://kids.example",
            "https://media.example",
        ])
        self.assertIn(
            "frame-src https://kids.example https://media.example;",
            policy,
        )
        self.assertIn("object-src 'none'", policy)
        self.assertNotIn("*", policy)


if __name__ == "__main__":
    unittest.main()
