#!/usr/bin/env python3
import http.server
import json
import os
import re
import shutil
import subprocess
import threading
import time
from urllib.parse import parse_qs, quote, unquote, urlparse

from app_detection import (
    BROWSER_CANDIDATES,
    browser_statuses,
    find_browser as detect_browser,
    parse_desktop_file,
    scan_apps as discover_apps,
)
from application_launcher import (
    ApplicationLauncher,
    direct_app_command,
    external_browser_command as build_external_browser_command,
    resolve_tile_action,
)
from activity_store import (
    ACTIVITY_VERSION,
    EmbeddedActivitySessions,
    activity_payload,
    remove_profile_activity,
)
from config_store import (
    CURRENT_CONFIG_VERSION,
    atomic_write_config,
    migrate_config,
    read_config,
)
from config_validation import (
    MAX_TILES,
    public_config,
    validate_config,
    validate_stored_config,
)
from profile_config import (
    active_config,
    add_profile,
    merge_active_config,
    profile_summaries,
    remove_profile,
    select_profile,
)
from backup_store import (
    create_pre_restore_backup,
    discover_config_backups,
    read_config_backup,
)
from browser_policy import allowed_frame_origins, embedded_browser_csp
from lifecycle_state import (
    clear_lifecycle_request,
    read_lifecycle_state,
    write_lifecycle_request,
)
from media_library import (
    MAX_MEDIA_COVER_BYTES,
    SUPPORTED_MEDIA_PATTERNS,
    catalog_item,
    find_media_player as detect_media_player,
    has_media as path_has_media,
    media_locations as discover_media_locations,
    media_player_command,
    public_media_catalog,
    scan_media_catalog,
)
from media_state import (
    media_state_payload,
    record_media_play,
    remove_profile_media_state,
    set_media_favorite,
)
from parent_auth import (
    ADMIN_COOKIE_NAME,
    ADMIN_SESSION_TTL_SECONDS,
    PIN_FAILURE_LIMIT,
    PIN_FAILURE_WINDOW_SECONDS,
    PIN_KDF_ITERATIONS,
    admin_session_cookie,
    clear_admin_sessions,
    clear_pin_failures,
    create_admin_session,
    expired_admin_session_cookie,
    hash_pin,
    is_legacy_pin_hash,
    is_supported_pin_hash,
    pin_attempt_blocked,
    record_pin_failure,
    valid_admin_session,
    verify_pin,
)
from process_state import (
    owned_process_alive,
    remove_process_record,
    terminate_owned_process,
    write_process_record,
)
from runtime_diagnostics import (
    build_diagnostics,
    close_runtime_logging,
    configure_runtime_logging,
    log_runtime_event,
)
from schedule_rules import availability_summary, tile_availability
from timer_state import (
    clear_timer as remove_timer_state,
    load_timer as read_timer_state,
    save_timer as write_timer_state,
    timer_status as calculate_timer_status,
)
from update_manager import (
    MissingUpdaterError,
    fetch_remote_json as fetch_update_json,
    fetch_remote_text as fetch_update_text,
    parse_semver,
    read_version,
    resolve_update_status,
    version_is_newer,
    write_update_trigger,
)

HOME = os.path.expanduser("~")
APP_ROOT = os.path.join(HOME, ".local", "share", "{{APP_ID}}")
VERSION_FILE = os.path.join(APP_ROOT, "version")
UPDATE_SCRIPT = os.path.join(APP_ROOT, "update.sh")
UPDATE_CHANNEL_FILE = os.path.join(APP_ROOT, "update-channel")
LATEST_RELEASE_API = os.environ.get(
    "COZY_KIDS_RELEASE_API_URL",
    "https://api.github.com/repos/TrissyGE/cozy-kids-launcher/releases/latest",
)
LEGACY_RAW_URL = os.environ.get(
    "COZY_KIDS_RAW_URL",
    "https://raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main",
).rstrip("/")
LEGACY_VERSION_URL = f"{LEGACY_RAW_URL}/VERSION"
CFG = os.path.join(HOME, ".config", "{{APP_ID}}", "config.json")
BACKUP_ROOT = os.path.join(HOME, ".local", "share", "{{APP_ID}}-backups")
LOG_FILE = os.path.join(HOME, ".local", "state", "{{APP_ID}}", "runtime.jsonl")
ACTIVITY_FILE = os.path.join(HOME, ".local", "state", "{{APP_ID}}", "activity.json")
MEDIA_STATE_FILE = os.path.join(HOME, ".local", "state", "{{APP_ID}}", "media.json")
PORT = int(os.environ.get("COZY_KIDS_PORT", "{{DEFAULT_PORT}}"))
PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "server.pid")
BROWSER_PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "browser.pid")
TILE_PROCESS_PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "tile-process.pid")
OVERLAY_PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "overlay.pid")
PROCESS_SUPERVISOR = os.path.join(APP_ROOT, "process_supervisor.py")
OVERLAY_SCRIPT = os.path.join(APP_ROOT, "overlay.py")
EXIT_FLAGFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "exit-requested")
LIFECYCLE_STATE_FILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "lifecycle.json")
LIFECYCLE_REQUEST_FILE = os.path.join(
    HOME,
    ".cache",
    "{{APP_ID}}",
    "lifecycle-request.json",
)
RECOMMENDATIONS_FILE = os.path.join(APP_ROOT, "recommendations.json")
VIDEOS = os.path.join(HOME, "Videos")
MUSIC = os.path.join(HOME, "Music")
ALT_MUSIC = os.path.join(HOME, "Musik")
EXTS = SUPPORTED_MEDIA_PATTERNS
LEGACY_WEB_ACTION_MIGRATIONS = {
    "special:external-browser:https://www.netflix.com/browse/kids":
        "special:external-browser:https://www.netflix.com/browse/genre/27346",
    "special:browser:https://www.tivi.de":
        "special:external-browser:https://www.zdf.de/kinder",
    "special:browser:https://www.kika.de":
        "special:external-browser:https://www.kika.de",
}
TIMER_FILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "timer.json")
MAX_JSON_BODY_BYTES = 512 * 1024
_tile_launch_lock = threading.Lock()
_activity_sessions_lock = threading.Lock()
_activity_sessions = None


def has_media(path):
    return path_has_media(path, patterns=EXTS)


def load_stored_cfg():
    data = read_config(CFG)
    data, migrated = migrate_config(data)
    recs = load_recommendations()
    rec_by_first_cmd = {}
    for rec in recs:
        if rec.get("cmd"):
            rec_by_first_cmd[rec["cmd"][0]] = rec["cmd"]
        for alt in rec.get("alt_cmds", []):
            rec_by_first_cmd[alt] = rec["cmd"]
    for profile in data.get("profiles", []):
        for tile in profile.get("tiles", []):
            cmd = tile.get("cmd", [])
            if len(cmd) == 1 and cmd[0] in LEGACY_WEB_ACTION_MIGRATIONS:
                tile["cmd"] = [LEGACY_WEB_ACTION_MIGRATIONS[cmd[0]]]
                cmd = tile["cmd"]
                migrated = True
            if (
                cmd
                and cmd[0] in rec_by_first_cmd
                and cmd != rec_by_first_cmd[cmd[0]]
            ):
                tile["cmd"] = rec_by_first_cmd[cmd[0]]
                migrated = True
    if "autoScanDone" not in data:
        data["autoScanDone"] = True
        migrated = True
    data = validate_stored_config(
        data,
        existing_pin_hash=data.get("pinHash", ""),
        allow_pin_hash=True,
    )
    if migrated:
        atomic_write_config(CFG, data)
        log_runtime_event(
            "config.migrated",
            configVersion=data.get("configVersion", CURRENT_CONFIG_VERSION),
        )
    return data


def load_cfg():
    return active_config(load_stored_cfg())


def save_stored_cfg(data):
    validated = validate_stored_config(
        data,
        existing_pin_hash=data.get("pinHash", ""),
        allow_pin_hash=True,
    )
    atomic_write_config(CFG, validated)
    return validated


def save_cfg(data):
    try:
        stored = load_stored_cfg()
    except FileNotFoundError:
        stored = validate_stored_config(
            data,
            existing_pin_hash=data.get("pinHash", ""),
            allow_pin_hash=True,
        )
        atomic_write_config(CFG, stored)
        return active_config(stored)

    validated = validate_config(
        data,
        existing_pin_hash=stored.get("pinHash", ""),
        allow_pin_hash=True,
    )
    stored = merge_active_config(stored, validated)
    stored = save_stored_cfg(stored)
    return active_config(stored)


def write_browser_override(data):
    browser_file = os.path.join(os.path.dirname(CFG), "browser")
    browser = data.get("browser", "")
    try:
        if browser:
            with open(browser_file, "w", encoding="utf-8") as handle:
                handle.write(browser)
        else:
            os.unlink(browser_file)
    except FileNotFoundError:
        pass
    except OSError:
        pass


def available_config_backups():
    backups = []
    for metadata in discover_config_backups(BACKUP_ROOT):
        try:
            raw = read_config_backup(BACKUP_ROOT, metadata["id"])
            validated = validate_stored_config(raw, existing_pin_hash="")
        except (FileNotFoundError, OSError, ValueError):
            continue
        backups.append({
            **metadata,
            "configVersion": validated.get(
                "configVersion",
                CURRENT_CONFIG_VERSION,
            ),
        })
    return backups


def restore_config_backup(backup_id):
    current = load_stored_cfg()
    raw = read_config_backup(BACKUP_ROOT, backup_id)
    restored = validate_stored_config(
        raw,
        existing_pin_hash=current.get("pinHash", ""),
    )
    safety_backup = create_pre_restore_backup(BACKUP_ROOT, current)
    restored = save_stored_cfg(restored)
    runtime = active_config(restored)
    write_browser_override(runtime)
    log_runtime_event(
        "config.restored",
        configVersion=restored.get(
            "configVersion",
            CURRENT_CONFIG_VERSION,
        ),
    )
    return runtime, safety_backup


def scan_apps():
    return discover_apps(HOME)


def media_location():
    locations = media_locations()
    return locations[0] if locations else None


def media_locations():
    """Return every configured media directory that contains supported files."""
    return discover_media_locations(
        (VIDEOS, MUSIC, ALT_MUSIC),
        has_media_fn=has_media,
    )


def media_catalog():
    """Return a bounded catalog without changing the legacy playlist launch path."""
    return scan_media_catalog((VIDEOS, MUSIC, ALT_MUSIC))


def configured_media_tile(cfg, tile_id):
    """Resolve one visible media tile without trusting a client-supplied command."""
    if not isinstance(tile_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]+", tile_id):
        return None
    tile = next(
        (
            candidate
            for candidate in cfg.get("tiles", [])
            if candidate.get("id") == tile_id and candidate.get("visible", True)
        ),
        None,
    )
    if not tile:
        return None
    try:
        action = resolve_tile_action(tile)
    except ValueError:
        return None
    return tile if action["type"] == "media" else None


def find_media_player():
    return detect_media_player(which=shutil.which)


def get_version():
    return read_version(VERSION_FILE)


def diagnostics_payload():
    """Return technical state without returning any family configuration values."""
    config_readable = False
    config_version = None
    try:
        data = read_config(CFG)
    except (OSError, ValueError, json.JSONDecodeError):
        pass
    else:
        if isinstance(data, dict):
            config_readable = True
            config_version = data.get("configVersion", 0)
    try:
        lifecycle = read_lifecycle_state(LIFECYCLE_STATE_FILE)
    except (OSError, ValueError, json.JSONDecodeError):
        lifecycle = None
    return build_diagnostics(
        LOG_FILE,
        app_version=get_version(),
        config_readable=config_readable,
        config_version=config_version,
        lifecycle=lifecycle,
    )


def activity_catalog(data):
    """Return current display labels without copying them into activity storage."""
    return [
        {
            "id": profile["id"],
            "name": profile.get("name", ""),
            "avatar": profile.get("avatar", ""),
            "tiles": [
                {
                    "id": tile["id"],
                    "label": tile.get("label", ""),
                    "emoji": tile.get("emoji", ""),
                }
                for tile in profile.get("tiles", [])
            ],
        }
        for profile in data.get("profiles", [])
    ]


def browser_wrapper_policy(data, query):
    """Bind one browser wrapper request to its configured embedded tile."""
    params = parse_qs(query, keep_blank_values=True, max_num_fields=8)
    tile_values = params.get("tile", [])
    url_values = params.get("url", [])
    if len(tile_values) != 1 or len(url_values) != 1:
        raise ValueError("Browser wrapper request is incomplete")
    tile_id = tile_values[0]
    requested_url = url_values[0]
    tile = next(
        (
            candidate
            for candidate in data.get("tiles", [])
            if candidate.get("id") == tile_id and candidate.get("visible", True)
        ),
        None,
    )
    if not tile:
        raise ValueError("Browser wrapper tile is unavailable")
    action = resolve_tile_action(tile)
    if (
        action.get("type") != "web"
        or action.get("mode") != "embedded"
        or action.get("url") != requested_url
    ):
        raise ValueError("Browser wrapper target does not match its tile")
    return embedded_browser_csp(allowed_frame_origins(tile, requested_url))


def _fetch_remote_json(url, timeout=5):
    return fetch_update_json(url, timeout=timeout)


def _fetch_remote_text(url, timeout=5):
    return fetch_update_text(url, timeout=timeout)


def get_update_status(timeout=5):
    return resolve_update_status(
        get_version(),
        LATEST_RELEASE_API,
        LEGACY_VERSION_URL,
        UPDATE_CHANNEL_FILE,
        timeout=timeout,
        fetch_json=_fetch_remote_json,
        fetch_text=_fetch_remote_text,
    )


def load_recommendations():
    if not os.path.isfile(RECOMMENDATIONS_FILE):
        return []
    try:
        with open(RECOMMENDATIONS_FILE, "r", encoding="utf-8") as fh:
            recs = json.load(fh)
    except Exception:
        return []
    result = []
    for rec in recs:
        all_cmds = []
        cmd = rec.get("cmd", [])
        # KDE wrapper detection: kstart/kstart5 are wrappers, not the app itself
        is_wrapper = cmd and cmd[0] in ("kstart", "kstart5")
        if is_wrapper:
            # Only check alt_cmds or the actual app name (skip wrapper and --fullscreen)
            for alt in rec.get("alt_cmds", []):
                all_cmds.append(alt)
            for part in cmd[2:]:
                if part and not part.startswith("-"):
                    all_cmds.append(part)
        else:
            if cmd:
                all_cmds.append(cmd[0])
            for alt in rec.get("alt_cmds", []):
                all_cmds.append(alt)
        installed = any(shutil.which(c) for c in all_cmds if c)
        if not installed and rec.get("category") == "browser":
            installed = True
        result.append({**rec, "installed": installed})
    return result


def find_browser(config=None):
    return detect_browser(
        config,
        candidates=BROWSER_CANDIDATES,
        which=shutil.which,
    )


def external_browser_command(browser, url):
    cache_root = os.path.join(HOME, ".cache", "{{APP_ID}}")
    return build_external_browser_command(browser, url, cache_root)


def application_launcher():
    return ApplicationLauncher(
        TILE_PROCESS_PIDFILE,
        OVERLAY_PIDFILE,
        PROCESS_SUPERVISOR,
        OVERLAY_SCRIPT,
        activity_file=ACTIVITY_FILE,
        lock=_tile_launch_lock,
    )


def embedded_activity_sessions():
    global _activity_sessions
    with _activity_sessions_lock:
        if _activity_sessions is None or _activity_sessions.path != os.fspath(ACTIVITY_FILE):
            _activity_sessions = EmbeddedActivitySessions(ACTIVITY_FILE)
        return _activity_sessions


def stop_existing_overlay():
    return application_launcher().stop_existing_overlay()


def stop_active_tile():
    return application_launcher().stop_active_tile()


def start_overlay(mode, url="", tile_id=""):
    return application_launcher().start_overlay(mode, url=url, tile_id=tile_id)


def reset_active_tile():
    embedded_activity_sessions().finish_all()
    application_launcher().reset_active_tile()


def launch_owned_tile(
    command,
    mode,
    url="",
    tile_id="",
    profile_id="",
    track_activity=False,
):
    return application_launcher().launch_owned_tile(
        command,
        mode,
        url=url,
        tile_id=tile_id,
        profile_id=profile_id,
        track_activity=track_activity,
    )


def load_timer():
    return read_timer_state(TIMER_FILE)


def save_timer(data):
    write_timer_state(TIMER_FILE, data)


def clear_timer():
    remove_timer_state(TIMER_FILE)


def timer_status(cfg):
    return calculate_timer_status(load_timer(), cfg, now=time.time())


class Handler(http.server.SimpleHTTPRequestHandler):
    server_version = "CozyKidsLauncher"
    sys_version = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        browser_csp = getattr(self, "browser_content_security_policy", "")
        if browser_csp:
            self.send_header("Content-Security-Policy", browser_csp)
        super().end_headers()

    def json_response(self, payload, status=200, headers=None):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def media_cover_response(self, item):
        path = item.get("coverPath", "") if item else ""
        content_types = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }
        content_type = content_types.get(os.path.splitext(path)[1].casefold())
        if not content_type:
            self.send_error(404)
            return
        try:
            with open(path, "rb") as cover_file:
                payload = cover_file.read(MAX_MEDIA_COVER_BYTES + 1)
        except OSError:
            self.send_error(404)
            return
        if len(payload) > MAX_MEDIA_COVER_BYTES:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def read_json_body(self, required=True):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.json_response({"status": "error", "message": "Invalid Content-Length"}, 400)
            return None
        if length < 0 or length > MAX_JSON_BODY_BYTES:
            self.json_response({"status": "error", "message": "Request body is too large"}, 413)
            return None
        if length == 0:
            if required:
                self.json_response({"status": "error", "message": "JSON body required"}, 400)
                return None
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self.json_response({"status": "error", "message": "Invalid JSON"}, 400)
            return None
        if not isinstance(data, dict):
            self.json_response({"status": "error", "message": "JSON body must be an object"}, 400)
            return None
        return data

    def request_has_local_origin(self):
        if self.headers.get("Sec-Fetch-Site", "").lower() == "cross-site":
            return False
        origin = self.headers.get("Origin")
        if not origin:
            return True
        try:
            parsed = urlparse(origin)
            expected_port = self.server.server_address[1]
            actual_port = parsed.port or (443 if parsed.scheme == "https" else 80)
            return (
                parsed.scheme == "http"
                and parsed.hostname in ("127.0.0.1", "localhost", "::1")
                and actual_port == expected_port
            )
        except ValueError:
            return False

    def has_admin_access(self, cfg=None):
        cfg = load_cfg() if cfg is None else cfg
        if not cfg.get("pinHash", ""):
            return True
        return valid_admin_session(self.headers.get("Cookie", ""))

    def require_admin(self, cfg=None):
        if self.has_admin_access(cfg):
            return True
        self.json_response({"status": "error", "message": "Parent authentication required"}, 403)
        return False

    @staticmethod
    def admin_cookie(token):
        return admin_session_cookie(token)

    def do_GET(self):
        request_url = urlparse(self.path)
        if request_url.path == "/browser.html":
            try:
                self.browser_content_security_policy = browser_wrapper_policy(
                    load_cfg(),
                    request_url.query,
                )
            except ValueError:
                self.send_error(404)
                return
            return super().do_GET()
        if request_url.path == "/api/media":
            entries, truncated = media_catalog()
            cfg = load_cfg()
            try:
                state = media_state_payload(
                    MEDIA_STATE_FILE,
                    cfg.get("activeProfileId", ""),
                    available_ids=[entry["id"] for entry in entries],
                )
            except (OSError, ValueError):
                state = {"favoriteIds": [], "recentIds": []}
            return self.json_response({
                "items": public_media_catalog(entries),
                "truncated": truncated,
                **state,
            })
        if request_url.path == "/api/media/cover":
            query = parse_qs(request_url.query, keep_blank_values=True)
            media_ids = query.get("id", [])
            if len(media_ids) != 1 or len(query) != 1:
                self.send_error(404)
                return
            entries, _ = media_catalog()
            return self.media_cover_response(catalog_item(entries, media_ids[0]))
        if self.path == "/api/config":
            return self.json_response(public_config(load_cfg()))
        if self.path == "/api/profiles":
            data = load_stored_cfg()
            if not self.require_admin(active_config(data)):
                return
            return self.json_response({
                "activeProfileId": data["activeProfileId"],
                "profiles": profile_summaries(data),
            })
        if self.path == "/api/apps":
            return self.json_response(scan_apps())
        if self.path == "/api/recommendations":
            return self.json_response(load_recommendations())
        if self.path == "/api/version":
            return self.json_response({"version": get_version()})
        if self.path == "/api/update/status":
            try:
                status = get_update_status()
            except RuntimeError as exc:
                log_runtime_event(
                    "update.failed",
                    level="warning",
                    exceptionType=type(exc).__name__,
                )
                return self.json_response({"status": "error", "message": str(exc)}, 503)
            log_runtime_event(
                "update.checked",
                source=status["source"],
                updateAvailable=status["updateAvailable"],
                version=status["latestVersion"],
            )
            return self.json_response(status)
        if self.path == "/api/features":
            shutdown_ok = bool(
                shutil.which("systemctl") or shutil.which("loginctl")
            )
            return self.json_response({"shutdownAvailable": shutdown_ok})
        if self.path == "/api/browsers":
            return self.json_response(
                browser_statuses(BROWSER_CANDIDATES, which=shutil.which)
            )
        if self.path == "/api/timer/status":
            return self.json_response(timer_status(load_cfg()))
        if self.path == "/api/availability/status":
            return self.json_response(availability_summary(load_cfg()))
        if self.path == "/api/activity":
            stored = load_stored_cfg()
            data = active_config(stored)
            if not self.require_admin(data):
                return
            payload = activity_payload(ACTIVITY_FILE)
            payload["enabled"] = bool(data.get("activityTrackingEnabled", False))
            payload["profiles"] = activity_catalog(stored)
            return self.json_response(payload)
        if self.path == "/api/activity/export":
            data = load_cfg()
            if not self.require_admin(data):
                return
            activity = activity_payload(ACTIVITY_FILE)
            payload = json.dumps({
                "activityVersion": ACTIVITY_VERSION,
                "exportedAt": int(time.time()),
                "records": list(reversed(activity["records"])),
            }, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="cozy-kids-activity.json"',
            )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/api/backups":
            data = load_cfg()
            if not self.require_admin(data):
                return
            return self.json_response({"backups": available_config_backups()})
        if self.path == "/api/export-config":
            data = load_stored_cfg()
            if not self.require_admin(active_config(data)):
                return
            payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="cozy-kids-config.json"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        if self.path == "/api/diagnostics":
            data = load_cfg()
            if not self.require_admin(data):
                return
            payload = json.dumps(
                diagnostics_payload(),
                ensure_ascii=False,
                indent=2,
            ).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header(
                "Content-Disposition",
                'attachment; filename="cozy-kids-diagnostics.json"',
            )
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            log_runtime_event("diagnostics.exported")
            return
        return super().do_GET()

    def do_POST(self):
        if not self.request_has_local_origin():
            log_runtime_event("request.rejected", level="warning", statusCode=403)
            self.json_response({"status": "error", "message": "Cross-site request rejected"}, 403)
            return
        action = self.path.strip("/")
        if action == "api/media/favorite":
            body = self.read_json_body()
            if body is None:
                return
            cfg = load_cfg()
            tile_id = body.get("tileId")
            if not configured_media_tile(cfg, tile_id):
                self.send_response(404)
                self.end_headers()
                return
            availability = tile_availability(cfg, tile_id)
            if not availability["allowed"]:
                self.json_response({
                    "status": "blocked",
                    "reason": availability["reason"],
                }, 403)
                return
            entries, _ = media_catalog()
            item = catalog_item(entries, body.get("mediaId"))
            if not item:
                self.send_response(404)
                self.end_headers()
                return
            try:
                favorite = set_media_favorite(
                    MEDIA_STATE_FILE,
                    cfg.get("activeProfileId", ""),
                    item["id"],
                    body.get("favorite"),
                )
            except ValueError as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            except OSError:
                self.json_response(
                    {"status": "error", "message": "Media favorite could not be saved"},
                    503,
                )
                return
            self.json_response({"status": "ok", "favorite": favorite})
            return
        if action == "api/media/play":
            body = self.read_json_body()
            if body is None:
                return
            cfg = load_cfg()
            tile_id = body.get("tileId")
            if not configured_media_tile(cfg, tile_id):
                self.send_response(404)
                self.end_headers()
                return
            availability = tile_availability(cfg, tile_id)
            if not availability["allowed"]:
                self.json_response({
                    "status": "blocked",
                    "reason": availability["reason"],
                }, 403)
                return
            entries, _ = media_catalog()
            item = catalog_item(entries, body.get("mediaId"))
            if not item:
                self.send_response(404)
                self.end_headers()
                return
            player = find_media_player()
            if player:
                command = media_player_command(player, [item["path"]])
            elif shutil.which("xdg-open"):
                command = ["xdg-open", item["path"]]
            else:
                log_runtime_event(
                    "launch.failed",
                    level="warning",
                    actionType="media",
                    result="missing",
                )
                self.json_response(
                    {"status": "error", "message": "No supported media player found"},
                    503,
                )
                return
            log_runtime_event("launch.started", actionType="media")
            try:
                launch_owned_tile(
                    command,
                    "local",
                    tile_id=tile_id,
                    profile_id=cfg.get("activeProfileId", ""),
                    track_activity=cfg.get("activityTrackingEnabled", False),
                )
            except OSError:
                log_runtime_event(
                    "launch.failed",
                    level="warning",
                    actionType="media",
                    result="failure",
                )
                self.json_response(
                    {"status": "error", "message": "Media process could not be started"},
                    503,
                )
                return
            try:
                record_media_play(
                    MEDIA_STATE_FILE,
                    cfg.get("activeProfileId", ""),
                    item["id"],
                )
            except (OSError, ValueError):
                pass
            self.send_response(204)
            self.end_headers()
            return
        if action == "api/activity/finish":
            body = self.read_json_body()
            if body is None:
                return
            embedded_activity_sessions().finish(body.get("token"))
            self.send_response(204)
            self.end_headers()
            return
        if action == "api/activity/clear":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            body = self.read_json_body(required=False)
            if body is None:
                return
            try:
                embedded_activity_sessions().discard_all()
            except OSError:
                self.json_response(
                    {"status": "error", "message": "Activity data could not be removed"},
                    500,
                )
                return
            self.json_response({"status": "ok"})
            return
        if action == "api/profiles/create":
            stored = load_stored_cfg()
            if not self.require_admin(active_config(stored)):
                return
            body = self.read_json_body()
            if body is None:
                return
            try:
                stored, profile_id = add_profile(
                    stored,
                    body.get("name"),
                    body.get("avatar", ""),
                )
                stored = save_stored_cfg(stored)
            except (OSError, ValueError) as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            log_runtime_event("profile.created")
            self.json_response({
                "status": "ok",
                "profileId": profile_id,
                "activeProfileId": stored["activeProfileId"],
                "profiles": profile_summaries(stored),
            })
            return
        if action == "api/profiles/select":
            stored = load_stored_cfg()
            if not self.require_admin(active_config(stored)):
                return
            body = self.read_json_body()
            if body is None:
                return
            try:
                stored = select_profile(stored, body.get("profileId"))
                stored = save_stored_cfg(stored)
                clear_timer()
            except (OSError, ValueError) as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            log_runtime_event("profile.selected")
            self.json_response({
                "status": "ok",
                "config": public_config(active_config(stored)),
            })
            return
        if action == "api/profiles/delete":
            stored = load_stored_cfg()
            if not self.require_admin(active_config(stored)):
                return
            body = self.read_json_body()
            if body is None:
                return
            try:
                stored = remove_profile(stored, body.get("profileId"))
                remove_profile_activity(ACTIVITY_FILE, body.get("profileId"))
                remove_profile_media_state(MEDIA_STATE_FILE, body.get("profileId"))
                stored = save_stored_cfg(stored)
            except (OSError, ValueError) as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            log_runtime_event("profile.removed")
            self.json_response({
                "status": "ok",
                "activeProfileId": stored["activeProfileId"],
                "profiles": profile_summaries(stored),
            })
            return
        if action == "api/save-config":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            data = self.read_json_body()
            if data is None:
                return
            try:
                data = validate_config(data, existing_pin_hash=cfg.get("pinHash", ""))
                data = save_cfg(data)
            except (OSError, ValueError) as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            write_browser_override(data)
            log_runtime_event(
                "config.saved",
                configVersion=data.get("configVersion", CURRENT_CONFIG_VERSION),
            )
            self.json_response({"status": "ok", "config": public_config(data)})
            return
        if action == "api/verify-pin":
            if pin_attempt_blocked():
                log_runtime_event("auth.throttled", level="warning")
                self.json_response({"valid": False, "message": "Too many attempts"}, 429)
                return
            data = self.read_json_body()
            if data is None:
                return
            cfg = load_cfg()
            pin_hash = cfg.get("pinHash", "")
            if not pin_hash:
                log_runtime_event("auth.succeeded")
                self.json_response({"valid": True, "pinConfigured": False})
                return
            pin = data.get("pin", "")
            if not isinstance(pin, str) or not verify_pin(pin_hash, pin):
                record_pin_failure()
                log_runtime_event("auth.failed", level="warning")
                self.json_response({"valid": False}, 403)
                return
            clear_pin_failures()
            if is_legacy_pin_hash(pin_hash):
                cfg["pinHash"] = hash_pin(pin)
                save_cfg(cfg)
            token = create_admin_session()
            log_runtime_event("auth.succeeded")
            self.json_response(
                {"valid": True, "pinConfigured": True},
                headers={"Set-Cookie": self.admin_cookie(token)},
            )
            return
        if action == "api/pin/set":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            data = self.read_json_body()
            if data is None:
                return
            try:
                cfg["pinHash"] = hash_pin(data.get("pin", ""))
                save_cfg(cfg)
            except (OSError, ValueError) as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            clear_admin_sessions()
            token = create_admin_session()
            log_runtime_event("pin.changed")
            self.json_response(
                {"status": "ok", "pinConfigured": True},
                headers={"Set-Cookie": self.admin_cookie(token)},
            )
            return
        if action == "api/pin/remove":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            cfg["pinHash"] = ""
            save_cfg(cfg)
            clear_admin_sessions()
            log_runtime_event("pin.removed")
            self.json_response(
                {"status": "ok", "pinConfigured": False},
                headers={"Set-Cookie": expired_admin_session_cookie()},
            )
            return
        if action == "api/import-config":
            stored = load_stored_cfg()
            cfg = active_config(stored)
            if not self.require_admin(cfg):
                return
            data = self.read_json_body()
            if data is None:
                return
            try:
                imported = validate_stored_config(
                    data,
                    existing_pin_hash=cfg.get("pinHash", ""),
                    allow_pin_hash="pinHash" in data,
                )
                imported = save_stored_cfg(imported)
                write_browser_override(active_config(imported))
            except (OSError, ValueError) as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            if imported.get("pinHash", "") != cfg.get("pinHash", ""):
                clear_admin_sessions()
            log_runtime_event(
                "config.imported",
                configVersion=imported.get("configVersion", CURRENT_CONFIG_VERSION),
            )
            self.json_response({"status": "ok"})
            return
        if action == "api/backups/restore":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            data = self.read_json_body()
            if data is None:
                return
            backup_id = data.get("backupId")
            if not isinstance(backup_id, str):
                self.json_response(
                    {"status": "error", "message": "Invalid backup identifier"},
                    400,
                )
                return
            try:
                restored, safety_backup = restore_config_backup(backup_id)
            except FileNotFoundError as exc:
                self.json_response(
                    {"status": "error", "message": str(exc)},
                    404,
                )
                return
            except ValueError as exc:
                self.json_response(
                    {"status": "error", "message": str(exc)},
                    400,
                )
                return
            except OSError:
                self.json_response(
                    {"status": "error", "message": "Backup could not be restored"},
                    500,
                )
                return
            self.json_response({
                "status": "ok",
                "config": public_config(restored),
                "safetyBackupId": safety_backup["id"],
            })
            return
        if action == "shutdown":
            if not self.require_admin():
                return
            shutdown_ok = False
            try:
                write_lifecycle_request(LIFECYCLE_REQUEST_FILE, "shutdown")
            except (OSError, ValueError):
                pass
            for cmd in (["systemctl", "poweroff"], ["loginctl", "poweroff"]):
                if shutil.which(cmd[0]):
                    try:
                        subprocess.Popen(cmd, env=dict(os.environ))
                        shutdown_ok = True
                        break
                    except Exception:
                        pass
            if not shutdown_ok:
                try:
                    clear_lifecycle_request(LIFECYCLE_REQUEST_FILE)
                except OSError:
                    pass
            self.json_response({"status": "ok" if shutdown_ok else "error"})
            return
        if action == "exit-kids":
            if not self.require_admin():
                return
            reset_active_tile()
            # Signal launcher.sh to exit its while-true loop
            try:
                write_lifecycle_request(LIFECYCLE_REQUEST_FILE, "parent-exit")
            except (OSError, ValueError):
                pass
            try:
                with open(EXIT_FLAGFILE, "w", encoding="utf-8") as f:
                    f.write("1")
            except OSError:
                pass
            terminate_owned_process(BROWSER_PIDFILE, "browser")
            self.send_response(204)
            self.end_headers()
            # Shutdown the HTTP server so launcher.sh exits cleanly
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if action == "api/timer/start":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            body = self.read_json_body(required=False)
            if body is None:
                return
            minutes = body.get("minutes", cfg.get("timerMinutes", 0))
            if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 180:
                self.json_response({"valid": False, "message": "Invalid duration"}, 400)
                return
            end_time = int(time.time()) + minutes * 60
            save_timer({"end_time": end_time, "totalMinutes": minutes})
            log_runtime_event("timer.started")
            self.json_response({"valid": True, "endTime": end_time, "minutes": minutes})
            return
        if action == "api/timer/stop":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            body = self.read_json_body(required=False)
            if body is None:
                return
            clear_timer()
            log_runtime_event("timer.stopped")
            self.json_response({"valid": True})
            return
        if action == "api/timer/extend":
            cfg = load_cfg()
            body = self.read_json_body(required=False)
            if body is None:
                return
            pin_hash = cfg.get("pinHash", "")
            if pin_hash:
                if pin_attempt_blocked():
                    self.json_response({"valid": False, "message": "Too many attempts"}, 429)
                    return
                pin = body.get("pin", "")
                if not isinstance(pin, str) or not verify_pin(pin_hash, pin):
                    record_pin_failure()
                    self.json_response({"valid": False, "message": "Invalid PIN"}, 403)
                    return
                clear_pin_failures()
            minutes = body.get("minutes", 15)
            if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 180:
                self.json_response({"valid": False, "message": "Invalid duration"}, 400)
                return
            end_time = int(time.time()) + minutes * 60
            save_timer({"end_time": end_time, "totalMinutes": minutes})
            log_runtime_event("timer.extended")
            self.json_response({"valid": True, "endTime": end_time, "minutes": minutes})
            return
        if action == "api/update":
            if not self.require_admin():
                return
            try:
                write_update_trigger(APP_ROOT, UPDATE_SCRIPT)
                log_runtime_event("update.triggered")
                self.json_response({"status": "triggered"})
            except MissingUpdaterError as exc:
                self.json_response(
                    {"status": "error", "message": str(exc)},
                    503,
                )
            except Exception as e:
                self.json_response({"status": "error", "message": str(e)}, 500)
            return
        if action == "api/install-package":
            if not self.require_admin():
                return
            data = self.read_json_body()
            if data is None:
                return
            package = data.get("package", "")
            recs = load_recommendations()
            valid_packages = {r["package"] for r in recs if r.get("package")}
            if not package or package not in valid_packages:
                self.json_response({"status": "error", "message": "Invalid package"}, 400)
                return
            command = f"sudo apt install -y {package}"
            self.json_response({"status": "manual", "command": command})
            return
        if action.startswith("launch/"):
            tile_id = unquote(action.split("/", 1)[1])
            if not tile_id or not re.match(r"^[A-Za-z0-9_-]+$", tile_id):
                self.send_response(400)
                self.end_headers()
                return
            cfg = load_cfg()
            tile = next((t for t in cfg.get("tiles", []) if t.get("id") == tile_id and t.get("visible", True)), None)
            if not tile:
                self.send_response(404)
                self.end_headers()
                return
            availability = tile_availability(cfg, tile_id)
            if not availability["allowed"]:
                self.json_response({
                    "status": "blocked",
                    "reason": availability["reason"],
                }, 403)
                return
            try:
                launch = resolve_tile_action(tile)
            except ValueError as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            log_runtime_event("launch.started", actionType=launch["type"])

            if launch["type"] == "media":
                locations = media_locations()
                if not locations:
                    reset_active_tile()
                    log_runtime_event(
                        "launch.failed",
                        level="warning",
                        actionType="media",
                        result="missing",
                    )
                    self.send_response(302)
                    self.send_header("Location", "/no-media.html")
                    self.end_headers()
                    return
                player = find_media_player()
                command = (
                    media_player_command(player, locations)
                    if player
                    else ["xdg-open", locations[0]]
                )
                try:
                    launch_owned_tile(
                        command,
                        "local",
                        tile_id=tile_id,
                        profile_id=cfg.get("activeProfileId", ""),
                        track_activity=cfg.get("activityTrackingEnabled", False),
                    )
                except OSError:
                    log_runtime_event(
                        "launch.failed",
                        level="warning",
                        actionType="media",
                        result="failure",
                    )
                    self.json_response(
                        {"status": "error", "message": "Media process could not be started"},
                        503,
                    )
                    return
                self.send_response(204)
                self.end_headers()
                return

            if launch["type"] == "web":
                url = launch["url"]
                if launch["mode"] == "embedded":
                    reset_active_tile()
                    activity_token = ""
                    if cfg.get("activityTrackingEnabled", False):
                        activity_token = embedded_activity_sessions().start(
                            cfg.get("activeProfileId", ""),
                            tile_id,
                        )
                    self.send_response(302)
                    self.send_header(
                        "Location",
                        f"/browser.html?url={quote(url, safe='')}&tile={quote(tile_id, safe='')}"
                        f"&activity={quote(activity_token, safe='')}",
                    )
                    self.end_headers()
                    return
                browser = find_browser(cfg)
                command = None
                if browser:
                    command = external_browser_command(browser, url)
                elif shutil.which("xdg-open"):
                    command = ["xdg-open", url]
                else:
                    reset_active_tile()
                    log_runtime_event(
                        "launch.failed",
                        level="warning",
                        actionType="web",
                        result="missing",
                    )
                    self.json_response({"status": "error", "message": "No supported browser found"}, 503)
                    return
                try:
                    launch_owned_tile(
                        command,
                        "external",
                        url=url,
                        tile_id=tile_id,
                        profile_id=cfg.get("activeProfileId", ""),
                        track_activity=cfg.get("activityTrackingEnabled", False),
                    )
                except OSError:
                    log_runtime_event(
                        "launch.failed",
                        level="warning",
                        actionType="web",
                        result="failure",
                    )
                    self.json_response(
                        {"status": "error", "message": "Browser process could not be started"},
                        503,
                    )
                    return
                self.send_response(204)
                self.end_headers()
                return

            clean = launch.get("argv", [])
            if launch["type"] == "none" or not clean:
                reset_active_tile()
                self.send_response(204)
                self.end_headers()
                return
            clean = direct_app_command(clean)
            try:
                # The supervisor still launches argv directly and never invokes a shell.
                launch_owned_tile(
                    clean,
                    "local",
                    tile_id=tile_id,
                    profile_id=cfg.get("activeProfileId", ""),
                    track_activity=cfg.get("activityTrackingEnabled", False),
                )
            except OSError:
                log_runtime_event(
                    "launch.failed",
                    level="warning",
                    actionType="app",
                    result="failure",
                )
                self.json_response(
                    {"status": "error", "message": "Application process could not be started"},
                    503,
                )
                return

            self.send_response(204)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()


def create_server(host="127.0.0.1", port=PORT):
    return http.server.ThreadingHTTPServer((host, port), Handler)


def main():
    try:
        configure_runtime_logging(LOG_FILE)
    except OSError:
        pass
    server_marker = os.path.abspath(__file__)
    if owned_process_alive(PIDFILE, "server", server_marker):
        log_runtime_event("server.duplicate", level="warning")
        close_runtime_logging()
        return
    try:
        with create_server() as httpd:
            write_process_record(
                PIDFILE,
                os.getpid(),
                "server",
                marker=server_marker,
            )
            log_runtime_event("server.started", version=get_version())
            try:
                recovery_attempt = int(
                    os.environ.get("COZY_KIDS_RECOVERY_ATTEMPT", "0")
                )
            except ValueError:
                recovery_attempt = 0
            if 1 <= recovery_attempt <= 100:
                log_runtime_event(
                    "launcher.recovered",
                    attempt=recovery_attempt,
                )
            httpd.serve_forever()
    except Exception as exc:
        log_runtime_event(
            "server.crashed",
            level="critical",
            exceptionType=type(exc).__name__,
        )
        raise
    finally:
        embedded_activity_sessions().finish_all()
        remove_process_record(PIDFILE, expected_pid=os.getpid())
        log_runtime_event("server.stopped")
        close_runtime_logging()


if __name__ == "__main__":
    main()
