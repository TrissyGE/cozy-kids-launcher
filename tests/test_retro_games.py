import os
from pathlib import Path
import stat
import struct
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import retro_games


class Ps1DiscSetTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform.startswith("linux"), "Test requires symbolic links")
    def test_miyoo_cover_is_local_and_same_folder_cover_takes_priority(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            sidecar = root / "Game.png"
            images = root / "Imgs"
            images.mkdir()
            miyoo = images / sidecar.name
            png = b"\x89PNG\r\n\x1a\n"
            miyoo.write_bytes(png + b"miyoo")
            game = {"path": str(root / "Game.m3u"), "title": "Game"}
            with patch.object(retro_games, "_download_cover") as download:
                self.assertEqual(retro_games.retro_cover(game), png + b"miyoo")
                sidecar.write_bytes(png + b"sidecar")
                self.assertEqual(retro_games.retro_cover(game), png + b"sidecar")
                sidecar.unlink()
                target = root / "Unrelated.png"
                target.write_bytes(png + b"unrelated")
                miyoo.unlink()
                miyoo.symlink_to(target)
                self.assertEqual(retro_games.retro_cover(game), b"")
                download.assert_not_called()

    @unittest.skipUnless(sys.platform.startswith("linux"), "PS1 runtime uses Linux paths")
    def test_playlist_rejects_unsafe_or_ambiguous_disc_references(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            header = bytearray(124)
            struct.pack_into(">8sII", header, 0, b"MComprHD", 124, 5)
            struct.pack_into(">QQQII", header, 32, 19584, 124, 125, 19584, 2448)
            for name in ("One.chd", "Two.chd"):
                (root / name).write_bytes(header + b"fixture")
            (root / "Link.chd").symlink_to(root / "Two.chd")
            (root / "Broken.chd").write_bytes(b"invalid")
            playlist = root / "Test.m3u"
            for reference in ("../Two.chd", "/Two.chd", "/_hidden/../Two.chd", "//Two.chd",
                              "C:/Two.chd", "Link.chd", "Broken.chd", "Test.m3u", "One.chd",
                              "Two.chd#member", "Missing.chd"):
                with self.subTest(reference=reference):
                    playlist.write_text(f"One.chd\n{reference}\n", encoding="utf-8")
                    self.assertIsNone(retro_games._ps1_disc_set(str(playlist)))
            playlist.write_bytes(b"#" * (retro_games.MAX_PLAYLIST_BYTES + 1))
            self.assertIsNone(retro_games._ps1_disc_set(str(playlist)))


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
            (("Folder/", b"unexpected data"), ("Game.gba", b"fixture")),
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
        self.assertEqual(command[4:6], ["mgba-qt", "--fullscreen"])
        self.assertIn(f"savestatePath={state / 'default' / game['id']}", command)
        before = self.path.stat()
        raw = self.path.read_bytes().replace(b"original payload", b"modified payload", 1)
        self.path.write_bytes(raw)
        os.utime(self.path, ns=(before.st_atime_ns, before.st_mtime_ns))
        with self.assertRaisesRegex(ValueError, "archive is unavailable or damaged"):
            retro_games.emulator_command("mgba-qt", game, state, "default")

    def test_mednafen_routes_loose_and_archived_cartridges_to_their_system(self):
        systems = {
            "nes": ("nes", "Nintendo - Nintendo Entertainment System"),
            "sfc": ("snes", "Nintendo - Super Nintendo Entertainment System"),
            "smc": ("snes", "Nintendo - Super Nintendo Entertainment System"),
            "sms": ("sms", "Sega - Master System - Mark III"),
            "gg": ("gg", "Sega - Game Gear"),
        }
        for extension, (module, cover_system) in systems.items():
            for archived in (False, True):
                with self.subTest(extension=extension, archived=archived):
                    filename = f"Local Game.{extension}"
                    path = self.root / (f"{extension}.zip" if archived else filename)
                    if archived:
                        with ZipFile(path, "w", compression=ZIP_DEFLATED) as archive:
                            archive.writestr(filename, b"fixture")
                    else:
                        path.write_bytes(b"fixture")
                    games, _, _ = retro_games.scan_retro_games([str(self.root)])
                    game = next(game for game in games.values() if game["path"] == str(path))
                    self.assertEqual(retro_games.emulator_binary(game), "mednafen")
                    state = self.root / "state"
                    command = retro_games.emulator_command("/usr/games/mednafen", game, state, "default")
                    self.assertEqual(command[-1], str(path))
                    self.assertIn(f"MEDNAFEN_HOME={state / 'default' / game['id']}", command)
                    self.assertEqual(command[command.index("-force_module") + 1], module)
                    with patch.object(retro_games, "_download_cover", return_value=b"cover") as cover:
                        self.assertEqual(retro_games.retro_cover(game, download=True), b"cover")
                        self.assertEqual(cover.call_args.args[:2], (cover_system, "Local Game"))

    def test_mednafen_does_not_launch_with_an_unapproved_ips_sidecar(self):
        rom = self.root / "Local Game.nes"
        rom.write_bytes(b"fixture")
        games, _, _ = retro_games.scan_retro_games([str(self.root)])
        game = next(iter(games.values()))
        Path(str(rom) + ".ips").write_bytes(b"patch")
        with self.assertRaisesRegex(ValueError, "unapproved IPS patch"):
            retro_games.emulator_command("mednafen", game, self.root / "state", "default")


if __name__ == "__main__":
    unittest.main()
