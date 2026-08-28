import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import update_manager


class VersionTests(unittest.TestCase):
    def test_read_version_preserves_content_and_missing_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "version"
            self.assertEqual(update_manager.read_version(path), "0.0.0")

            path.write_text("0.4.0\n", encoding="utf-8")
            self.assertEqual(update_manager.read_version(path), "0.4.0")

    def test_semver_comparison_is_numeric_and_strict(self):
        self.assertTrue(update_manager.version_is_newer("0.10.0", "0.9.9"))
        self.assertFalse(update_manager.version_is_newer("0.3.4", "0.3.4"))
        self.assertIsNone(update_manager.parse_semver("v0.4.0"))
        self.assertIsNone(update_manager.parse_semver("0.4"))


class UpdateDiscoveryTests(unittest.TestCase):
    def test_complete_stable_release_is_preferred(self):
        release = {
            "tag_name": "v0.4.0",
            "draft": False,
            "prerelease": False,
            "assets": [
                {"name": "cozy-kids-launcher-0.4.0.tar.gz"},
                {"name": "SHA256SUMS"},
            ],
        }
        fetch_json = mock.Mock(return_value=release)
        fetch_text = mock.Mock()

        status = update_manager.resolve_update_status(
            "0.3.4",
            "https://example.test/releases/latest",
            "https://example.test/main/VERSION",
            "/missing/channel",
            timeout=3,
            fetch_json=fetch_json,
            fetch_text=fetch_text,
        )

        self.assertEqual(
            status,
            {
                "installedVersion": "0.3.4",
                "latestVersion": "0.4.0",
                "source": "release",
                "tag": "v0.4.0",
                "updateAvailable": True,
            },
        )
        fetch_json.assert_called_once_with(
            "https://example.test/releases/latest",
            timeout=3,
        )
        fetch_text.assert_not_called()

    def test_network_failure_uses_legacy_main_for_legacy_installations(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            status = update_manager.resolve_update_status(
                "0.3.4",
                "release-url",
                "legacy-url",
                str(Path(temp_dir) / "channel"),
                fetch_json=mock.Mock(side_effect=OSError("offline")),
                fetch_text=mock.Mock(return_value="0.3.5"),
            )

        self.assertEqual(status["source"], "legacy-main")
        self.assertTrue(status["updateAvailable"])

    def test_invalid_release_metadata_does_not_downgrade_to_legacy(self):
        fetch_text = mock.Mock()
        with self.assertRaisesRegex(RuntimeError, "invalid release metadata"):
            update_manager.resolve_update_status(
                "0.3.4",
                "release-url",
                "legacy-url",
                "/missing/channel",
                fetch_json=mock.Mock(
                    return_value={
                        "tag_name": "v0.4.0",
                        "assets": [],
                    }
                ),
                fetch_text=fetch_text,
            )
        fetch_text.assert_not_called()

    def test_release_channel_fails_closed_when_release_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            channel = Path(temp_dir) / "channel"
            channel.write_text("release\n", encoding="utf-8")
            fetch_text = mock.Mock()

            with self.assertRaisesRegex(RuntimeError, "Update check failed"):
                update_manager.resolve_update_status(
                    "0.4.0",
                    "release-url",
                    "legacy-url",
                    channel,
                    fetch_json=mock.Mock(side_effect=OSError("offline")),
                    fetch_text=fetch_text,
                )
        fetch_text.assert_not_called()


class UpdateTriggerTests(unittest.TestCase):
    def test_trigger_delegates_to_the_installed_updater(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir) / "app root"
            app_root.mkdir()
            updater = app_root / "update script.sh"
            updater.write_text("#!/usr/bin/env bash\n", encoding="utf-8")

            with mock.patch.object(update_manager.os, "chmod") as chmod:
                trigger = Path(
                    update_manager.write_update_trigger(app_root, updater)
                )

            self.assertEqual(
                trigger.read_text(encoding="utf-8"),
                "#!/usr/bin/env bash\n"
                "set -euo pipefail\n"
                f"exec bash '{updater}'\n",
            )
            chmod.assert_called_once_with(str(trigger), 0o755)

    def test_missing_updater_is_reported_without_creating_a_trigger(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app_root = Path(temp_dir)
            with self.assertRaisesRegex(
                update_manager.MissingUpdaterError,
                "Installed updater is missing",
            ):
                update_manager.write_update_trigger(
                    app_root,
                    app_root / "missing-update.sh",
                )
            self.assertFalse((app_root / "update-trigger.sh").exists())
