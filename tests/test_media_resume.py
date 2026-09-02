import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import media_resume


class MediaResumeTests(unittest.TestCase):
    def test_profile_directories_are_private_and_separate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            first = Path(media_resume.prepare_profile_resume_directory(root, "default"))
            second = Path(media_resume.prepare_profile_resume_directory(root, "alex"))

            self.assertEqual(first, root / "default")
            self.assertEqual(second, root / "alex")
            self.assertTrue(first.is_dir())
            self.assertTrue(second.is_dir())
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(first.stat().st_mode), 0o700)

    def test_invalid_profile_ids_cannot_escape_the_resume_root(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            for profile_id in ("", "../alex", "alex/other", "bad profile"):
                with self.subTest(profile_id=profile_id), self.assertRaisesRegex(
                    ValueError,
                    "profileId",
                ):
                    media_resume.prepare_profile_resume_directory(root, profile_id)
            self.assertFalse(root.exists())

    def test_profile_removal_does_not_touch_other_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            first = Path(media_resume.prepare_profile_resume_directory(root, "default"))
            second = Path(media_resume.prepare_profile_resume_directory(root, "alex"))
            (first / "position").write_text("start=15", encoding="utf-8")
            (second / "position").write_text("start=30", encoding="utf-8")

            media_resume.remove_profile_resume_directory(root, "alex")
            media_resume.remove_profile_resume_directory(root, "alex")

            self.assertTrue(first.is_dir())
            self.assertTrue((first / "position").is_file())
            self.assertFalse(second.exists())

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links unavailable")
    def test_existing_profile_symlink_is_rejected_and_unlinked_without_following(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            target = Path(directory) / "outside"
            root.mkdir()
            target.mkdir()
            marker = target / "keep"
            marker.write_text("private", encoding="utf-8")
            link = root / "alex"
            try:
                link.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")

            with self.assertRaisesRegex(OSError, "symbolic link"):
                media_resume.prepare_profile_resume_directory(root, "alex")
            media_resume.remove_profile_resume_directory(root, "alex")

            self.assertFalse(link.exists())
            self.assertEqual(marker.read_text(encoding="utf-8"), "private")

    @unittest.skipUnless(hasattr(os, "symlink"), "symbolic links unavailable")
    def test_resume_root_symlink_is_never_followed(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "outside"
            target.mkdir()
            profile = target / "alex"
            profile.mkdir()
            marker = profile / "keep"
            marker.write_text("private", encoding="utf-8")
            root = Path(directory) / "media-resume"
            try:
                root.symlink_to(target, target_is_directory=True)
            except OSError as exc:
                self.skipTest(f"symbolic links unavailable: {exc}")

            with self.assertRaisesRegex(OSError, "root"):
                media_resume.prepare_profile_resume_directory(root, "alex")
            with self.assertRaisesRegex(OSError, "root"):
                media_resume.remove_profile_resume_directory(root, "alex")

            self.assertEqual(marker.read_text(encoding="utf-8"), "private")


if __name__ == "__main__":
    unittest.main()
