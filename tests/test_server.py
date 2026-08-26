import copy
import json
import sys
import tempfile
import threading
import types
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


def load_server_template():
    source = (REPOSITORY_ROOT / "src" / "server.py").read_text(encoding="utf-8")
    source = source.replace("{{APP_ID}}", "cozy-kids-launcher-test")
    source = source.replace("{{DEFAULT_PORT}}", "0")
    module = types.ModuleType("cozy_server_test")
    module.__file__ = str(REPOSITORY_ROOT / "src" / "server.py")
    exec(compile(source, module.__file__, "exec"), module.__dict__)
    return module


server_module = load_server_template()


def base_config(pin_hash=""):
    return {
        "configVersion": 1,
        "language": "en",
        "title": "Hello Kiddo",
        "theme": "rosa",
        "layoutMode": "gross",
        "parentLabel": "Parent",
        "exitLabel": "Exit kids mode",
        "shutdownLabel": "Shut down",
        "pinHash": pin_hash,
        "currentPage": 0,
        "autoScanDone": True,
        "timerMinutes": 0,
        "timerWarningMinutes": 5,
        "tiles": [
            {
                "id": "paint",
                "label": "Paint",
                "emoji": "🎨",
                "cmd": ["tuxpaint"],
                "visible": True,
            }
        ],
    }


class ServerLifecycleTests(unittest.TestCase):
    def test_main_refuses_a_second_owned_server_instance(self):
        with mock.patch.object(server_module, "configure_runtime_logging"), \
                mock.patch.object(server_module, "owned_process_alive", return_value=True), \
                mock.patch.object(server_module, "create_server") as create_server, \
                mock.patch.object(server_module, "log_runtime_event") as log_event, \
                mock.patch.object(server_module, "close_runtime_logging") as close_logging:
            server_module.main()

        create_server.assert_not_called()
        log_event.assert_called_once_with("server.duplicate", level="warning")
        close_logging.assert_called_once_with()


class ConfigValidationTests(unittest.TestCase):
    def test_legacy_config_is_upgraded_to_the_current_schema(self):
        legacy = base_config("0123456789abcdef")
        legacy.pop("configVersion")
        legacy["futureCompatibleKey"] = {"kept": True}

        migrated, changed = server_module.migrate_config(legacy)

        self.assertTrue(changed)
        self.assertEqual(
            migrated["configVersion"],
            server_module.CURRENT_CONFIG_VERSION,
        )
        self.assertEqual(migrated["futureCompatibleKey"], {"kept": True})
        self.assertEqual(migrated["pinHash"], "0123456789abcdef")

    def test_current_config_does_not_report_a_migration(self):
        migrated, changed = server_module.migrate_config(base_config())
        self.assertFalse(changed)
        self.assertEqual(migrated["configVersion"], 1)

    def test_future_config_version_is_rejected(self):
        data = base_config()
        data["configVersion"] = server_module.CURRENT_CONFIG_VERSION + 1
        with self.assertRaisesRegex(ValueError, "newer than supported"):
            server_module.validate_config(data)

    def test_invalid_config_version_is_rejected(self):
        for value in (True, -1, "1"):
            with self.subTest(value=value):
                data = base_config()
                data["configVersion"] = value
                with self.assertRaisesRegex(ValueError, "configVersion"):
                    server_module.validate_config(data)

    def test_loading_legacy_config_persists_the_schema_version_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = Path(temp_dir) / "config.json"
            legacy = base_config()
            legacy.pop("configVersion")
            config_path.write_text(
                json.dumps(legacy, ensure_ascii=False),
                encoding="utf-8",
            )

            with mock.patch.object(server_module, "CFG", str(config_path)):
                loaded = server_module.load_cfg()

            persisted = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(loaded["configVersion"], 1)
            self.assertEqual(persisted["configVersion"], 1)
            self.assertFalse(
                list(config_path.parent.glob("config-*.json")),
                "Atomic migration must not leave a temporary config behind",
            )

    def test_public_config_does_not_expose_pin_hash(self):
        public = server_module.public_config(base_config("0123456789abcdef"))
        self.assertNotIn("pinHash", public)
        self.assertTrue(public["pinConfigured"])

    def test_save_validation_preserves_existing_pin_hash(self):
        data = base_config()
        data["pinHash"] = "attacker-controlled"
        data["pinConfigured"] = False
        validated = server_module.validate_config(
            data,
            existing_pin_hash="0123456789abcdef",
        )
        self.assertEqual(validated["pinHash"], "0123456789abcdef")
        self.assertNotIn("pinConfigured", validated)

    def test_duplicate_tile_ids_are_rejected(self):
        data = base_config()
        data["tiles"].append(copy.deepcopy(data["tiles"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate tile id"):
            server_module.validate_config(data)

    def test_invalid_browser_name_is_rejected(self):
        data = base_config()
        data["browser"] = "firefox; touch /tmp/oops"
        with self.assertRaisesRegex(ValueError, "browser"):
            server_module.validate_config(data)


class PinTests(unittest.TestCase):
    def test_pbkdf2_pin_round_trip(self):
        pin_hash = server_module.hash_pin("1234", salt="00" * 16)
        self.assertTrue(server_module.verify_pin(pin_hash, "1234"))
        self.assertFalse(server_module.verify_pin(pin_hash, "9999"))

    def test_legacy_pin_hash_remains_supported(self):
        legacy = server_module.hashlib.sha256(b"1234").hexdigest()[:16]
        self.assertTrue(server_module.verify_pin(legacy, "1234"))
        self.assertFalse(server_module.verify_pin(legacy, "5678"))


class LaunchActionTests(unittest.TestCase):
    def test_obsolete_web_targets_are_migrated(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config_path = str(Path(temp_dir) / "config.json")
            config = base_config()
            config["tiles"][0]["cmd"] = ["special:browser:https://www.tivi.de"]
            with mock.patch.object(server_module, "CFG", config_path):
                server_module.save_cfg(config)
                migrated = server_module.load_cfg()
            self.assertEqual(
                migrated["tiles"][0]["cmd"],
                ["special:external-browser:https://www.zdf.de/kinder"],
            )

    def test_legacy_tile_commands_share_one_action_model(self):
        self.assertEqual(
            server_module.resolve_tile_action({"cmd": ["special:filme-musik"]}),
            {"type": "media"},
        )
        self.assertEqual(
            server_module.resolve_tile_action({"cmd": ["special:browser:https://example.com/kids"]}),
            {"type": "web", "mode": "embedded", "url": "https://example.com/kids"},
        )
        self.assertEqual(
            server_module.resolve_tile_action({"cmd": ["special:external-browser:https://example.com/kids"]}),
            {"type": "web", "mode": "external", "url": "https://example.com/kids"},
        )
        self.assertEqual(
            server_module.resolve_tile_action({"cmd": ["xdg-open", "https://example.com/kids"]}),
            {"type": "web", "mode": "external", "url": "https://example.com/kids"},
        )

    def test_app_command_is_split_without_a_shell(self):
        action = server_module.resolve_tile_action({"cmd": ['paint-app --title "Kids mode"']})
        self.assertEqual(action, {
            "type": "app",
            "argv": ["paint-app", "--title", "Kids mode"],
        })

    def test_kde_wrapper_is_removed_before_process_supervision(self):
        self.assertEqual(
            server_module.direct_app_command(
                ["kstart", "--fullscreen", "kturtle", "--demo"]
            ),
            ["kturtle", "--demo"],
        )

    def test_invalid_special_web_url_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Invalid browser URL"):
            server_module.resolve_tile_action({"cmd": ["special:browser:file:///etc/passwd"]})

    def test_configured_browser_is_preferred(self):
        with mock.patch.object(
            server_module.shutil,
            "which",
            side_effect=lambda name: f"/usr/bin/{name}" if name in ("google-chrome", "firefox") else None,
        ):
            self.assertEqual(
                server_module.find_browser({"browser": "google-chrome"}),
                "google-chrome",
            )

    def test_external_chromium_uses_a_dedicated_profile(self):
        command = server_module.external_browser_command(
            "google-chrome",
            "https://example.com/kids",
        )
        self.assertEqual(command[0], "google-chrome")
        self.assertTrue(any(arg.startswith("--user-data-dir=") for arg in command))
        self.assertIn("--kiosk", command)
        self.assertIn("--app=https://example.com/kids", command)

    def test_vlc_media_command_contains_all_media_locations(self):
        command = server_module.media_player_command(
            "vlc",
            ["/home/kid/Videos", "/home/kid/Music"],
        )
        self.assertEqual(command[0], "vlc")
        self.assertIn("--fullscreen", command)
        self.assertEqual(command[-2:], ["/home/kid/Videos", "/home/kid/Music"])


class RecommendationTests(unittest.TestCase):
    def test_public_web_recommendations_use_external_mode(self):
        recommendations = json.loads(
            (REPOSITORY_ROOT / "src" / "recommendations.json").read_text(encoding="utf-8")
        )
        web_recommendations = [
            recommendation for recommendation in recommendations
            if recommendation.get("category") == "browser"
        ]
        self.assertEqual(len(web_recommendations), 7)
        for recommendation in web_recommendations:
            action = server_module.resolve_tile_action(recommendation)
            self.assertEqual(action["type"], "web", recommendation["id"])
            self.assertEqual(action["mode"], "external", recommendation["id"])

    def test_obsolete_web_urls_are_not_recommended(self):
        source = (REPOSITORY_ROOT / "src" / "recommendations.json").read_text(encoding="utf-8")
        self.assertNotIn("netflix.com/browse/kids", source)
        self.assertNotIn("https://www.tivi.de", source)


class UpdateStatusTests(unittest.TestCase):
    def test_semver_comparison_is_numeric_and_strict(self):
        self.assertTrue(server_module.version_is_newer("0.10.0", "0.9.9"))
        self.assertFalse(server_module.version_is_newer("0.3.4", "0.3.4"))
        self.assertIsNone(server_module.parse_semver("v0.4.0"))
        self.assertIsNone(server_module.parse_semver("0.4"))

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
        with mock.patch.object(server_module, "get_version", return_value="0.3.4"), \
                mock.patch.object(server_module, "_fetch_remote_json", return_value=release), \
                mock.patch.object(server_module, "_fetch_remote_text") as legacy_fetch:
            status = server_module.get_update_status()
        self.assertEqual(status["source"], "release")
        self.assertEqual(status["latestVersion"], "0.4.0")
        self.assertTrue(status["updateAvailable"])
        legacy_fetch.assert_not_called()

    def test_legacy_version_remains_a_compatibility_fallback(self):
        with tempfile.TemporaryDirectory() as temp_dir, \
                mock.patch.object(server_module, "UPDATE_CHANNEL_FILE", str(Path(temp_dir) / "channel")), \
                mock.patch.object(server_module, "get_version", return_value="0.3.4"), \
                mock.patch.object(server_module, "_fetch_remote_json", side_effect=OSError("offline")), \
                mock.patch.object(server_module, "_fetch_remote_text", return_value="0.3.5"):
            status = server_module.get_update_status()
        self.assertEqual(status["source"], "legacy-main")
        self.assertTrue(status["updateAvailable"])

    def test_incomplete_release_is_not_treated_as_a_legacy_update(self):
        incomplete = {
            "tag_name": "v0.4.0",
            "draft": False,
            "prerelease": False,
            "assets": [],
        }
        with mock.patch.object(server_module, "get_version", return_value="0.3.4"), \
                mock.patch.object(server_module, "_fetch_remote_json", return_value=incomplete), \
                mock.patch.object(server_module, "_fetch_remote_text") as legacy_fetch:
            with self.assertRaisesRegex(RuntimeError, "invalid release metadata"):
                server_module.get_update_status()
        legacy_fetch.assert_not_called()

    def test_release_channel_fails_closed_when_release_discovery_breaks(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            channel_file = Path(temp_dir) / "channel"
            channel_file.write_text("release\n", encoding="utf-8")
            with mock.patch.object(server_module, "UPDATE_CHANNEL_FILE", str(channel_file)), \
                    mock.patch.object(server_module, "get_version", return_value="0.4.0"), \
                    mock.patch.object(server_module, "_fetch_remote_json", side_effect=OSError("offline")), \
                    mock.patch.object(server_module, "_fetch_remote_text") as legacy_fetch:
                with self.assertRaisesRegex(RuntimeError, "Update check failed"):
                    server_module.get_update_status()
            legacy_fetch.assert_not_called()


class ServerApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        app_root = root / "app"
        config_dir = root / "config"
        cache_dir = root / "cache"
        app_root.mkdir()
        config_dir.mkdir()
        cache_dir.mkdir()
        (app_root / "index.html").write_text("<!doctype html><title>test</title>", encoding="utf-8")
        (app_root / "recommendations.json").write_text("[]", encoding="utf-8")

        server_module.APP_ROOT = str(app_root)
        server_module.CFG = str(config_dir / "config.json")
        server_module.VERSION_FILE = str(app_root / "version")
        server_module.UPDATE_SCRIPT = str(app_root / "update.sh")
        server_module.UPDATE_CHANNEL_FILE = str(app_root / "update-channel")
        server_module.RECOMMENDATIONS_FILE = str(app_root / "recommendations.json")
        server_module.BACKUP_ROOT = str(root / "backups")
        server_module.LOG_FILE = str(root / "state" / "runtime.jsonl")
        server_module.TIMER_FILE = str(cache_dir / "timer.json")
        server_module.PIDFILE = str(cache_dir / "server.pid")
        server_module.BROWSER_PIDFILE = str(cache_dir / "browser.pid")
        server_module.TILE_PROCESS_PIDFILE = str(cache_dir / "tile-process.pid")
        server_module.OVERLAY_PIDFILE = str(cache_dir / "overlay.pid")
        server_module.PROCESS_SUPERVISOR = str(app_root / "process_supervisor.py")
        server_module.OVERLAY_SCRIPT = str(app_root / "overlay.py")
        server_module.EXIT_FLAGFILE = str(cache_dir / "exit-requested")
        server_module.clear_admin_sessions()
        server_module.clear_pin_failures()
        server_module.Handler.log_message = lambda *args, **kwargs: None

        server_module.save_cfg(base_config())
        self.httpd = server_module.create_server(port=0)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()
        self.port = self.httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{self.port}"

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)
        self.temp_dir.cleanup()

    def request(self, path, method="GET", body=None, cookie=None, origin=None):
        headers = {}
        payload = None
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        if cookie:
            headers["Cookie"] = cookie
        if origin:
            headers["Origin"] = origin
        request = urllib.request.Request(
            self.base_url + path,
            data=payload,
            headers=headers,
            method=method,
        )
        try:
            response = urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        raw = response.read()
        parsed = json.loads(raw.decode("utf-8")) if raw else None
        return response.status, parsed, response.headers

    def enable_pin(self, pin="1234"):
        config = base_config(server_module.hash_pin(pin, salt="11" * 16))
        server_module.save_cfg(config)

    def authenticate(self, pin="1234"):
        status, data, headers = self.request(
            "/api/verify-pin",
            method="POST",
            body={"pin": pin},
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["valid"])
        return headers["Set-Cookie"].split(";", 1)[0]

    def write_backup(self, backup_id, config):
        directory = Path(server_module.BACKUP_ROOT) / backup_id
        directory.mkdir(parents=True)
        (directory / "config.json").write_text(
            json.dumps(config),
            encoding="utf-8",
        )
        return directory

    def test_config_endpoint_hides_hash_and_sends_security_headers(self):
        self.enable_pin()
        status, data, headers = self.request("/api/config")
        self.assertEqual(status, 200)
        self.assertTrue(data["pinConfigured"])
        self.assertNotIn("pinHash", data)
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")

    def test_update_status_comes_from_the_local_release_resolver(self):
        expected = {
            "installedVersion": "0.3.4",
            "latestVersion": "0.4.0",
            "source": "release",
            "updateAvailable": True,
        }
        with mock.patch.object(server_module, "get_update_status", return_value=expected):
            status, data, _ = self.request("/api/update/status")
        self.assertEqual(status, 200)
        self.assertEqual(data, expected)

    def test_update_request_only_writes_a_single_launcher_trigger(self):
        update_script = Path(server_module.UPDATE_SCRIPT)
        update_script.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
        with mock.patch.object(server_module.subprocess, "Popen") as popen:
            status, data, _ = self.request(
                "/api/update",
                method="POST",
                origin=self.base_url,
            )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "triggered")
        trigger = Path(server_module.APP_ROOT) / "update-trigger.sh"
        self.assertIn(str(update_script), trigger.read_text(encoding="utf-8"))
        popen.assert_not_called()

    def test_diagnostics_require_parent_access_and_exclude_family_values(self):
        self.enable_pin()
        status, _, _ = self.request("/api/diagnostics")
        self.assertEqual(status, 403)

        cookie = self.authenticate()
        logger = server_module.configure_runtime_logging(server_module.LOG_FILE)
        try:
            server_module.log_runtime_event(
                "server.started",
                version="0.5.0",
            )
        finally:
            server_module.close_runtime_logging()
        status, data, headers = self.request(
            "/api/diagnostics",
            cookie=cookie,
        )

        serialized = json.dumps(data)
        config = server_module.load_cfg()
        self.assertEqual(status, 200)
        self.assertIn("cozy-kids-diagnostics.json", headers["Content-Disposition"])
        self.assertEqual(data["configuration"]["schemaVersion"], 1)
        self.assertIn("server.started", serialized)
        self.assertNotIn(config["title"], serialized)
        self.assertNotIn(config["tiles"][0]["label"], serialized)
        self.assertNotIn(config["tiles"][0]["cmd"][0], serialized)
        self.assertNotIn(config["pinHash"], serialized)
        self.assertNotIn(str(self.temp_dir.name), serialized)

    def test_parent_actions_require_authenticated_session(self):
        self.enable_pin()
        status, _, _ = self.request("/api/backups")
        self.assertEqual(status, 403)
        for path, body in (
            ("/api/save-config", base_config()),
            ("/api/import-config", base_config()),
            ("/api/backups/restore", {"backupId": "20260825-120000"}),
            ("/api/update", None),
            ("/shutdown", None),
        ):
            status, _, _ = self.request(
                path,
                method="POST",
                body=body,
                origin=self.base_url,
            )
            self.assertEqual(status, 403, path)

    def test_backup_restore_preserves_pin_and_creates_safety_snapshot(self):
        self.enable_pin("1234")
        current = server_module.load_cfg()
        current["title"] = "Current family settings"
        server_module.save_cfg(current)
        backup = base_config(server_module.hash_pin("5678", salt="22" * 16))
        backup["title"] = "Restored family settings"
        backup["browser"] = "firefox"
        self.write_backup("20260825-120000", backup)
        cookie = self.authenticate("1234")

        status, listing, _ = self.request("/api/backups", cookie=cookie)
        serialized = json.dumps(listing)
        self.assertEqual(status, 200)
        self.assertEqual(listing["backups"][0]["id"], "20260825-120000")
        self.assertNotIn("Restored family settings", serialized)
        self.assertNotIn("pinHash", serialized)
        self.assertNotIn(self.temp_dir.name, serialized)

        status, result, _ = self.request(
            "/api/backups/restore",
            method="POST",
            body={"backupId": "20260825-120000"},
            cookie=cookie,
            origin=self.base_url,
        )

        self.assertEqual(status, 200)
        self.assertEqual(result["status"], "ok")
        restored = server_module.load_cfg()
        self.assertEqual(restored["title"], "Restored family settings")
        self.assertTrue(server_module.verify_pin(restored["pinHash"], "1234"))
        self.assertFalse(server_module.verify_pin(restored["pinHash"], "5678"))
        browser_override = Path(server_module.CFG).parent / "browser"
        self.assertEqual(browser_override.read_text(encoding="utf-8"), "firefox")

        safety_id = result["safetyBackupId"]
        safety = server_module.read_config_backup(
            server_module.BACKUP_ROOT,
            safety_id,
        )
        self.assertEqual(safety["title"], "Current family settings")
        self.assertTrue(server_module.verify_pin(safety["pinHash"], "1234"))
        status, updated_listing, _ = self.request("/api/backups", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertIn(
            "pre-restore",
            {item["source"] for item in updated_listing["backups"]},
        )

    def test_backup_restore_rejects_traversal_without_changing_config(self):
        original = server_module.load_cfg()
        status, data, _ = self.request(
            "/api/backups/restore",
            method="POST",
            body={"backupId": "../20260825-120000"},
            origin=self.base_url,
        )
        self.assertEqual(status, 400)
        self.assertEqual(data["status"], "error")
        self.assertEqual(server_module.load_cfg(), original)

    def test_backup_list_filters_corrupt_and_future_schema_configs(self):
        self.write_backup("20260825-120000", {"configVersion": 999})
        directory = Path(server_module.BACKUP_ROOT) / "20260826-120000"
        directory.mkdir(parents=True)
        (directory / "config.json").write_text("not json", encoding="utf-8")

        status, data, _ = self.request("/api/backups")

        self.assertEqual(status, 200)
        self.assertEqual(data["backups"], [])

    def test_login_allows_save_without_overwriting_pin(self):
        self.enable_pin()
        cookie = self.authenticate()
        public = base_config()
        public["title"] = "Updated"
        public["pinHash"] = "attacker-controlled"
        public["pinConfigured"] = False
        status, data, _ = self.request(
            "/api/save-config",
            method="POST",
            body=public,
            cookie=cookie,
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        saved = server_module.load_cfg()
        self.assertEqual(saved["title"], "Updated")
        self.assertTrue(server_module.verify_pin(saved["pinHash"], "1234"))

    def test_successful_login_upgrades_legacy_pin_hash(self):
        legacy = server_module.hashlib.sha256(b"1234").hexdigest()[:16]
        server_module.save_cfg(base_config(legacy))
        self.authenticate()
        upgraded = server_module.load_cfg()["pinHash"]
        self.assertTrue(upgraded.startswith("pbkdf2_sha256$"))
        self.assertTrue(server_module.verify_pin(upgraded, "1234"))

    def test_cross_site_posts_are_rejected_even_without_pin(self):
        status, data, _ = self.request(
            "/api/save-config",
            method="POST",
            body=base_config(),
            origin="https://example.com",
        )
        self.assertEqual(status, 403)
        self.assertIn("Cross-site", data["message"])

    def test_invalid_import_is_rejected(self):
        status, data, _ = self.request(
            "/api/import-config",
            method="POST",
            body={"tiles": [{"id": "bad id", "cmd": []}]},
            origin=self.base_url,
        )
        self.assertEqual(status, 400)
        self.assertEqual(data["status"], "error")

    def test_setting_and_removing_pin_uses_server_side_hashing(self):
        status, data, headers = self.request(
            "/api/pin/set",
            method="POST",
            body={"pin": "2468"},
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertTrue(data["pinConfigured"])
        stored = server_module.load_cfg()["pinHash"]
        self.assertTrue(stored.startswith("pbkdf2_sha256$"))
        self.assertTrue(server_module.verify_pin(stored, "2468"))

        cookie = headers["Set-Cookie"].split(";", 1)[0]
        status, data, _ = self.request(
            "/api/pin/remove",
            method="POST",
            cookie=cookie,
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertFalse(data["pinConfigured"])
        self.assertEqual(server_module.load_cfg()["pinHash"], "")

    def test_pin_attempts_are_throttled_across_pin_protected_endpoints(self):
        self.enable_pin()
        for _ in range(server_module.PIN_FAILURE_LIMIT):
            status, _, _ = self.request(
                "/api/timer/extend",
                method="POST",
                body={"pin": "9999", "minutes": 15},
                origin=self.base_url,
            )
            self.assertEqual(status, 403)
        status, data, _ = self.request(
            "/api/verify-pin",
            method="POST",
            body={"pin": "1234"},
            origin=self.base_url,
        )
        self.assertEqual(status, 429)
        self.assertIn("Too many", data["message"])


class FrontendSafetyTests(unittest.TestCase):
    def test_tile_content_is_rendered_as_text(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        self.assertIn("tileLabel.textContent=tile.label||''", source)
        self.assertIn("tileEmoji.textContent=tile.emoji||'✨'", source)
        self.assertNotIn("btn.innerHTML=html", source)

    def test_every_tile_uses_the_same_launch_endpoint(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        launch_function = source[source.index("function launchTile"):source.index("// PIN handling")]
        self.assertIn("fetch('/launch/'", launch_function)
        self.assertNotIn("special:browser:", launch_function)
        self.assertNotIn("special:external-browser:", launch_function)

    def test_frontend_uses_the_local_update_status_endpoint(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        self.assertIn("fetch('/api/update/status'", source)
        self.assertNotIn("raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main/VERSION", source)

    def test_diagnostics_download_is_local_and_bilingual(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("fetch('/api/diagnostics')", source)
        self.assertIn("{{LABEL_EXPORT_DIAGNOSTICS}}", source)
        self.assertIn('de:export_diagnostics) echo "Diagnose herunterladen"', installer)
        self.assertIn('en:export_diagnostics) echo "Download diagnostics"', installer)

    def test_theme_and_browser_labels_follow_the_interface_language(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        self.assertIn("const THEME_LABELS=", source)
        self.assertIn("function interfaceLanguage()", source)
        self.assertIn("themeLabel(t.id)", source)
        self.assertIn("Changes take effect after the next login.", source)

    def test_browser_tile_fields_do_not_hide_their_mode_selector(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        self.assertIn("select.className='appSelect'", source)
        self.assertIn(".tileform.has-browser > .appSelect { display:none; }", source)
        self.assertNotIn(".tileform.has-browser select { display:none; }", source)

    def test_backup_restore_ui_uses_local_api_and_text_content(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        backup_functions = source[
            source.index("function backupLabel"):source.index("// Keyboard navigation")
        ]
        self.assertIn("fetch('/api/backups'", backup_functions)
        self.assertIn("fetch('/api/backups/restore'", backup_functions)
        self.assertIn("option.textContent=backupLabel(backup)", backup_functions)
        self.assertNotIn("innerHTML", backup_functions)
        self.assertIn('de:backup_title) echo "Sicherungen"', installer)
        self.assertIn('en:backup_title) echo "Backups"', installer)


if __name__ == "__main__":
    unittest.main()
