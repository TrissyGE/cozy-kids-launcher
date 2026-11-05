#!/usr/bin/env python3
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

from package_provider import catalog_package_route, detect_native_provider, prepare_install, read_os_release
from package_install import PackageInstaller
from packagekit_backend import InstallError
from daily_budget import DailyBudget
from runtime_locale import render_browser_wrapper
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
    INDIVIDUAL_MEDIA_PLAYER_CANDIDATES,
    MAX_MEDIA_COVER_BYTES,
    SUPPORTED_MEDIA_PATTERNS,
    catalog_item,
    find_media_player as detect_media_player,
    has_media as path_has_media,
    managed_media_sources,
    media_locations as discover_media_locations,
    media_player_command,
    public_media_catalog,
    scan_media_catalog,
    validate_media_roots,
)
from media_state import (
    media_state_payload,
    record_media_play,
    remove_profile_media_state,
    set_media_favorite,
)
from retro_device import retro_device_report
from retro_benchmark import BenchmarkError, RetroBenchmark, attach_benchmark
from retro_games import (
    HUB_COMMAND, HUB_ID, PS1_BIOS_BYTES, PS1_CORE_UPLOAD_BYTES, PS1_CORE_VERSION, ROM_SYSTEMS,
    approved_retro_ids, download_ps1_core, emulator_binary, emulator_command, import_ps1_bios,
    import_ps1_core, ps1_bios_status, ps1_core_path, ps1_core_supported, retro_cover, retro_hub,
    retro_id, scan_retro_games,
)
from retro_saves import backup_retro_saves, remove_retro_saves, retro_save_ids
from media_resume import (
    prepare_profile_resume_directory,
    remove_profile_resume_directory,
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
from schedule_rules import availability_summary, next_profile_opening, tile_availability
from speech_feedback import SpeechFeedback
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
    read_update_track,
    read_version,
    resolve_update_status,
    version_is_newer,
    write_update_track,
    write_update_trigger,
)

HOME = os.path.expanduser("~")
APP_ROOT = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(APP_ROOT, "version")
UPDATE_SCRIPT = os.path.join(APP_ROOT, "update.sh")
UPDATE_CHANNEL_FILE = os.path.join(APP_ROOT, "update-channel")
LATEST_RELEASE_API = os.environ.get(
    "COZY_KIDS_RELEASE_API_URL",
    "https://api.github.com/repos/TrissyGE/cozy-kids-launcher/releases/latest",
)
PREVIEW_RELEASE_API = os.environ.get(
    "COZY_KIDS_PREVIEW_API_URL",
    LATEST_RELEASE_API.removesuffix("/latest") + "?per_page=100",
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
BUDGET_FILE = os.path.join(HOME, ".local", "state", "{{APP_ID}}", "daily-budget.json")
_family_lock = threading.RLock()
_budget = None
MEDIA_STATE_FILE = os.path.join(HOME, ".local", "state", "{{APP_ID}}", "media.json")
MEDIA_RESUME_ROOT = os.path.join(
    HOME,
    ".local",
    "state",
    "{{APP_ID}}",
    "media-resume",
)
MEDIA_SESSION_SCRIPT = os.path.join(APP_ROOT, "media_session.py")
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
_speech_feedback_lock = threading.Lock()
_speech_feedback = None


def has_media(path):
    return path_has_media(path, patterns=EXTS)


def load_stored_cfg():
    data = read_config(CFG)
    data, migrated = migrate_config(data)
    recs = load_recommendations()
    rec_by_command = {}
    for rec in recs:
        if rec.get("cmd"):
            rec_by_command[(rec["cmd"][0],)] = rec["cmd"]
            for alt in rec.get("alt_cmds", []):
                rec_by_command[(alt,)] = rec["cmd"]
            for legacy in rec.get("legacy_cmds", []):
                rec_by_command[tuple(legacy)] = rec["cmd"]
    for profile in data.get("profiles", []):
        for tile in profile.get("tiles", []):
            cmd = tile.get("cmd", [])
            if len(cmd) == 1 and cmd[0] in LEGACY_WEB_ACTION_MIGRATIONS:
                tile["cmd"] = [LEGACY_WEB_ACTION_MIGRATIONS[cmd[0]]]
                cmd = tile["cmd"]
                migrated = True
            if (
                isinstance(cmd, list)
                and all(isinstance(part, str) for part in cmd)
                and tuple(cmd) in rec_by_command
                and cmd != rec_by_command[tuple(cmd)]
            ):
                # Migrate only exact known defaults. Matching the executable
                # alone silently discarded Parent-selected flags on every read.
                tile["cmd"] = list(rec_by_command[tuple(cmd)])
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
    return discover_apps(HOME, language=load_cfg().get("language", "en"))


def media_location():
    locations = media_locations()
    return locations[0] if locations else None


def media_locations():
    """Return every configured media directory that contains supported files."""
    return discover_media_locations(
        (VIDEOS, MUSIC, ALT_MUSIC),
        has_media_fn=has_media,
    )


def media_catalog(cfg):
    """Return the bounded library and the availability snapshot used to build it."""
    roots, sources = managed_media_sources(cfg.get("mediaRoots", []))
    entries, truncated = scan_media_catalog((VIDEOS, MUSIC, ALT_MUSIC, *roots))
    return entries, truncated, sources


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


def configured_feedback_tile(cfg, tile_id):
    """Resolve one visible tile without accepting a client-provided label."""
    if (
        not isinstance(tile_id, str)
        or len(tile_id) > 80
        or not re.fullmatch(r"[A-Za-z0-9_-]+", tile_id)
    ):
        return None
    return next(
        (
            tile
            for tile in cfg.get("tiles", [])
            if tile.get("id") == tile_id and tile.get("visible", True)
        ),
        None,
    )


def find_media_player(candidates=None):
    if candidates is None:
        return detect_media_player(which=shutil.which)
    return detect_media_player(candidates=candidates, which=shutil.which)


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


def updates_are_package_managed():
    return os.path.lexists(os.path.join(APP_ROOT, "package-managed"))


def get_update_status(timeout=5):
    if updates_are_package_managed():
        version = get_version()
        return {"installedVersion": version, "latestVersion": version,
                "source": "package-manager", "updateAvailable": False}
    return resolve_update_status(
        get_version(),
        LATEST_RELEASE_API,
        LEGACY_VERSION_URL,
        UPDATE_CHANNEL_FILE,
        timeout=timeout,
        fetch_json=_fetch_remote_json,
        fetch_text=_fetch_remote_text,
        preview_api_url=PREVIEW_RELEASE_API,
        track_file=Path(CFG).with_name("update-track"),
    )


def load_recommendations():
    if not os.path.isfile(RECOMMENDATIONS_FILE):
        return []
    try:
        with open(RECOMMENDATIONS_FILE, "r", encoding="utf-8") as fh:
            recs = json.load(fh)
    except Exception:
        return []
    release = read_os_release()
    provider = detect_native_provider(release)
    from flatpak_catalog import catalog_routes
    flatpaks = catalog_routes()
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
        entry = {**rec, "installed": installed}
        if "package" in rec or "packages" in rec:
            entry["packageRoute"] = catalog_package_route(rec, release, provider)
        if rec.get("id") in flatpaks:
            entry["flatpakRoute"] = flatpaks[rec["id"]]
        result.append(entry)
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


def speech_feedback():
    global _speech_feedback
    with _speech_feedback_lock:
        if _speech_feedback is None:
            _speech_feedback = SpeechFeedback()
        return _speech_feedback


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
    finish_budget_session()
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
    finish_budget_session()
    process = application_launcher().launch_owned_tile(
        command,
        mode,
        url=url,
        tile_id=tile_id,
        profile_id=profile_id,
        track_activity=track_activity,
    )
    try:
        budget().begin(profile_id, tile_id, load_cfg().get("dailyBudgetMinutes", 0),
                       alive=lambda: process.poll() is None)
    except (OSError, ValueError):
        application_launcher().reset_active_tile()
        raise OSError("Daily budget could not be reserved") from None
    return process


def budget():
    global _budget
    if _budget is None or _budget.path != Path(BUDGET_FILE):
        _budget = DailyBudget(BUDGET_FILE)
    return _budget


def finish_budget_session():
    try:
        budget().finish()
    except (OSError, ValueError):
        log_runtime_event("budget.storage.unavailable", level="warning")


def retain_profile_budgets(stored):
    try:
        budget().retain_profiles({profile["id"] for profile in stored["profiles"]})
    except (OSError, ValueError):
        log_runtime_event("budget.storage.unavailable", level="warning")


def budget_status(cfg):
    return budget().status(cfg.get("activeProfileId", ""), cfg.get("dailyBudgetMinutes", 0))


def family_tile_availability(cfg, tile_id):
    state = budget_status(cfg)
    if state.get("enabled") and not state.get("remainingSeconds"):
        return {"allowed": False, "reason": "budget_unavailable" if state.get("unavailable") else "daily_budget"}
    return tile_availability(cfg, tile_id)


def budget_monitor(stop):
    while not stop.wait(1):
        with _family_lock:
            if _budget is None or not _budget.session:
                continue
            cfg = load_cfg()
            try:
                should_stop = budget().tick(cfg["activeProfileId"], cfg.get("dailyBudgetMinutes", 0))
            except (OSError, ValueError):
                finish_budget_session()
                should_stop = True
            if should_stop:
                # The overlay notices the stopped process and restores launcher focus.
                stop_active_tile()


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

    def parse_request(self):
        if not super().parse_request():
            return False
        port = self.server.server_address[1]
        local_hosts = ("localhost", "127.0.0.1", "[::1]")
        allowed = {f"{host}:{port}" for host in local_hosts}
        if port == 80:
            allowed.update(local_hosts)
        hosts = self.headers.get_all("Host", [])
        if len(hosts) != 1 or hosts[0].lower() not in allowed:
            self.close_connection = True
            self.send_error(400, "Invalid loopback Host")
            return False
        return True

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
        if request_url.path == "/api/packages/status":
            if self.require_admin():
                self.json_response(self.server.package_installer.snapshot())
            return
        if request_url.path == "/browser.html":
            try:
                cfg = load_cfg()
                self.browser_content_security_policy = browser_wrapper_policy(
                    cfg,
                    request_url.query,
                )
                if cfg.get("dailyBudgetMinutes"):
                    params = parse_qs(request_url.query, max_num_fields=8)
                    tile = params.get("tile", [""])[0]
                    token = params.get("budget", [""])[0]
                    with _family_lock:
                        if not budget().matches(token, cfg["activeProfileId"], tile):
                            self.send_error(403)
                            return
            except ValueError:
                self.send_error(404)
                return
            try:
                template = (Path(APP_ROOT) / "browser.html").read_text(encoding="utf-8")
                page = render_browser_wrapper(template, cfg.get("language")).encode("utf-8")
            except (OSError, ValueError):
                self.send_error(503)
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(page)))
            self.end_headers()
            self.wfile.write(page)
            return
        if request_url.path == "/api/media/roots":
            cfg = load_cfg()
            if self.require_admin(cfg):
                return self.json_response({"roots": cfg.get("mediaRoots", [])})
            return
        if request_url.path == "/api/retro/saves":
            return self.get_retro_saves(parse_qs(request_url.query))
        if request_url.path == "/api/retro/device":
            if self.require_admin():
                core_ready = bool(ps1_core_path(os.path.dirname(MEDIA_STATE_FILE)))
                report = retro_device_report(load_recommendations(), core_ready)
                return self.json_response(attach_benchmark(report, self.server.retro_benchmark.snapshot()))
            return
        if request_url.path == "/api/retro/benchmark":
            if self.require_admin():
                return self.json_response(self.server.retro_benchmark.snapshot())
            return
        if request_url.path == "/api/retro/games":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            roots = cfg.get("retroRoots", [])
            games, unavailable, truncated = scan_retro_games(roots)
            approved = approved_retro_ids(cfg)
            playlist_discs = {disc for game in games.values() for disc in game.get("discPaths", ())}
            visible_games = (game for game in games.values()
                             if game["path"] not in playlist_discs or game["id"] in approved)
            return self.json_response({
                "roots": roots,
                "games": sorted(visible_games, key=lambda game: (game["title"].casefold(), game["path"])),
                "unavailable": unavailable,
                "truncated": truncated,
                "enabled": bool(retro_hub(cfg)),
                "covers": (retro_hub(cfg, require_visible=False) or {}).get("retroCovers", False),
                "approvedIds": list(approved),
                "ps1Bios": ps1_bios_status(os.path.dirname(MEDIA_STATE_FILE)),
                "ps1Runtime": {
                    "retroarch": bool(shutil.which("retroarch")),
                    "core": bool(ps1_core_path(os.path.dirname(MEDIA_STATE_FILE))),
                    "coreVersion": PS1_CORE_VERSION,
                    "coreSupported": ps1_core_supported(),
                },
            })
        if request_url.path in ("/api/retro/library", "/api/retro/cover"):
            cfg = load_cfg()
            hub = retro_hub(cfg)
            if not hub:
                return self.json_response({"status": "unavailable"}, 404)
            games, unavailable, truncated = scan_retro_games(cfg.get("retroRoots", []))
            approved = approved_retro_ids(cfg)
            if request_url.path == "/api/retro/cover":
                ids = parse_qs(request_url.query).get("id", [])
                game = games.get(ids[0]) if len(ids) == 1 and ids[0] in approved else None
                payload = retro_cover(game, hub.get("retroCovers", False)) if game else b""
                if not payload:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
                return
            return self.json_response({
                "items": [
                    {"id": identifier, "title": approved[identifier]["label"],
                     "system": ROM_SYSTEMS[games[identifier]["romExtension"]][2],
                     "coverUrl": f"/api/retro/cover?id={identifier}"}
                    for identifier in sorted(games.keys() & approved.keys(),
                                             key=lambda key: (approved[key]["label"].casefold(), key))
                ],
                "unavailableSources": unavailable,
                "truncated": truncated,
            })
        if request_url.path == "/api/media/sources":
            _, sources = managed_media_sources(load_cfg().get("mediaRoots", []))
            return self.json_response(sources)
        if request_url.path == "/api/media":
            cfg = load_cfg()
            entries, truncated, sources = media_catalog(cfg)
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
                **sources,
                **state,
            })
        if request_url.path == "/api/media/cover":
            query = parse_qs(request_url.query, keep_blank_values=True)
            media_ids = query.get("id", [])
            cover_versions = query.get("v", ["0"])
            if (
                len(media_ids) != 1
                or set(query) - {"id", "v"}
                or len(cover_versions) != 1
                or not re.fullmatch(r"[0-9]{1,16}", cover_versions[0])
            ):
                self.send_error(404)
                return
            entries, _, _ = media_catalog(load_cfg())
            return self.media_cover_response(catalog_item(entries, media_ids[0]))
        if request_url.path == "/api/config":
            cfg = load_cfg()
            parent = request_url.query == "parent=1"
            if parent and not self.require_admin(cfg):
                return
            result = public_config(cfg)
            if cfg.get("pinHash") and not parent:
                for field in ("weeklySchedule", "appAvailability", "appLimits", "dailyBudgetMinutes"):
                    result.pop(field, None)
            return self.json_response(result)
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
        if self.path == "/api/update/channel":
            if self.require_admin():
                if updates_are_package_managed():
                    return self.json_response({"managed": True})
                self.json_response({"channel": read_update_track(Path(CFG).with_name("update-track"))})
            return
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
            return self.json_response({
                "shutdownAvailable": shutdown_ok,
                "speechFeedbackAvailable": speech_feedback().available(),
            })
        if self.path == "/api/browsers":
            return self.json_response(
                browser_statuses(BROWSER_CANDIDATES, which=shutil.which)
            )
        if self.path == "/api/timer/status":
            return self.json_response(timer_status(load_cfg()))
        if self.path == "/api/availability/status":
            with _family_lock:
                cfg = load_cfg()
                result = availability_summary(cfg)
                state = budget_status(cfg)
                if state.get("enabled"):
                    result["budget"] = state
                    if not state.get("remainingSeconds"):
                        result.update(profileAllowed=False,
                                      reason="budget_unavailable" if state.get("unavailable") else "daily_budget")
                        result["blockedTileIds"] = [tile["id"] for tile in cfg.get("tiles", [])]
                if not result["profileAllowed"]:
                    earliest = state.get("nextAvailableAt") if result.get("reason") == "daily_budget" else time.time()
                    if not state.get("unavailable") and earliest is not None:
                        next_opening = next_profile_opening(cfg.get("weeklySchedule"), earliest)
                        if next_opening is not None:
                            result["nextAllowedAt"] = next_opening
            return self.json_response(result)
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

    def get_retro_saves(self, query):
        if not self.request_has_local_origin():
            return self.json_response({"status": "invalid"}, 403)
        with ExitStack() as resources:
            with _family_lock:
                cfg = load_cfg()
                if not self.require_admin(cfg):
                    return
                profile_id = cfg["activeProfileId"]
                root = os.path.join(os.path.dirname(MEDIA_STATE_FILE), "retro")
                try:
                    if "gameId" not in query:
                        labels = {retro_id(tile["cmd"]): tile["label"] for tile in cfg["tiles"]}
                        games = [{"id": identifier, "title": labels.get(identifier, identifier)}
                                 for identifier in retro_save_ids(root, profile_id)]
                        games.sort(key=lambda item: (item["title"].casefold(), item["id"]))
                        return self.json_response({"profileId": profile_id, "games": games})
                    if query.get("profileId") != [profile_id] or len(query["gameId"]) != 1:
                        return self.json_response({"status": "invalid"}, 400)
                    if self.retro_save_busy():
                        return self.json_response({"status": "busy"}, 409)
                    identifier = query["gameId"][0]
                    backup = resources.enter_context(tempfile.TemporaryFile())
                    backup_retro_saves(root, profile_id, identifier, backup)
                except FileNotFoundError:
                    return self.json_response({"status": "unavailable"}, 404)
                except ValueError:
                    return self.json_response({"status": "invalid"}, 400)
                except OSError:
                    return self.json_response({"status": "unavailable"}, 503)
            size = backup.tell()
            backup.seek(0)
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", f'attachment; filename="cozy-retro-{identifier}.zip"')
            self.send_header("Content-Length", str(size))
            self.end_headers()
            self.copyfile(backup, self.wfile)

    @staticmethod
    def retro_save_busy():
        launcher = application_launcher()
        return owned_process_alive(launcher.tile_process_pidfile, "tile-process", launcher.process_supervisor)

    def do_POST(self):
        if not self.request_has_local_origin():
            log_runtime_event("request.rejected", level="warning", statusCode=403)
            self.json_response({"status": "error", "message": "Cross-site request rejected"}, 403)
            return
        action = self.path.strip("/")
        if action.startswith("launch/") or action in {
            "api/media/play", "api/media/roots", "api/retro/games", "api/retro/approve",
            "api/retro/settings", "api/retro/play", "api/retro/saves",
            "api/profiles/create", "api/profiles/select", "api/profiles/delete",
            "api/save-config", "api/import-config", "api/backups/restore", "api/budget/session",
            "api/verify-pin", "api/pin/set", "api/pin/remove",
            "api/budget/extend", "exit-kids",
        }:
            with _family_lock:
                return self.dispatch_post(action)
        return self.dispatch_post(action)

    def dispatch_post(self, action, retro_from_hub=False):
        if action in {"api/retro/benchmark", "api/retro/benchmark/cancel", "api/retro/benchmark/clear"}:
            if not self.require_admin():
                return
            body = self.read_json_body()
            if body is None:
                return
            manager = self.server.retro_benchmark
            try:
                if action == "api/retro/benchmark":
                    if body != {"system": "ps1"}:
                        return self.json_response({"status": "invalid"}, 400)
                    root = os.path.dirname(MEDIA_STATE_FILE)
                    report = retro_device_report(load_recommendations(), bool(ps1_core_path(root)))
                    row = next(row for row in report["systems"] if row["catalog"] == "retroarch")
                    with _family_lock:
                        if self.retro_save_busy() or self.server.package_installer.snapshot()["status"] in {"checking", "installing"}:
                            return self.json_response({"status": "busy"}, 409)
                        if row["status"] == "incompatible":
                            return self.json_response({"status": "unavailable"}, 409)
                        return self.json_response(manager.start(root, row["resultKey"]), 202)
                if set(body) != {"jobId"} or not isinstance(body["jobId"], str):
                    return self.json_response({"status": "invalid"}, 400)
                result = manager.cancel(body["jobId"]) if action.endswith("/cancel") else manager.clear(body["jobId"])
                return self.json_response(result)
            except BenchmarkError as error:
                return self.json_response({"status": error.code}, 409)
            except (OSError, ValueError):
                return self.json_response({"status": "unavailable"}, 503)
        if action == "api/retro/saves":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            body = self.read_json_body()
            if body is None:
                return
            profile_id = cfg["activeProfileId"]
            identifier = body.get("gameId")
            if body.get("profileId") != profile_id or not isinstance(identifier, str) or body.get("confirm") is not True:
                return self.json_response({"status": "invalid"}, 400)
            if self.retro_save_busy():
                return self.json_response({"status": "busy"}, 409)
            root = os.path.join(os.path.dirname(MEDIA_STATE_FILE), "retro")
            try:
                remove_retro_saves(root, profile_id, identifier)
            except FileNotFoundError:
                return self.json_response({"status": "unavailable"}, 404)
            except ValueError:
                return self.json_response({"status": "invalid"}, 400)
            except OSError:
                return self.json_response({"status": "unavailable"}, 503)
            return self.json_response({"status": "ok"})
        if action == "api/retro/ps1-core-download":
            if not self.require_admin():
                return
            try:
                download_ps1_core(os.path.dirname(MEDIA_STATE_FILE))
            except ValueError:
                return self.json_response({"status": "unreviewed"}, 409)
            except OSError:
                return self.json_response({"status": "unavailable"}, 503)
            return self.json_response({"status": "ok", "coreVersion": PS1_CORE_VERSION})
        if action in ("api/retro/ps1-bios", "api/retro/ps1-core"):
            if not self.require_admin(load_cfg()):
                return
            bios = action == "api/retro/ps1-bios"
            maximum = PS1_BIOS_BYTES if bios else PS1_CORE_UPLOAD_BYTES
            if self.headers.get_content_type() != "application/octet-stream":
                return self.json_response({"status": "invalid"}, 415)
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self.json_response({"status": "invalid"}, 400)
            if not 0 < length <= maximum or (bios and length != maximum):
                return self.json_response({"status": "invalid"}, 413 if length > maximum else 400)
            self.connection.settimeout(10)
            state_root = os.path.dirname(MEDIA_STATE_FILE)
            try:
                payload = self.rfile.read(length)
                if len(payload) != length:
                    raise ValueError("Truncated PS1 upload")
                if bios:
                    import_ps1_bios(state_root, payload)
                else:
                    import_ps1_core(state_root, payload)
            except ValueError:
                return self.json_response({"status": "invalid"}, 400)
            except OSError:
                return self.json_response({"status": "unavailable"}, 503)
            result = {"ps1Bios": ps1_bios_status(state_root)} if bios else {"coreVersion": PS1_CORE_VERSION}
            return self.json_response({"status": "ok", **result})
        if action == "api/retro/play":
            body = self.read_json_body()
            if body is None:
                return
            cfg = load_cfg()
            if not retro_hub(cfg):
                return self.json_response({"status": "unavailable"}, 404)
            availability = family_tile_availability(cfg, HUB_ID)
            if not availability["allowed"]:
                return self.json_response({"status": "blocked", "reason": availability["reason"]}, 403)
            identifier = body.get("gameId")
            approved = approved_retro_ids(cfg)
            if not isinstance(identifier, str) or identifier not in approved:
                return self.json_response({"status": "unavailable"}, 404)
            return self.dispatch_post("launch/" + approved[identifier]["id"], retro_from_hub=True)
        if action == "api/retro/settings":
            cfg = load_cfg()
            if not self.require_admin(cfg):
                return
            body = self.read_json_body()
            if body is None:
                return
            if (body.get("profileId") != cfg["activeProfileId"]
                    or type(body.get("enabled")) is not bool or type(body.get("covers")) is not bool):
                return self.json_response({"status": "invalid"}, 400)
            tile = retro_hub(cfg, require_visible=False)
            if tile is None:
                if any(item["id"] == HUB_ID for item in cfg["tiles"]):
                    return self.json_response({"status": "conflict"}, 409)
                tile = {"id": HUB_ID, "label": "RetroGameCorner", "emoji": "🎮", "cmd": [HUB_COMMAND]}
                cfg["tiles"].append(tile)
            tile.update(visible=body["enabled"], retroCovers=body["covers"])
            try:
                save_cfg(cfg)
            except (OSError, ValueError):
                return self.json_response({"status": "error"}, 400)
            return self.json_response({"tile": tile})
        if action == "api/retro/approve":
            stored = load_stored_cfg()
            if not self.require_admin(stored):
                return
            body = self.read_json_body()
            if not isinstance(body, dict):
                return
            cfg = active_config(stored)
            identifier = body.get("gameId")
            if not isinstance(identifier, str) or body.get("profileId") != cfg["activeProfileId"]:
                return self.json_response({"status": "invalid"}, 400)
            games, _, _ = scan_retro_games(stored.get("retroRoots", []))
            game = games.get(identifier)
            if not game:
                return self.json_response({"status": "unavailable"}, 404)
            tile_id = f"retro-{identifier}"
            tile = next((tile for tile in cfg["tiles"] if tile["id"] == tile_id), None)
            if tile is None:
                if not retro_hub(cfg, require_visible=False):
                    if any(item["id"] == HUB_ID for item in cfg["tiles"]):
                        return self.json_response({"status": "conflict"}, 409)
                    cfg["tiles"].append({
                        "id": HUB_ID, "label": "RetroGameCorner", "emoji": "🎮",
                        "cmd": [HUB_COMMAND], "visible": False,
                    })
                tile = {
                    "id": tile_id, "label": game["title"], "emoji": "🎮",
                    "cmd": [f"special:retro:{identifier}"], "visible": True,
                }
                cfg["tiles"].append(tile)
                try:
                    save_cfg(cfg)
                except (OSError, ValueError):
                    return self.json_response({"status": "error"}, 400)
            elif tile["cmd"] != [f"special:retro:{identifier}"]:
                return self.json_response({"status": "conflict"}, 409)
            elif not tile["visible"]:
                tile["visible"] = True
                try:
                    save_cfg(cfg)
                except (OSError, ValueError):
                    return self.json_response({"status": "error"}, 400)
            return self.json_response({"tile": tile, "hub": retro_hub(cfg, require_visible=False)})
        if action in ("api/media/roots", "api/retro/games"):
            stored = load_stored_cfg()
            if not self.require_admin(stored):
                return
            body = self.read_json_body()
            if body is None:
                return
            try:
                roots = body.get("roots") if isinstance(body, dict) else None
                field = "retroRoots" if action == "api/retro/games" else "mediaRoots"
                stored[field] = validate_media_roots(roots)
                stored = save_stored_cfg(stored)
            except ValueError:
                return self.json_response({"status": "invalid"}, 400)
            except OSError:
                return self.json_response({"status": "error"}, 503)
            return self.json_response({"roots": stored[field]})
        if action in ("api/budget/session", "api/budget/extend"):
            body = self.read_json_body()
            if body is None:
                return
            cfg = load_cfg()
            profile = cfg["activeProfileId"]
            if action == "api/budget/session":
                if set(body) != {"token", "finished"} or type(body["finished"]) is not bool:
                    return self.json_response({"valid": False}, 400)
                try:
                    valid = budget().heartbeat(body["token"], profile, body["finished"])
                except (OSError, ValueError):
                    valid = False
                return self.json_response({"valid": valid})
            if set(body) != {"pin", "minutes"}:
                return self.json_response({"valid": False}, 400)
            pin_hash = cfg.get("pinHash", "")
            if not pin_hash:
                return self.json_response({"valid": False}, 403)
            if pin_attempt_blocked():
                return self.json_response({"valid": False}, 429)
            pin = body["pin"]
            if not isinstance(pin, str) or not verify_pin(pin_hash, pin):
                record_pin_failure()
                return self.json_response({"valid": False}, 403)
            clear_pin_failures()
            state = budget_status(cfg)
            if not state.get("enabled") or state.get("remainingSeconds") or state.get("unavailable"):
                return self.json_response({"valid": False}, 409)
            try:
                state = budget().extend(profile, cfg.get("dailyBudgetMinutes", 0), body["minutes"])
            except ValueError:
                return self.json_response({"valid": False}, 409)
            except OSError:
                return self.json_response({"valid": False}, 503)
            return self.json_response({"valid": True, "budget": state})
        if action in ("api/packages/prepare", "api/packages/install", "api/packages/confirm"):
            if not self.require_admin():
                return
            body = self.read_json_body()
            if body is None:
                return
            try:
                if action.endswith("/prepare") and "appId" in body and set(body) <= {"appId", "operation", "source"}:
                    args = (body["appId"], load_recommendations(), body.get("operation", "install"))
                    result = self.server.package_installer.prepare(*args, **({"source": body["source"]} if "source" in body else {}))
                elif action in ("api/packages/install", "api/packages/confirm") and set(body) == {"jobId", "confirmationToken"}:
                    result = self.server.package_installer.start(
                        body["jobId"], body["confirmationToken"],
                        expected_operation="install" if action.endswith("/install") else None,
                    )
                else:
                    raise ValueError("Invalid package action")
                self.json_response(result, 202)
            except ValueError:
                self.json_response({"status": "error", "error": "invalid"}, 400)
            except InstallError as error:
                self.json_response({"status": "error", "error": error.code}, 409)
            return
        if action == "api/feedback/speak":
            body = self.read_json_body()
            if body is None:
                return
            if set(body) != {"tileId"}:
                self.json_response(
                    {"status": "error", "message": "Only a tile identifier is accepted"},
                    400,
                )
                return
            cfg = load_cfg()
            if cfg.get("speechFeedbackEnabled") is not True:
                self.json_response({"status": "disabled"})
                return
            tile = configured_feedback_tile(cfg, body.get("tileId"))
            if tile is None:
                self.send_response(404)
                self.end_headers()
                return
            try:
                status = speech_feedback().speak(
                    tile.get("label", ""),
                    cfg.get("language", "en"),
                )
            except ValueError:
                self.json_response(
                    {"status": "error", "message": "Tile label cannot be spoken"},
                    400,
                )
                return
            self.json_response({"status": status})
            return
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
            availability = family_tile_availability(cfg, tile_id)
            if not availability["allowed"]:
                self.json_response({
                    "status": "blocked",
                    "reason": availability["reason"],
                }, 403)
                return
            entries, _, _ = media_catalog(cfg)
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
            availability = family_tile_availability(cfg, tile_id)
            if not availability["allowed"]:
                self.json_response({
                    "status": "blocked",
                    "reason": availability["reason"],
                }, 403)
                return
            entries, _, _ = media_catalog(cfg)
            item = catalog_item(entries, body.get("mediaId"))
            if not item:
                self.send_response(404)
                self.end_headers()
                return
            player = find_media_player(INDIVIDUAL_MEDIA_PLAYER_CANDIDATES)
            if player:
                self.server.retro_benchmark.cancel()
                resume_directory = None
                profile_id = cfg.get("activeProfileId", "")
                if player in ("mpv", "vlc"):
                    try:
                        resume_directory = prepare_profile_resume_directory(
                            MEDIA_RESUME_ROOT,
                            profile_id,
                        )
                    except (OSError, ValueError):
                        log_runtime_event(
                            "media.resume.unavailable",
                            level="warning",
                            actionType="media",
                        )
                command = media_player_command(
                    player,
                    [item["path"]],
                    resume_directory=resume_directory,
                )
                if (
                    player == "vlc"
                    and resume_directory
                    and os.path.isfile(MEDIA_SESSION_SCRIPT)
                ):
                    command = [
                        sys.executable,
                        MEDIA_SESSION_SCRIPT,
                        "--resume-root",
                        MEDIA_RESUME_ROOT,
                        "--profile-id",
                        profile_id,
                        "--media-id",
                        item["id"],
                        "--media-path",
                        item["path"],
                        "--",
                        *command,
                    ]
            elif not cfg.get("dailyBudgetMinutes") and shutil.which("xdg-open"):
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
                    source_profile_id=body.get("sourceProfileId"),
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
                reset_active_tile()
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
                budget().forget(body.get("profileId"))
                remove_profile_media_state(MEDIA_STATE_FILE, body.get("profileId"))
                remove_profile_resume_directory(
                    MEDIA_RESUME_ROOT,
                    body.get("profileId"),
                )
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
            if data.get("dailyBudgetMinutes", 0) != cfg.get("dailyBudgetMinutes", 0):
                reset_active_tile()
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
                reset_active_tile()
                retain_profile_budgets(imported)
                write_browser_override(active_config(imported))
            except (OSError, ValueError) as exc:
                self.json_response({"status": "error", "message": str(exc)}, 400)
                return
            pin_changed = imported.get("pinHash", "") != cfg.get("pinHash", "")
            if pin_changed:
                clear_admin_sessions()
            log_runtime_event(
                "config.imported",
                configVersion=imported.get("configVersion", CURRENT_CONFIG_VERSION),
            )
            self.json_response({"status": "ok", "requiresPin": pin_changed and bool(imported.get("pinHash"))})
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
                reset_active_tile()
                retain_profile_budgets(restored)
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
        if action == "api/update/channel":
            if not self.require_admin():
                return
            if updates_are_package_managed():
                return self.json_response({"status": "package-managed"}, 409)
            body = self.read_json_body()
            if body is None:
                return
            try:
                write_update_track(Path(CFG).with_name("update-track"), body.get("channel"))
            except ValueError:
                return self.json_response({"status": "error"}, 400)
            except OSError:
                return self.json_response({"status": "error"}, 503)
            return self.json_response({"channel": body["channel"]})
        if action == "api/update":
            if not self.require_admin():
                return
            if updates_are_package_managed():
                return self.json_response({"status": "package-managed"}, 409)
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
            try:
                plan = prepare_install(package, load_recommendations())
            except ValueError as error:
                self.json_response({"status": "error", "message": str(error)}, 400)
            else:
                self.json_response(plan)
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
            availability = family_tile_availability(cfg, tile_id)
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
            self.server.retro_benchmark.cancel()
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
                if not player and cfg.get("dailyBudgetMinutes"):
                    self.json_response({"status": "error", "message": "No supervised media player found"}, 503)
                    return
                command = media_player_command(player, locations) if player else ["xdg-open", locations[0]]
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
                    try:
                        budget_token = budget().begin(cfg["activeProfileId"], tile_id, cfg.get("dailyBudgetMinutes", 0))
                    except (OSError, ValueError):
                        self.json_response({"status": "blocked", "reason": "budget_unavailable"}, 403)
                        return
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
                        f"&activity={quote(activity_token, safe='')}"
                        + (f"&budget={quote(budget_token, safe='')}" if budget_token else ""),
                    )
                    self.end_headers()
                    return
                browser = find_browser(cfg)
                command = None
                if browser:
                    command = external_browser_command(browser, url)
                elif not cfg.get("dailyBudgetMinutes") and shutil.which("xdg-open"):
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
            if launch["type"] == "retro":
                if retro_hub(cfg, require_visible=False) and not retro_from_hub:
                    return self.json_response({"status": "unavailable"}, 404)
                games, _, _ = scan_retro_games(cfg.get("retroRoots", []))
                game = games.get(launch["id"])
                emulator = shutil.which(emulator_binary(game)) if game else None
                if not emulator:
                    return self.json_response({"status": "unavailable"}, 503)
                try:
                    clean = emulator_command(
                        emulator, game,
                        os.path.join(os.path.dirname(MEDIA_STATE_FILE), "retro"),
                        cfg["activeProfileId"],
                    )
                except (OSError, ValueError):
                    return self.json_response({"status": "unavailable"}, 503)
            if cfg.get("dailyBudgetMinutes") and clean and os.path.basename(clean[0]) in {"xdg-open", "gio"}:
                self.json_response({"status": "error", "message": "This opener cannot be supervised"}, 503)
                return
            if launch["type"] == "none" or not clean:
                reset_active_tile()
                self.send_response(204)
                self.end_headers()
                return
            try:
                # Keep the legacy fullscreen request until the owned supervisor
                # can replace the wrapper and confirm the compositor's state.
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


class LauncherHTTPServer(http.server.ThreadingHTTPServer):
    def server_close(self):
        if hasattr(self, "retro_benchmark"):
            self.retro_benchmark.close()
        super().server_close()


def create_server(host="127.0.0.1", port=PORT):
    server = LauncherHTTPServer((host, port), Handler)
    server.package_installer = PackageInstaller(os.path.join(os.path.dirname(LOG_FILE), "package-install.json"))
    server.retro_benchmark = RetroBenchmark(os.path.join(os.path.dirname(LOG_FILE), "retro-benchmark.json"))
    return server


def main():
    stop_budget = threading.Event()
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
            threading.Thread(target=budget_monitor, args=(stop_budget,), daemon=True).start()
            httpd.serve_forever()
    except Exception as exc:
        log_runtime_event(
            "server.crashed",
            level="critical",
            exceptionType=type(exc).__name__,
        )
        raise
    finally:
        stop_budget.set()
        with _family_lock:
            finish_budget_session()
        embedded_activity_sessions().finish_all()
        if _speech_feedback is not None:
            _speech_feedback.close()
        remove_process_record(PIDFILE, expected_pid=os.getpid())
        log_runtime_event("server.stopped")
        close_runtime_logging()


if __name__ == "__main__":
    main()
