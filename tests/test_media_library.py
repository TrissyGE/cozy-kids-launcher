import sys
import tempfile
import unittest
from pathlib import Path


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
