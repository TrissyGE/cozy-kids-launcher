import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import retro_games


class RetroArchiveTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name).resolve()
        self.path = self.root / "Collection Entry.zip"

    def write_archive(self, *entries, compression=0):
        with ZipFile(self.path, "w", compression=compression) as archive:
            for name, contents in entries:
                archive.writestr(name, contents)

    def test_discovery_and_cover_use_the_rom_inside_the_archive(self):
        self.write_archive(("Folder/", b""), ("Folder/Example (Europe).GBC", b"fixture"),
                           compression=ZIP_DEFLATED)
        games, unavailable, truncated = retro_games.scan_retro_games([str(self.root)])
        self.assertEqual((len(games), unavailable, truncated), (1, 0, False))
        game = next(iter(games.values()))
        self.assertEqual(game["title"], "Example (Europe)")
        self.assertEqual(game["path"], str(self.path))
        self.assertEqual(game["romExtension"], ".gbc")
        with patch.object(retro_games, "_download_cover", return_value=b"cover") as cover:
            self.assertEqual(retro_games.retro_cover(game, download=True), b"cover")
            self.assertEqual(cover.call_args.args[:2], ("Nintendo - Game Boy Color", "Example (Europe)"))

    def test_rejects_unrelated_files_traversal_and_symbolic_links(self):
        symlink = ZipInfo("link.gba")
        symlink.create_system = 3
        symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
        cases = (
            (("../Game.gba", b"fixture"),),
            (("/Game.gba", b"fixture"),),
            (("C:\\Game.gba", b"fixture"),),
            (("Game.gba", b"fixture"), ("Second.gba", b"fixture")),
            (("Game.gba", b"fixture"), ("readme.txt", b"note")),
            ((symlink, b"/tmp/game.gba"),),
            (("Game.gba", b""),),
        )
        for entries in cases:
            with self.subTest(entries=entries):
                self.write_archive(*entries)
                self.assertIsNone(retro_games.inspect_rom_zip(str(self.path)))

    def test_checks_member_size_and_central_directory_before_decompression(self):
        self.write_archive(("Game.gba", b"12345"))
        with patch.object(retro_games, "MAX_ROM_BYTES", 4):
            self.assertIsNone(retro_games.inspect_rom_zip(str(self.path)))
        with patch.object(retro_games, "MAX_ZIP_DIRECTORY_BYTES", 10), \
                patch.object(retro_games.zipfile, "ZipFile") as open_zip:
            self.assertIsNone(retro_games.inspect_rom_zip(str(self.path)))
            open_zip.assert_not_called()

    def test_corrupted_payload_is_rejected_before_emulator_launch(self):
        self.write_archive(("Game.gba", b"original payload"))
        games, _, _ = retro_games.scan_retro_games([str(self.root)])
        game = next(iter(games.values()))
        state = self.root / "state"
        command = retro_games.emulator_command("mgba-qt", game, state, "default")
        self.assertEqual(command[-1], str(self.path))
        self.assertIn(f"savestatePath={state / 'default' / game['id']}", command)
        before = self.path.stat()
        raw = self.path.read_bytes().replace(b"original payload", b"modified payload", 1)
        self.path.write_bytes(raw)
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "archive is unavailable or damaged"):
            retro_games.emulator_command("mgba-qt", game, state, "default")


if __name__ == "__main__":
    unittest.main()
