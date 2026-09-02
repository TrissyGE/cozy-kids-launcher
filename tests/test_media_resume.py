import json
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

    def test_vlc_positions_are_profile_specific_path_free_and_file_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            media = Path(directory) / "Film.mp4"
            media.write_bytes(b"first version")
            first_id = "1" * 24
            second_id = "2" * 24

            media_resume.save_resume_position(
                root,
                "default",
                first_id,
                media,
                25,
                120,
            )
            media_resume.save_resume_position(
                root,
                "alex",
                second_id,
                media,
                40,
                120,
            )

            self.assertEqual(
                media_resume.load_resume_position(root, "default", first_id, media),
                25,
            )
            self.assertEqual(
                media_resume.load_resume_position(root, "alex", second_id, media),
                40,
            )
            self.assertEqual(
                media_resume.load_resume_position(root, "default", second_id, media),
                0,
            )
            state = root / "default" / "vlc-positions.json"
            payload = state.read_text(encoding="utf-8")
            self.assertNotIn(str(media), payload)
            self.assertNotIn(media.name, payload)
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(state.stat().st_mode), 0o600)

            media.write_bytes(b"replacement with a different size")
            self.assertEqual(
                media_resume.load_resume_position(root, "default", first_id, media),
                0,
            )

    def test_vlc_positions_clear_near_the_start_and_end(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            media = Path(directory) / "Film.mp4"
            media.write_bytes(b"video")
            media_id = "1" * 24

            media_resume.save_resume_position(root, "default", media_id, media, 30, 120)
            self.assertEqual(
                media_resume.load_resume_position(root, "default", media_id, media),
                30,
            )
            media_resume.save_resume_position(root, "default", media_id, media, 2, 120)
            self.assertEqual(
                media_resume.load_resume_position(root, "default", media_id, media),
                0,
            )
            media_resume.save_resume_position(root, "default", media_id, media, 30, 120)
            media_resume.save_resume_position(root, "default", media_id, media, 115, 120)
            self.assertEqual(
                media_resume.load_resume_position(root, "default", media_id, media),
                0,
            )

    def test_corrupt_vlc_resume_state_and_invalid_values_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            profile = Path(
                media_resume.prepare_profile_resume_directory(root, "default")
            )
            media = Path(directory) / "Film.mp4"
            media.write_bytes(b"video")
            state = profile / "vlc-positions.json"
            state.write_text("not json", encoding="utf-8")

            self.assertEqual(
                media_resume.load_resume_position(root, "default", "1" * 24, media),
                0,
            )
            with self.assertRaisesRegex(ValueError, "mediaId"):
                media_resume.load_resume_position(root, "default", "../film", media)
            with self.assertRaisesRegex(ValueError, "position"):
                media_resume.save_resume_position(
                    root,
                    "default",
                    "1" * 24,
                    media,
                    True,
                    120,
                )

            state.write_bytes(b" " * (media_resume.MAX_RESUME_STATE_BYTES + 1))
            self.assertEqual(
                media_resume.load_resume_position(root, "default", "1" * 24, media),
                0,
            )

    def test_vlc_resume_collection_keeps_only_the_newest_bounded_items(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "media-resume"
            media = Path(directory) / "Film.mp4"
            media.write_bytes(b"video")
            for index in range(media_resume.MAX_RESUME_ITEMS + 5):
                media_resume.save_resume_position(
                    root,
                    "default",
                    f"{index:024x}",
                    media,
                    30,
                    120,
                )

            state = json.loads(
                (root / "default" / "vlc-positions.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(len(state["items"]), media_resume.MAX_RESUME_ITEMS)
            self.assertEqual(
                state["items"][0]["id"],
                f"{media_resume.MAX_RESUME_ITEMS + 4:024x}",
            )

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
