import copy
import hashlib
import json
import os
import sys
import tempfile
import threading
import time
import types
import unittest
import urllib.error
import urllib.request
from urllib.parse import parse_qs, urlparse
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import lifecycle_state
import activity_store


def frontend_source():
    frontend_root = REPOSITORY_ROOT / "src" / "frontend"
    paths = [
        REPOSITORY_ROOT / "src" / "index.html",
        frontend_root / "design-system.css",
        frontend_root / "state.js",
        frontend_root / "localization.js",
        frontend_root / "icons.js",
        frontend_root / "dialogs.js",
        frontend_root / "launcher-ui.js",
        frontend_root / "profiles.js",
        frontend_root / "schedule-controls.js",
        frontend_root / "activity-dashboard.js",
        frontend_root / "parent-settings.js",
        frontend_root / "first-run.js",
        frontend_root / "runtime-controls.js",
        frontend_root / "styles.css",
    ]
    return "\n".join(path.read_text(encoding="utf-8") for path in paths)


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
        "activityTrackingEnabled": False,
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
        current, _ = server_module.migrate_config(base_config())
        migrated, changed = server_module.migrate_config(current)
        self.assertFalse(changed)
        self.assertEqual(migrated["configVersion"], 2)

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
            self.assertEqual(loaded["configVersion"], 2)
            self.assertEqual(persisted["configVersion"], 2)
            self.assertEqual(persisted["activeProfileId"], "default")
            self.assertEqual(persisted["profiles"][0]["title"], "Hello Kiddo")
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
        legacy = hashlib.sha256(b"1234").hexdigest()[:16]
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
    def test_update_urls_share_the_updater_environment_overrides(self):
        with mock.patch.dict(
            os.environ,
            {
                "COZY_KIDS_RELEASE_API_URL": "http://127.0.0.1:8000/releases/latest",
                "COZY_KIDS_RAW_URL": "http://127.0.0.1:8000/raw/",
            },
        ):
            isolated_module = load_server_template()
        self.assertEqual(
            isolated_module.LATEST_RELEASE_API,
            "http://127.0.0.1:8000/releases/latest",
        )
        self.assertEqual(
            isolated_module.LEGACY_VERSION_URL,
            "http://127.0.0.1:8000/raw/VERSION",
        )

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
        videos = root / "Videos"
        music = root / "Music"
        alternate_music = root / "Musik"
        videos.mkdir()
        music.mkdir()
        alternate_music.mkdir()
        (app_root / "index.html").write_text("<!doctype html><title>test</title>", encoding="utf-8")
        (app_root / "browser.html").write_text(
            "<!doctype html><title>browser test</title>",
            encoding="utf-8",
        )
        (app_root / "recommendations.json").write_text("[]", encoding="utf-8")

        server_module.APP_ROOT = str(app_root)
        server_module.CFG = str(config_dir / "config.json")
        server_module.VERSION_FILE = str(app_root / "version")
        server_module.UPDATE_SCRIPT = str(app_root / "update.sh")
        server_module.UPDATE_CHANNEL_FILE = str(app_root / "update-channel")
        server_module.RECOMMENDATIONS_FILE = str(app_root / "recommendations.json")
        server_module.VIDEOS = str(videos)
        server_module.MUSIC = str(music)
        server_module.ALT_MUSIC = str(alternate_music)
        server_module.BACKUP_ROOT = str(root / "backups")
        server_module.LOG_FILE = str(root / "state" / "runtime.jsonl")
        server_module.ACTIVITY_FILE = str(root / "state" / "activity.json")
        server_module.TIMER_FILE = str(cache_dir / "timer.json")
        server_module.PIDFILE = str(cache_dir / "server.pid")
        server_module.BROWSER_PIDFILE = str(cache_dir / "browser.pid")
        server_module.TILE_PROCESS_PIDFILE = str(cache_dir / "tile-process.pid")
        server_module.OVERLAY_PIDFILE = str(cache_dir / "overlay.pid")
        server_module.PROCESS_SUPERVISOR = str(app_root / "process_supervisor.py")
        server_module.OVERLAY_SCRIPT = str(app_root / "overlay.py")
        server_module.EXIT_FLAGFILE = str(cache_dir / "exit-requested")
        server_module.LIFECYCLE_STATE_FILE = str(cache_dir / "lifecycle.json")
        server_module.LIFECYCLE_REQUEST_FILE = str(
            cache_dir / "lifecycle-request.json"
        )
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

    def test_media_catalog_returns_opaque_metadata_and_safe_cover_urls(self):
        media_file = Path(server_module.VIDEOS) / "My_Film.mp4"
        cover_file = Path(server_module.VIDEOS) / "My_Film.png"
        media_file.write_bytes(b"video")
        cover_file.write_bytes(b"cover-bytes")

        status, data, _ = self.request("/api/media")

        self.assertEqual(status, 200)
        self.assertFalse(data["truncated"])
        self.assertEqual(len(data["items"]), 1)
        item = data["items"][0]
        self.assertEqual(item["title"], "My Film")
        self.assertEqual(item["kind"], "video")
        self.assertRegex(item["id"], r"^[0-9a-f]{24}$")
        self.assertEqual(item["coverUrl"], f"/api/media/cover?id={item['id']}")
        self.assertNotIn(str(media_file), json.dumps(data))

        with urllib.request.urlopen(
            self.base_url + item["coverUrl"],
            timeout=5,
        ) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers["Content-Type"], "image/png")
            self.assertEqual(response.read(), b"cover-bytes")

    def test_media_cover_endpoint_rejects_unknown_or_ambiguous_identifiers(self):
        for path in (
            "/api/media/cover?id=unknown",
            "/api/media/cover?id=" + "a" * 24 + "&extra=1",
            "/api/media/cover",
        ):
            with self.subTest(path=path):
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(self.base_url + path, timeout=5)
                self.assertEqual(error.exception.code, 404)

    def test_media_cover_endpoint_rejects_oversized_images(self):
        (Path(server_module.VIDEOS) / "Film.mp4").write_bytes(b"video")
        (Path(server_module.VIDEOS) / "Film.jpg").write_bytes(b"large")
        _, data, _ = self.request("/api/media")

        with mock.patch.object(server_module, "MAX_MEDIA_COVER_BYTES", 4):
            with self.assertRaises(urllib.error.HTTPError) as error:
                urllib.request.urlopen(
                    self.base_url + data["items"][0]["coverUrl"],
                    timeout=5,
                )

        self.assertEqual(error.exception.code, 404)

    def test_app_discovery_endpoint_preserves_public_payload(self):
        expected = [{"name": "Paint", "exec": "paint-app --kids"}]
        with mock.patch.object(
            server_module,
            "discover_apps",
            return_value=expected,
        ) as discover_apps:
            status, data, _ = self.request("/api/apps")

        self.assertEqual(status, 200)
        self.assertEqual(data, expected)
        discover_apps.assert_called_once_with(server_module.HOME)

    def test_browser_endpoint_preserves_candidate_order_and_status(self):
        candidates = ("firefox", "chromium")
        with mock.patch.object(
            server_module,
            "BROWSER_CANDIDATES",
            candidates,
        ), mock.patch.object(
            server_module.shutil,
            "which",
            side_effect=lambda name: "/usr/bin/firefox"
            if name == "firefox"
            else None,
        ):
            status, data, _ = self.request("/api/browsers")

        self.assertEqual(status, 200)
        self.assertEqual(
            data,
            [
                {"name": "firefox", "installed": True},
                {"name": "chromium", "installed": False},
            ],
        )

    def test_app_launch_preserves_argv_and_uses_owned_supervision(self):
        config = server_module.load_cfg()
        config["activityTrackingEnabled"] = True
        server_module.save_cfg(config)
        with mock.patch.object(server_module, "launch_owned_tile") as launch:
            status, data, _ = self.request(
                "/launch/paint",
                method="POST",
                origin=self.base_url,
            )

        self.assertEqual(status, 204)
        self.assertIsNone(data)
        launch.assert_called_once_with(
            ["tuxpaint"],
            "local",
            tile_id="paint",
            profile_id="default",
            track_activity=True,
        )

    def test_activity_api_is_opt_in_parent_only_and_removable(self):
        self.enable_pin()
        status, _, _ = self.request("/api/activity")
        self.assertEqual(status, 403)
        status, _, _ = self.request("/api/activity/export")
        self.assertEqual(status, 403)
        cookie = self.authenticate()

        status, data, _ = self.request("/api/activity", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertFalse(data["enabled"])
        self.assertEqual(data["records"], [])

        config = server_module.load_cfg()
        config["activityTrackingEnabled"] = True
        server_module.save_cfg(config)
        now = int(time.time())
        activity_store.record_activity(
            server_module.ACTIVITY_FILE,
            "default",
            "paint",
            now - 45,
            ended_at=now,
        )

        status, data, _ = self.request("/api/activity", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertTrue(data["enabled"])
        self.assertEqual(data["recordCount"], 1)
        self.assertEqual(data["totalDurationSeconds"], 45)
        self.assertEqual(data["records"][0]["tileId"], "paint")
        self.assertEqual(data["profiles"][0]["name"], "Kiddo")
        self.assertEqual(data["profiles"][0]["tiles"][0]["label"], "Paint")
        self.assertNotIn("Paint", json.dumps(data["records"]))
        self.assertNotIn("tuxpaint", json.dumps(data))

        status, exported, headers = self.request(
            "/api/activity/export",
            cookie=cookie,
        )
        self.assertEqual(status, 200)
        self.assertEqual(exported["activityVersion"], 1)
        self.assertEqual(exported["records"][0]["durationSeconds"], 45)
        self.assertNotIn("profiles", exported)
        self.assertIn("cozy-kids-activity.json", headers["Content-Disposition"])

        status, result, _ = self.request(
            "/api/activity/clear",
            method="POST",
            body={},
            cookie=cookie,
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertEqual(result, {"status": "ok"})
        status, data, _ = self.request("/api/activity", cookie=cookie)
        self.assertEqual(status, 200)
        self.assertEqual(data["recordCount"], 0)

    def test_embedded_activity_uses_an_opaque_finish_token(self):
        config = server_module.load_cfg()
        config["activityTrackingEnabled"] = True
        config["tiles"][0]["cmd"] = ["special:browser:https://example.com/kids"]
        server_module.save_cfg(config)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, file_pointer, code, message, headers, url):
                return None

        request = urllib.request.Request(
            self.base_url + "/launch/paint",
            data=b"",
            headers={"Origin": self.base_url},
            method="POST",
        )
        try:
            response = urllib.request.build_opener(NoRedirect).open(request, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        self.assertEqual(response.status, 302)
        location = response.headers["Location"]
        response.close()
        query = parse_qs(urlparse(location).query)
        self.assertEqual(query["tile"], ["paint"])
        token = query["activity"][0]
        self.assertGreaterEqual(len(token), 16)

        status, data, _ = self.request(
            "/api/activity/finish",
            method="POST",
            body={"token": token},
            origin=self.base_url,
        )
        self.assertEqual(status, 204)
        self.assertIsNone(data)
        status, activity, _ = self.request("/api/activity")
        self.assertEqual(status, 200)
        self.assertEqual(activity["recordCount"], 1)
        self.assertEqual(activity["records"][0]["tileId"], "paint")

    def test_embedded_browser_wrapper_enforces_its_configured_exact_origins(self):
        config = server_module.load_cfg()
        config["tiles"][0]["cmd"] = ["special:browser:https://kids.example/start"]
        config["tiles"][0]["browserAllowedOrigins"] = [
            "https://media.example/videos",
            "https://kids.example/duplicate",
        ]
        server_module.save_cfg(config)

        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, request, file_pointer, code, message, headers, url):
                return None

        launch_request = urllib.request.Request(
            self.base_url + "/launch/paint",
            data=b"",
            headers={"Origin": self.base_url},
            method="POST",
        )
        try:
            launch_response = urllib.request.build_opener(NoRedirect).open(
                launch_request,
                timeout=5,
            )
        except urllib.error.HTTPError as error:
            launch_response = error
        self.assertEqual(launch_response.status, 302)
        location = launch_response.headers["Location"]
        launch_response.close()

        with urllib.request.urlopen(self.base_url + location, timeout=5) as response:
            self.assertEqual(response.status, 200)
            policy = response.headers["Content-Security-Policy"]
        self.assertIn(
            "frame-src https://kids.example https://media.example;",
            policy,
        )
        self.assertNotIn("*", policy)

        forged = (
            "/browser.html?url=https%3A%2F%2Fevil.example&tile=paint&activity="
        )
        try:
            urllib.request.urlopen(self.base_url + forged, timeout=5)
        except urllib.error.HTTPError as error:
            self.assertEqual(error.code, 404)
        else:
            self.fail("A forged browser wrapper target was accepted")

    def test_schedule_status_and_launch_enforcement_share_the_same_boundary(self):
        config = server_module.load_cfg()
        config["weeklySchedule"] = {"enabled": True, "days": {}}
        server_module.save_cfg(config)

        status, availability, _ = self.request("/api/availability/status")
        self.assertEqual(status, 200)
        self.assertEqual(
            availability,
            {"profileAllowed": False, "blockedTileIds": ["paint"]},
        )

        with mock.patch.object(server_module, "launch_owned_tile") as launch:
            status, data, _ = self.request(
                "/launch/paint",
                method="POST",
                origin=self.base_url,
            )

        self.assertEqual(status, 403)
        self.assertEqual(
            data,
            {"status": "blocked", "reason": "profile_schedule"},
        )
        launch.assert_not_called()

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

    def test_update_request_reports_a_missing_installed_updater(self):
        status, data, _ = self.request(
            "/api/update",
            method="POST",
            origin=self.base_url,
        )

        self.assertEqual(status, 503)
        self.assertEqual(
            data,
            {"status": "error", "message": "Installed updater is missing"},
        )
        self.assertFalse(
            (Path(server_module.APP_ROOT) / "update-trigger.sh").exists()
        )

    def test_timer_start_status_and_stop_contract(self):
        with mock.patch.object(server_module.time, "time", return_value=1000):
            status, data, _ = self.request(
                "/api/timer/start",
                method="POST",
                body={"minutes": 15},
                origin=self.base_url,
            )
            self.assertEqual(status, 200)
            self.assertEqual(
                data,
                {"valid": True, "endTime": 1900, "minutes": 15},
            )

            status, data, _ = self.request("/api/timer/status")
            self.assertEqual(status, 200)
            self.assertEqual(
                data,
                {
                    "active": True,
                    "expired": False,
                    "warning": False,
                    "remainingSeconds": 900,
                    "totalMinutes": 15,
                },
            )

            status, data, _ = self.request(
                "/api/timer/stop",
                method="POST",
                body={},
                origin=self.base_url,
            )
            self.assertEqual(status, 200)
            self.assertEqual(data, {"valid": True})

            status, data, _ = self.request("/api/timer/status")
            self.assertEqual(status, 200)
            self.assertEqual(
                data,
                {
                    "active": False,
                    "expired": False,
                    "warning": False,
                    "remainingSeconds": 0,
                    "totalMinutes": 0,
                },
            )

    def test_diagnostics_require_parent_access_and_exclude_family_values(self):
        self.enable_pin()
        status, _, _ = self.request("/api/diagnostics")
        self.assertEqual(status, 403)

        cookie = self.authenticate()
        lifecycle_state.begin_lifecycle(
            server_module.LIFECYCLE_STATE_FILE,
            "initial-start",
        )
        lifecycle_state.transition_lifecycle(
            server_module.LIFECYCLE_STATE_FILE,
            "running",
            "ready",
        )
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
        self.assertEqual(data["configuration"]["schemaVersion"], 2)
        self.assertEqual(
            data["lifecycle"],
            {"state": "running", "reason": "ready", "attempt": None},
        )
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
            ("/api/profiles/create", {"name": "Alex", "avatar": "🚀"}),
            ("/api/profiles/select", {"profileId": "default"}),
            ("/api/profiles/delete", {"profileId": "default"}),
            ("/api/activity/clear", {}),
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
        self.assertEqual(
            server_module.active_config(safety)["title"],
            "Current family settings",
        )
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
        self.assertEqual(data["config"]["title"], "Updated")
        self.assertNotIn("pinHash", data["config"])
        saved = server_module.load_cfg()
        self.assertEqual(saved["title"], "Updated")
        self.assertTrue(server_module.verify_pin(saved["pinHash"], "1234"))

    def test_profile_api_keeps_child_settings_separate_and_resets_runtime_timer(self):
        status, listing, _ = self.request("/api/profiles")
        self.assertEqual(status, 200)
        self.assertEqual(listing["activeProfileId"], "default")
        self.assertEqual(len(listing["profiles"]), 1)

        status, created, _ = self.request(
            "/api/profiles/create",
            method="POST",
            body={"name": "Alex", "avatar": "🚀"},
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        profile_id = created["profileId"]
        self.assertNotEqual(profile_id, "default")

        status, public, _ = self.request("/api/config")
        self.assertEqual(status, 200)
        self.assertEqual(len(public["profiles"]), 2)
        self.assertNotIn("tiles", public["profiles"][1])
        status, exported, _ = self.request("/api/export-config")
        self.assertEqual(status, 200)
        self.assertEqual(len(exported["profiles"]), 2)
        self.assertIn("tiles", exported["profiles"][1])

        server_module.save_timer({"end_time": 9999999999, "totalMinutes": 30})
        status, selected, _ = self.request(
            "/api/profiles/select",
            method="POST",
            body={"profileId": profile_id},
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertEqual(selected["config"]["activeProfileId"], profile_id)
        self.assertEqual(selected["config"]["name"], "Alex")
        self.assertFalse(Path(server_module.TIMER_FILE).exists())

        alex = selected["config"]
        alex["title"] = "Alex's space"
        alex["theme"] = "blau"
        alex["tiles"][0]["label"] = "Alex Paint"
        status, _, _ = self.request(
            "/api/save-config",
            method="POST",
            body=alex,
            origin=self.base_url,
        )
        self.assertEqual(status, 200)

        status, selected, _ = self.request(
            "/api/profiles/select",
            method="POST",
            body={"profileId": "default"},
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertEqual(selected["config"]["title"], "Hello Kiddo")
        self.assertEqual(selected["config"]["theme"], "rosa")
        self.assertEqual(selected["config"]["tiles"][0]["label"], "Paint")

        now = int(time.time())
        activity_store.record_activity(
            server_module.ACTIVITY_FILE,
            profile_id,
            "paint",
            now - 10,
            ended_at=now,
        )
        activity_store.record_activity(
            server_module.ACTIVITY_FILE,
            "default",
            "paint",
            now - 5,
            ended_at=now,
        )

        status, deleted, _ = self.request(
            "/api/profiles/delete",
            method="POST",
            body={"profileId": profile_id},
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(deleted["profiles"]), 1)
        self.assertEqual(
            [record["profileId"] for record in activity_store.read_activity(server_module.ACTIVITY_FILE)],
            ["default"],
        )

    def test_profile_api_rejects_deleting_the_active_profile(self):
        status, data, _ = self.request(
            "/api/profiles/delete",
            method="POST",
            body={"profileId": "default"},
            origin=self.base_url,
        )
        self.assertEqual(status, 400)
        self.assertIn("active profile", data["message"])

    def test_successful_login_upgrades_legacy_pin_hash(self):
        legacy = hashlib.sha256(b"1234").hexdigest()[:16]
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

    def test_shutdown_records_a_short_lived_lifecycle_intent(self):
        with mock.patch.object(
            server_module.shutil,
            "which",
            side_effect=lambda name: f"/fake/{name}" if name == "systemctl" else None,
        ), mock.patch.object(server_module.subprocess, "Popen") as popen:
            status, data, _ = self.request(
                "/shutdown",
                method="POST",
                origin=self.base_url,
            )

        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "ok")
        popen.assert_called_once_with(
            ["systemctl", "poweroff"],
            env=mock.ANY,
        )
        self.assertEqual(
            lifecycle_state.consume_lifecycle_request(
                server_module.LIFECYCLE_REQUEST_FILE
            ),
            "shutdown",
        )

    def test_failed_shutdown_does_not_leave_a_stale_intent(self):
        with mock.patch.object(server_module.shutil, "which", return_value=None):
            status, data, _ = self.request(
                "/shutdown",
                method="POST",
                origin=self.base_url,
            )

        self.assertEqual(status, 200)
        self.assertEqual(data["status"], "error")
        self.assertFalse(Path(server_module.LIFECYCLE_REQUEST_FILE).exists())

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

        set_cookie = headers["Set-Cookie"]
        self.assertTrue(set_cookie.startswith("cozy_admin="))
        self.assertTrue(
            set_cookie.endswith(
                "; Path=/; HttpOnly; SameSite=Strict; Max-Age=1800"
            )
        )
        cookie = set_cookie.split(";", 1)[0]
        status, data, headers = self.request(
            "/api/pin/remove",
            method="POST",
            cookie=cookie,
            origin=self.base_url,
        )
        self.assertEqual(status, 200)
        self.assertFalse(data["pinConfigured"])
        self.assertEqual(server_module.load_cfg()["pinHash"], "")
        self.assertEqual(
            headers["Set-Cookie"],
            "cozy_admin=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0",
        )

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
    def test_frontend_uses_focused_external_assets(self):
        source = (REPOSITORY_ROOT / "src" / "index.html").read_text(encoding="utf-8")
        expected_assets = (
            "/frontend/design-system.css",
            "/frontend/styles.css",
            "/frontend/state.js",
            "/frontend/localization.js",
            "/frontend/icons.js",
            "/frontend/dialogs.js",
            "/frontend/launcher-ui.js",
            "/frontend/profiles.js",
            "/frontend/schedule-controls.js",
            "/frontend/activity-dashboard.js",
            "/frontend/parent-settings.js",
            "/frontend/first-run.js",
            "/frontend/runtime-controls.js",
        )
        for asset in expected_assets:
            self.assertIn(asset, source)
        self.assertLess(
            source.index("/frontend/design-system.css"),
            source.index("/frontend/styles.css"),
        )
        self.assertNotIn("<style", source)
        self.assertNotRegex(source, r"<script(?![^>]*\bsrc=)[^>]*>")

        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        for asset in ("design-system.css", "styles.css", "state.js", "localization.js", "icons.js", "dialogs.js", "launcher-ui.js", "profiles.js", "schedule-controls.js", "activity-dashboard.js", "parent-settings.js", "first-run.js", "runtime-controls.js"):
            self.assertIn(f'$SRC_DIR/frontend/{asset}', installer)
        self.assertIn('backup_if_exists "$FRONTEND_DESIGN_SYSTEM_FILE"', installer)
        self.assertIn('backup_if_exists "$FRONTEND_ICONS_FILE"', installer)
        self.assertIn('backup_if_exists "$FRONTEND_DIALOGS_FILE"', installer)
        self.assertIn('backup_if_exists "$FRONTEND_PROFILES_FILE"', installer)
        self.assertIn('backup_if_exists "$FRONTEND_SCHEDULE_FILE"', installer)
        self.assertIn('backup_if_exists "$FRONTEND_ACTIVITY_FILE"', installer)
        self.assertIn('backup_if_exists "$FRONTEND_LOCALIZATION_FILE"', installer)
        self.assertIn('backup_if_exists "$FRONTEND_FIRST_RUN_FILE"', installer)

    def test_design_system_defines_shared_tokens_and_controls(self):
        source = (
            REPOSITORY_ROOT / "src" / "frontend" / "design-system.css"
        ).read_text(encoding="utf-8")
        for token in (
            "--space-2",
            "--radius-control",
            "--touch-target-min",
            "--focus-ring-width",
            "--motion-fast",
        ):
            self.assertIn(token, source)
        for control in (".smallbtn", ".nav", "input, select", ".panel"):
            self.assertIn(control, source)
        self.assertIn(".pinbox, .install-box, .timerbox", source)

    def test_parent_settings_are_split_into_six_keyboard_sections(self):
        source = frontend_source()
        for section in (
            "overview",
            "children",
            "apps",
            "screen-time",
            "appearance",
            "system",
        ):
            self.assertIn(f'data-admin-section="{section}"', source)
            self.assertIn(f'data-admin-panel="{section}"', source)
        self.assertIn("function activateAdminSection(", source)
        self.assertIn("function handleAdminNavKey(", source)
        self.assertIn("button.tabIndex=active?0:-1", source)

        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        for label in (
            "Übersicht",
            "Kinder",
            "Apps & Medien",
            "Bildschirmzeit",
            "Darstellung",
            "Overview",
            "Children",
            "Apps & Media",
            "Screen Time",
            "Appearance",
        ):
            self.assertIn(label, installer)

    def test_app_editor_search_and_visibility_filters_are_localized(self):
        source = frontend_source()
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="tileSearch" type="search"', source)
        self.assertIn('id="tileVisibilityFilter"', source)
        self.assertIn('id="adminTileEmptyState"', source)
        self.assertIn("function filteredAdminTileIndexes()", source)
        self.assertIn("function setAdminTileSearch(value)", source)
        self.assertIn("function setAdminTileVisibility(value)", source)
        self.assertIn("renderAdminPageNav(filteredTileIndexes.length)", source)
        self.assertIn(
            "if(adminTileVisibility==='all') renderAdminSections(); else renderAdmin();",
            source,
        )
        for label in (
            "Apps und Medien durchsuchen",
            "Nach Sichtbarkeit filtern",
            "Keine Kacheln passen zu Suche und Filter.",
            "Search apps and media",
            "Filter by visibility",
            "No tiles match your search and filter.",
        ):
            self.assertIn(label, installer)

    def test_appearance_live_preview_does_not_apply_unsaved_settings(self):
        source = frontend_source()
        preview = source[
            source.index("function renderAppearancePreview()"):
            source.index("function filteredAdminTileIndexes()")
        ]
        self.assertIn('id="appearancePreview"', source)
        self.assertIn('id="appearancePreviewGrid"', source)
        self.assertIn("preview.className='launcher-preview theme-'", preview)
        self.assertIn("previewGrid.replaceChildren()", preview)
        self.assertIn("createTileVisual(tile.emoji,'preview-tile-emoji')", preview)
        self.assertIn("label.textContent=tile.label||''", preview)
        self.assertNotIn("document.body.className", preview)
        self.assertNotIn("persistConfig", preview)

        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('de:preview_title) echo "Vorschau"', installer)
        self.assertIn('en:preview_title) echo "Preview"', installer)

    def test_app_editor_bulk_actions_use_stable_tile_ids(self):
        source = frontend_source()
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("adminSelectedTileIds=new Set()", source)
        self.assertIn('id="bulkSelectFiltered"', source)
        self.assertIn('id="bulkShowTilesBtn"', source)
        self.assertIn('id="bulkHideTilesBtn"', source)
        self.assertIn('id="bulkDeleteTilesBtn"', source)
        self.assertIn("function toggleFilteredTileSelection(selected)", source)
        self.assertIn("function setSelectedTilesVisible(visible)", source)
        self.assertIn("function deleteSelectedTiles()", source)
        self.assertIn("adminSelectedTileIds.has(tile.id)", source)
        self.assertIn("requestConfirmation(uiText.appBulkDeleteConfirm", source)
        design_system = (
            REPOSITORY_ROOT / "src" / "frontend" / "design-system.css"
        ).read_text(encoding="utf-8")
        self.assertIn(".smallbtn:disabled", design_system)
        for label in (
            "Mehrfachaktionen",
            "Treffer auswählen",
            "Auswahl löschen",
            "Bulk actions",
            "Select results",
            "Delete selection",
        ):
            self.assertIn(label, installer)

    def test_destructive_frontend_actions_share_an_accessible_confirmation_dialog(self):
        source = frontend_source()
        dialogs = (REPOSITORY_ROOT / "src" / "frontend" / "dialogs.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="confirmOverlay"', source)
        self.assertIn('role="dialog"', source)
        self.assertIn('aria-modal="true"', source)
        self.assertNotIn("window.confirm(", source)
        self.assertEqual(source.count("requestConfirmation("), 7)
        self.assertIn("return new Promise(resolve=>", dialogs)
        self.assertIn("confirmationReturnFocus=document.activeElement", dialogs)
        self.assertIn("returnFocus.focus()", dialogs)
        self.assertIn("event.key==='Escape'", dialogs)
        self.assertIn("event.stopImmediatePropagation()", dialogs)
        self.assertIn("buttons[buttons.length-1].focus()", dialogs)

        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('de:confirm_title) echo "Bitte bestätigen"', installer)
        self.assertIn('en:confirm_title) echo "Please confirm"', installer)

    def test_async_frontend_resources_have_localized_recoverable_states(self):
        source = frontend_source()
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('id="startupState"', source)
        self.assertIn('id="appCatalogState"', source)
        self.assertIn('id="browserCatalogState"', source)
        self.assertIn('id="saveMsg"', source)
        self.assertIn("function renderUiState(element,state,message,retryAction=null)", source)
        self.assertIn("function showLauncherStartupState(state)", source)
        self.assertIn("async function bootstrapLauncher()", source)
        bootstrap = source[
            source.index("async function bootstrapLauncher()"):
            source.index("function applyDynamicTheme()")
        ]
        self.assertLess(bootstrap.index("await loadConfig()"), bootstrap.index("Promise.all(["))
        self.assertIn("showLauncherStartupState('error')", bootstrap)
        self.assertIn("loadApps()", bootstrap)
        self.assertIn("loadRecommendations()", bootstrap)
        self.assertIn("loadBrowsers()", bootstrap)
        self.assertIn("appCatalogState='error'", source)
        self.assertIn("recommendationState=recommendations.length?'ready':'empty'", source)
        self.assertIn("if(recommendationState==='error') return", source)
        self.assertIn("browserCatalogState='error'", source)
        self.assertIn("opt.value=currentBrowser", source)
        self.assertIn("renderUiState(msg,'loading',uiText.updateLoading)", source)
        self.assertIn("renderUiState(message,'error',uiText.saveError)", source)
        self.assertIn("backupState=backups.length?'ready':'empty'", source)
        self.assertIn("@keyframes uiStateSpin", source)
        for label in (
            "Launcher wird geladen...",
            "Die Launcher-Einstellungen konnten nicht geladen werden.",
            "App-Empfehlungen konnten nicht geladen werden.",
            "Loading launcher...",
            "The launcher settings could not be loaded.",
            "App recommendations could not be loaded.",
        ):
            self.assertIn(label, installer)

    def test_tile_content_is_rendered_as_text(self):
        source = frontend_source()
        self.assertIn("tileLabel.textContent=tile.label||''", source)
        self.assertIn("createTileVisual(tile.emoji,'emoji')", source)
        self.assertIn("emoji.textContent=value||'✨'", source)
        self.assertNotIn("btn.innerHTML=html", source)

    def test_profile_interfaces_keep_parent_authentication_and_render_text_safely(self):
        source = frontend_source()
        profiles = (REPOSITORY_ROOT / "src" / "frontend" / "profiles.js").read_text(
            encoding="utf-8"
        )
        self.assertIn("fetch(path", profiles)
        self.assertIn("'/api/profiles/create'", profiles)
        self.assertIn("'/api/profiles/select'", profiles)
        self.assertIn("'/api/profiles/delete'", profiles)
        self.assertIn("requestPin(()=>activateProfile", profiles)
        self.assertIn("name.textContent=profile.name", profiles)
        self.assertIn("avatar.textContent=profile.avatar||'👤'", profiles)
        self.assertNotIn("innerHTML", profiles)
        self.assertIn("localStorage.getItem(profileStorageKey())", source)
        self.assertIn("localStorage.setItem(profileStorageKey(),id)", source)
        self.assertIn("document.getElementById('profileOverlay').classList.contains('hidden')", source)

    def test_guided_setup_and_runtime_locales_are_local_dependency_free_assets(self):
        frontend = REPOSITORY_ROOT / "src" / "frontend"
        source = frontend_source()
        first_run = (frontend / "first-run.js").read_text(encoding="utf-8")
        localization = (frontend / "localization.js").read_text(encoding="utf-8")
        de = json.loads((frontend / "locales" / "de.json").read_text(encoding="utf-8"))
        en = json.loads((frontend / "locales" / "en.json").read_text(encoding="utf-8"))
        self.assertEqual(de.keys(), en.keys())
        self.assertGreaterEqual(len(de), 140)
        self.assertIn("'/frontend/locales/'+normalized+'.json'", localization)
        self.assertNotIn("https://", localization)
        self.assertNotIn("innerHTML", first_run)
        self.assertIn("cfg.setupCompleted!==false", first_run)
        self.assertIn("cfg.setupCompleted=true", first_run)
        self.assertIn("await persistConfig()", first_run)
        self.assertIn("requestPin(persistFirstRun)", first_run)
        self.assertIn("document.getElementById('firstRunOverlay').classList.contains('hidden')", source)

    def test_schedule_controls_use_local_status_and_safe_dom_rendering(self):
        frontend = REPOSITORY_ROOT / "src" / "frontend"
        source = frontend_source()
        controls = (frontend / "schedule-controls.js").read_text(encoding="utf-8")
        browser = (REPOSITORY_ROOT / "src" / "browser.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('<script defer src="/frontend/schedule-controls.js"></script>', source)
        self.assertIn("fetch('/api/availability/status'", controls)
        self.assertIn("blockedTileIds", controls)
        self.assertIn("setProfileScheduleEnabled", controls)
        self.assertIn("setAppScheduleEnabled", controls)
        self.assertIn("renderScheduleEditor", controls)
        self.assertNotIn("innerHTML", controls)
        self.assertNotIn("https://", controls)
        self.assertIn('id="availabilityBlock"', source)
        self.assertIn("aria-disabled','true'", source)
        self.assertIn("document.getElementById('availabilityBlock').classList.contains('hidden')", source)
        self.assertIn("browserParams.get('tile')", browser)
        self.assertIn("fetch('/api/availability/status'", browser)
        self.assertIn("navigator.sendBeacon", browser)
        self.assertIn("'/api/activity/finish'", browser)

    def test_local_icon_registry_preserves_custom_emoji_tiles(self):
        source = frontend_source()
        icons = (REPOSITORY_ROOT / "src" / "frontend" / "icons.js").read_text(
            encoding="utf-8"
        )
        self.assertIn('<script defer src="/frontend/icons.js"></script>', source)
        self.assertLess(source.index("/frontend/state.js"), source.index("/frontend/icons.js"))
        self.assertLess(source.index("/frontend/icons.js"), source.index("/frontend/dialogs.js"))
        self.assertIn("const LOCAL_ICON_PATHS=Object.freeze({", icons)
        self.assertIn("function createLocalIcon(name,className='ui-icon')", icons)
        self.assertIn("function setIconLabel(element,name,label)", icons)
        self.assertIn("function localTileIconName(value)", icons)
        self.assertIn("return LEGACY_TILE_ICONS[normalized]||''", icons)
        self.assertIn("emoji.textContent=value||'✨'", icons)
        self.assertNotIn("innerHTML", icons)
        self.assertNotIn("https://", icons)
        self.assertNotIn("fetch(", icons)
        self.assertIn("setIconLabel(button,ADMIN_SECTION_ICONS[section],label)", source)
        self.assertIn("setIconLabel(shutdownBtn,'power'", source)
        self.assertIn("setIconLabel(badge,clockIconName(h)", source)

    def test_every_tile_uses_the_same_launch_endpoint(self):
        source = frontend_source()
        launch_function = source[source.index("function launchTile"):source.index("// PIN handling")]
        self.assertIn("fetch('/launch/'", launch_function)
        self.assertNotIn("special:browser:", launch_function)
        self.assertNotIn("special:external-browser:", launch_function)

    def test_frontend_uses_the_local_update_status_endpoint(self):
        source = frontend_source()
        self.assertIn("fetch('/api/update/status'", source)
        self.assertNotIn("raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main/VERSION", source)

    def test_diagnostics_download_is_local_and_bilingual(self):
        source = frontend_source()
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("fetch('/api/diagnostics')", source)
        self.assertIn("{{LABEL_EXPORT_DIAGNOSTICS}}", source)
        self.assertIn('de:export_diagnostics) echo "Diagnose herunterladen"', installer)
        self.assertIn('en:export_diagnostics) echo "Download diagnostics"', installer)

    def test_activity_dashboard_is_local_bounded_and_bilingual(self):
        dashboard = (
            REPOSITORY_ROOT / "src" / "frontend" / "activity-dashboard.js"
        ).read_text(encoding="utf-8")
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("fetch('/api/activity'", dashboard)
        self.assertIn("fetch('/api/activity/export'", dashboard)
        self.assertIn("fetch('/api/activity/clear'", dashboard)
        self.assertIn("activityData.records.slice(0,12)", dashboard)
        self.assertIn("requestConfirmation(uiText.activityClearConfirm", dashboard)
        self.assertIn("document.createElement('li')", dashboard)
        self.assertNotIn("innerHTML", dashboard)
        for label in (
            "Aktivitätsübersicht",
            "Aktivität exportieren",
            "Activity overview",
            "Export activity",
        ):
            self.assertIn(label, installer)

    def test_theme_and_browser_labels_follow_the_interface_language(self):
        source = frontend_source()
        self.assertIn("const THEME_LABELS=", source)
        self.assertIn("function interfaceLanguage()", source)
        self.assertIn("themeLabel(t.id)", source)
        self.assertIn("Changes take effect after the next login.", source)

    def test_browser_tile_fields_do_not_hide_their_mode_selector(self):
        source = frontend_source()
        self.assertIn("select.className='appSelect'", source)
        self.assertIn(".tileform.has-browser > .appSelect { display:none; }", source)
        self.assertNotIn(".tileform.has-browser select { display:none; }", source)

    def test_embedded_browser_editor_explains_and_validates_exact_origin_boundaries(self):
        source = frontend_source()
        browser = (REPOSITORY_ROOT / "src" / "browser.html").read_text(
            encoding="utf-8"
        )
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("function parseBrowserAllowedOrigins(value)", source)
        self.assertIn("tile.browserAllowedOrigins=origins", source)
        self.assertIn("origins.length>20", source)
        self.assertIn("uiText.browserBoundaryEmbedded", source)
        self.assertIn("uiText.browserBoundaryExternal", source)
        self.assertIn("document.querySelector('#admin :invalid')", source)
        self.assertNotIn("allow-top-navigation", browser)
        self.assertIn("securitypolicyviolation", browser)
        self.assertIn('role="alertdialog"', browser)
        self.assertIn('aria-describedby="navigationBlockBody"', browser)
        self.assertIn("buttons[event.shiftKey?buttons.length-1:0].focus()", browser)
        for label in (
            "Zusätzliche erlaubte Websites",
            "andere Ziele bleiben blockiert",
            "Additional allowed websites",
            "other destinations stay blocked",
            "Diese Seite ist nicht erlaubt",
            "This page is not allowed",
        ):
            self.assertIn(label, installer)

    def test_backup_restore_ui_uses_local_api_and_text_content(self):
        source = frontend_source()
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

    def test_accessibility_preferences_and_compact_layout_are_explicit(self):
        styles = (REPOSITORY_ROOT / "src" / "frontend" / "styles.css").read_text(
            encoding="utf-8"
        )
        self.assertIn("@media (prefers-reduced-motion: reduce)", styles)
        self.assertIn("animation-duration:.01ms !important", styles)
        self.assertIn("@media (forced-colors: active)", styles)
        self.assertIn("border:2px solid ButtonText", styles)
        self.assertIn("@media (max-width:900px), (max-height:700px)", styles)
        self.assertIn("#admin .wrap { max-height:calc(100vh - 76px)", styles)

    def test_keyboard_and_touch_navigation_respect_ui_boundaries(self):
        source = frontend_source()
        self.assertIn("const el=document.createElement('button')", source)
        self.assertIn("el.setAttribute('aria-pressed'", source)
        self.assertIn("btn.onfocus=()=>{ focusedTileIndex=i; updateTileFocus(false); }", source)
        self.assertIn("btn.focus({preventScroll:true})", source)
        self.assertIn("pinReturnFocus.focus()", source)
        self.assertIn("const tileFocused=document.activeElement", source)
        self.assertIn("function homeGestureAllowed()", source)
        self.assertIn("touchStartX===null||touchStartY===null", source)
        self.assertIn("homeHidden||cfg.currentPage<=0", source)


if __name__ == "__main__":
    unittest.main()
