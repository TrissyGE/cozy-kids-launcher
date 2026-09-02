import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SCREENSHOTS = {
    "screenshot-admin-appearance.png",
    "screenshot-admin-children.png",
    "screenshot-admin-general.png",
    "screenshot-admin-screen-time.png",
    "screenshot-home-default.png",
    "screenshot-home-world.png",
    "screenshot-media-library.png",
    "screenshot-profile-picker.png",
    "screenshot-theme-picker.png",
}


def png_dimensions(path):
    payload = path.read_bytes()[:24]
    if payload[:8] != b"\x89PNG\r\n\x1a\n" or payload[12:16] != b"IHDR":
        raise ValueError(f"Not a PNG image: {path}")
    return struct.unpack(">II", payload[16:24])


class ScreenshotGalleryTests(unittest.TestCase):
    def test_gallery_contains_the_canonical_images_at_one_aspect_ratio(self):
        screenshot_root = ROOT / "screenshots"
        actual = {path.name for path in screenshot_root.glob("*.png")}
        self.assertEqual(actual, EXPECTED_SCREENSHOTS)
        for name in EXPECTED_SCREENSHOTS:
            self.assertEqual(png_dimensions(screenshot_root / name), (1440, 900), name)

    def test_readme_and_guide_reference_every_image(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        guide = (ROOT / "docs" / "SCREENSHOTS.md").read_text(encoding="utf-8")
        for name in EXPECTED_SCREENSHOTS:
            self.assertIn(f"screenshots/{name}", readme)
            self.assertIn(f"screenshots/{name}", guide)


if __name__ == "__main__":
    unittest.main()
