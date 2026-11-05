import fcntl
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import package_session
import service_control


class PackageSessionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.home = Path(self.temporary.name) / "family"
        self.root = Path(self.temporary.name) / "system"
        self.root.mkdir()
        self.session = package_session.PackageSession(self.home, self.root, {"LANG": "es_ES.UTF-8"})
        self.write(self.root / "default-config.json", json.dumps({"language": "en", "profiles": [{"title": "Kids", "tiles": [{"label": ""} for _ in range(4)]}]}))
        self.write(self.root / "cozy-kids-launcher.desktop", "[Desktop Entry]\nExec=/usr/bin/cozy-kids-launcher\nTryExec=/usr/bin/cozy-kids-launcher\n")
        self.write(self.root / "cozy-kids-launcher.service", "[Service]\nExecStart=/usr/bin/cozy-kids-launcher --service-run\n")

    def write(self, path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def legacy(self):
        self.write(self.session.legacy / "server.py", "# previous runtime\n")
        self.command = self.write(self.home / ".local/bin/cozy-kids-launcher", "#!/bin/sh\necho old\n")
        self.command.chmod(0o750)
        self.write(self.session.config, '{"pinHash":"preserve","profiles":[],"unknown":"retain"}\n')
        self.private = self.write(self.home / ".local/state/cozy-kids-launcher/retro-saves/child/game/saved.srm", "private save")

    def test_first_start_is_localized_private_and_never_overwrites_existing_config(self):
        self.session.first_start()
        config = json.loads(self.session.config.read_text())
        self.assertEqual(config["language"], "es")
        self.assertEqual(config["parentLabel"], package_session.load_translations("es")["parent_label"])
        self.assertEqual(self.session.config.stat().st_mode & 0o777, 0o600)
        self.session.config.write_text("malformed existing config", encoding="utf-8")
        self.session.first_start()
        self.assertEqual(self.session.config.read_text(), "malformed existing config")
        self.assertEqual(package_session.PackageSession(self.home, self.root, {"LANG": "zz"}).language(), "en")

    def test_script_install_requires_explicit_migration(self):
        self.legacy()
        with self.assertRaisesRegex(ValueError, "migrate-script-install"):
            self.session.first_start()
        self.assertFalse(self.session.migration_file.exists())

    def test_migration_and_restore_preserve_family_state_and_entry_modes(self):
        self.legacy()
        original = self.session.config.read_bytes()
        autostart = self.write(self.home / ".config/autostart/cozy-kids-launcher-autostart.desktop", "old login entry\n")
        backup = Path(self.session.migrate())
        self.assertTrue(backup.is_dir())
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.command.read_text(), package_session.WRAPPER)
        self.assertIn("--autostart", autostart.read_text())
        self.assertIn("TryExec=/usr/bin", autostart.read_text())
        self.assertTrue((self.session.legacy / "package-managed").is_file())
        self.session.first_start()
        self.assertEqual(self.session.migrate(), str(backup))
        self.assertEqual(self.session.config.read_bytes(), original)
        self.assertEqual(self.private.read_text(), "private save")
        self.session.restore()
        self.assertEqual(self.command.read_text(), "#!/bin/sh\necho old\n")
        self.assertEqual(self.command.stat().st_mode & 0o777, 0o750)
        self.assertEqual(autostart.read_text(), "old login entry\n")
        self.assertFalse((self.session.legacy / "package-managed").exists())
        self.assertFalse(self.session.migration_file.exists())

    def test_active_launcher_pending_update_links_and_custom_service_prevent_migration(self):
        self.legacy()
        with self.session.idle():
            with self.assertRaisesRegex(ValueError, "running launcher"):
                self.session.migrate()
        trigger = self.write(self.session.legacy / "update-trigger.sh", "pending")
        with self.assertRaisesRegex(ValueError, "pending"):
            self.session.migrate()
        trigger.unlink()
        self.command.unlink()
        self.command.symlink_to(self.root / "cozy-kids-launcher.desktop")
        with self.assertRaisesRegex(ValueError, "Linked"):
            self.session.migrate()
        self.command.unlink()
        self.write(self.session.legacy / "cozy-kids-launcher.service", "standard")
        self.write(self.home / ".config/systemd/user/cozy-kids-launcher.service", "custom")
        with self.assertRaisesRegex(ValueError, "customized"):
            self.session.migrate()
        self.assertFalse(self.session.migration_file.exists())

    def test_modified_entry_blocks_restore_before_any_entry_changes(self):
        self.legacy()
        self.session.migrate()
        self.command.write_text("customized after migration", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed"):
            self.session.restore()
        self.assertTrue((self.session.legacy / "package-managed").is_file())
        self.assertTrue(self.session.migration_file.exists())

    def test_interrupted_migration_rolls_back_without_losing_the_backup(self):
        self.legacy()
        real_write = package_session.atomic_text
        def fail_entry(path, text, mode=0o600):
            if path == self.command and text == package_session.WRAPPER:
                raise OSError("disk full")
            return real_write(path, text, mode)
        with patch.object(package_session, "atomic_text", side_effect=fail_entry):
            with self.assertRaisesRegex(OSError, "disk full"):
                self.session.migrate()
        self.assertEqual(self.command.read_text(), "#!/bin/sh\necho old\n")
        self.assertFalse(self.session.migration_file.exists())
        self.assertEqual(len(list((self.home / ".local/share/cozy-kids-launcher-backups").iterdir())), 1)

    def test_package_service_reads_the_system_template(self):
        self.write(self.root / "package-managed", "system")
        with patch.object(service_control, "__file__", str(self.root / "service_control.py")):
            service = service_control.UserService(self.home, {})
        self.assertEqual(service.app_root, self.root)
        self.assertIn("/usr/bin/cozy-kids-launcher", service.template())


if __name__ == "__main__":
    unittest.main()
