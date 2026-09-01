import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import media_library


class MediaDiscoveryTests(unittest.TestCase):
    def test_supported_media_is_found_recursively(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "family" / "movies"
            nested.mkdir(parents=True)
            (nested / "movie.mp4").write_bytes(b"test")

            self.assertTrue(media_library.has_media(root))
            self.assertFalse(media_library.has_media(root / "missing"))

    def test_unsupported_files_do_not_count_as_media(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "notes.txt").write_text("not media", encoding="utf-8")

            self.assertFalse(media_library.has_media(root))

    def test_locations_preserve_order_and_deduplicate_real_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            videos = root / "Videos"
            music = root / "Music"
            empty = root / "Empty"
            videos.mkdir()
            music.mkdir()
            empty.mkdir()
            (videos / "movie.mkv").write_bytes(b"video")
            (music / "song.ogg").write_bytes(b"audio")

            locations = media_library.media_locations(
                (videos, videos / ".." / "Videos", empty, music)
            )

        self.assertEqual(locations, [videos, music])

    def test_first_location_returns_none_when_all_candidates_are_empty(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = Path(temp_dir) / "Videos"
            second = Path(temp_dir) / "Music"
            first.mkdir()
            second.mkdir()

            self.assertIsNone(media_library.media_location((first, second)))

    def test_catalog_discovers_media_and_adjacent_covers_without_exposing_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "Videos"
            album = root / "Family"
            album.mkdir(parents=True)
            (album / "A_Film.MP4").write_bytes(b"video")
            (album / "A_Film.JPG").write_bytes(b"cover")
            (album / "Bedtime.ogg").write_bytes(b"audio")

            first, truncated = media_library.scan_media_catalog((root,))
            second, _ = media_library.scan_media_catalog((root,))
            public = media_library.public_media_catalog(first)

        self.assertFalse(truncated)
        self.assertEqual([item["title"] for item in first], ["A Film", "Bedtime"])
        self.assertEqual([item["kind"] for item in first], ["video", "audio"])
        self.assertEqual(first[0]["id"], second[0]["id"])
        self.assertRegex(first[0]["id"], r"^[0-9a-f]{24}$")
        self.assertTrue(first[0]["coverPath"].endswith("A_Film.JPG"))
        self.assertEqual(
            public[0]["coverUrl"],
            f"/api/media/cover?id={first[0]['id']}",
        )
        self.assertEqual(public[1]["coverUrl"], "")
        self.assertNotIn("path", public[0])
        self.assertNotIn(temp_dir, repr(public))

    def test_catalog_is_bounded_deduplicated_and_skips_hidden_content(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            hidden = root / ".private"
            hidden.mkdir()
            (hidden / "secret.mp4").write_bytes(b"private")
            (root / "one.mp4").write_bytes(b"one")
            (root / "two.mp4").write_bytes(b"two")

            entries, truncated = media_library.scan_media_catalog(
                (root, root / "."),
                limit=1,
            )

        self.assertTrue(truncated)
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["title"], "one")

    def test_catalog_skips_media_links_that_leave_the_configured_root(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            base = Path(temp_dir)
            root = base / "Videos"
            root.mkdir()
            outside = base / "private.mp4"
            outside.write_bytes(b"private")
            try:
                (root / "linked.mp4").symlink_to(outside)
            except OSError as exc:
                self.skipTest(f"Symbolic links are unavailable: {exc}")

            entries, truncated = media_library.scan_media_catalog((root,))

        self.assertFalse(truncated)
        self.assertEqual(entries, [])

    def test_catalog_item_requires_an_exact_opaque_identifier(self):
        entry = {"id": "a" * 24, "title": "Film", "kind": "video"}
        self.assertIs(media_library.catalog_item([entry], "a" * 24), entry)
        self.assertIsNone(media_library.catalog_item([entry], "a" * 23))
        self.assertIsNone(media_library.catalog_item([entry], None))

    def test_catalog_rejects_unbounded_or_invalid_limits(self):
        for limit in (0, -1, True, "10"):
            with self.subTest(limit=limit):
                with self.assertRaisesRegex(ValueError, "positive integer"):
                    media_library.scan_media_catalog((), limit=limit)

    def test_catalog_caps_total_files_scanned_even_before_the_item_limit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "a-not-media.txt").write_text("skip", encoding="utf-8")
            (root / "b-film.mp4").write_bytes(b"video")
            with mock.patch.object(media_library, "MAX_MEDIA_SCAN_FILES", 1):
                entries, truncated = media_library.scan_media_catalog((root,))

        self.assertTrue(truncated)
        self.assertEqual(entries, [])


class MediaPlayerTests(unittest.TestCase):
    def test_player_detection_uses_the_existing_fallback_order(self):
        available = {"mpv", "totem"}
        player = media_library.find_media_player(
            which=lambda name: f"/usr/bin/{name}" if name in available else None
        )
        self.assertEqual(player, "mpv")

    def test_player_commands_keep_fullscreen_and_location_contracts(self):
        locations = ["/home/kid/Videos", "/home/kid/Music"]
        self.assertEqual(
            media_library.media_player_command("vlc", locations),
            [
                "vlc",
                "--fullscreen",
                "--play-and-exit",
                "--no-video-title-show",
                *locations,
            ],
        )
        self.assertEqual(
            media_library.media_player_command("mpv", locations),
            ["mpv", "--fullscreen", *locations],
        )
        self.assertEqual(
            media_library.media_player_command("totem", locations),
            ["totem", *locations],
        )
