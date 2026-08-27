import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import backup_store


class BackupStoreTests(unittest.TestCase):
    def write_backup(self, root, backup_id, data):
        directory = root / backup_id
        directory.mkdir(parents=True)
        (directory / "config.json").write_text(
            json.dumps(data),
            encoding="utf-8",
        )
        return directory

    def test_discovery_returns_only_safe_timestamped_config_backups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.write_backup(root, "20260825-120000", {"configVersion": 1})
            self.write_backup(
                root,
                "restore-20260826-130000-deadbeef",
                {"configVersion": 1},
            )
            self.write_backup(root, "manual-copy", {"configVersion": 1})
            (root / "20260824-090000").mkdir()

            discovered = backup_store.discover_config_backups(root)

        self.assertEqual(
            [item["id"] for item in discovered],
            ["restore-20260826-130000-deadbeef", "20260825-120000"],
        )
        self.assertEqual(discovered[0]["source"], "pre-restore")
        self.assertEqual(discovered[1]["source"], "installer")
        self.assertNotIn("path", discovered[0])

    def test_read_rejects_traversal_and_oversized_configuration(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            oversized = self.write_backup(root, "20260825-120000", {})
            (oversized / "config.json").write_bytes(
                b" " * (backup_store.MAX_BACKUP_BYTES + 1)
            )

            with self.assertRaisesRegex(ValueError, "identifier"):
                backup_store.read_config_backup(root, "../20260825-120000")
            with self.assertRaisesRegex(ValueError, "too large"):
                backup_store.read_config_backup(root, "20260825-120000")

    def test_discovery_ignores_symlinked_configuration(self):
        if not hasattr(os, "symlink"):
            self.skipTest("symlinks are unavailable")
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            outside = root / "outside.json"
            outside.write_text('{"configVersion": 1}', encoding="utf-8")
            directory = root / "20260825-120000"
            directory.mkdir()
            try:
                os.symlink(outside, directory / "config.json")
            except OSError as exc:
                self.skipTest(f"symlink creation is unavailable: {exc}")

            self.assertEqual(backup_store.discover_config_backups(root), [])
            with self.assertRaisesRegex(ValueError, "unsafe"):
                backup_store.read_config_backup(root, "20260825-120000")

    def test_pre_restore_snapshot_round_trips_with_private_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir) / "backups"
            data = {"configVersion": 1, "title": "Before restore"}

            metadata = backup_store.create_pre_restore_backup(
                root,
                data,
                now=datetime(2026, 8, 26, 14, 30, 15),
                token="0123abcd",
            )

            self.assertEqual(
                metadata["id"],
                "restore-20260826-143015-0123abcd",
            )
            self.assertEqual(
                backup_store.read_config_backup(root, metadata["id"]),
                data,
            )
            if os.name == "posix":
                directory = root / metadata["id"]
                self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
                self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
                self.assertEqual(
                    stat.S_IMODE((directory / "config.json").stat().st_mode),
                    0o600,
                )


if __name__ == "__main__":
    unittest.main()
