"""Validation and public projection for launcher configuration data."""

import copy
import re

from browser_policy import normalize_browser_allowed_origins
from config_store import migrate_config
from parent_auth import is_supported_pin_hash
from profile_config import (
    MAX_PROFILES,
    PROFILE_FIELDS,
    PROFILE_ID_PATTERN,
    active_config,
    profile_summaries,
)
from schedule_rules import validate_app_availability, validate_schedule


MAX_TILES = 200


def _bounded_string(value, field, maximum, allow_empty=True):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{field} is too long")
    return value


def _validate_flat_config(data, existing_pin_hash="", allow_pin_hash=False):
    """Validate the flat active-profile view used by the runtime and web UI."""
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")
    result = copy.deepcopy(data)
    result.pop("pinConfigured", None)
    tiles = result.get("tiles")
    if not isinstance(tiles, list):
        raise ValueError("tiles must be a list")
    if len(tiles) > MAX_TILES:
        raise ValueError(f"A maximum of {MAX_TILES} tiles is supported")

    validated_tiles = []
    seen_ids = set()
    for index, tile in enumerate(tiles):
        if not isinstance(tile, dict):
            raise ValueError(f"tiles[{index}] must be an object")
        tile_id = _bounded_string(tile.get("id"), f"tiles[{index}].id", 80, False)
        if not re.fullmatch(r"[A-Za-z0-9_-]+", tile_id):
            raise ValueError(f"tiles[{index}].id contains invalid characters")
        if tile_id in seen_ids:
            raise ValueError(f"Duplicate tile id: {tile_id}")
        seen_ids.add(tile_id)

        label = _bounded_string(tile.get("label", ""), f"tiles[{index}].label", 200)
        emoji = _bounded_string(tile.get("emoji", ""), f"tiles[{index}].emoji", 32)
        command = tile.get("cmd", [])
        if not isinstance(command, list) or len(command) > 32:
            raise ValueError(f"tiles[{index}].cmd must be a short list")
        clean_command = [
            _bounded_string(part, f"tiles[{index}].cmd", 2048)
            for part in command
        ]
        visible = tile.get("visible", True)
        if not isinstance(visible, bool):
            raise ValueError(f"tiles[{index}].visible must be a boolean")
        validated_tile = {
            **tile,
            "id": tile_id,
            "label": label,
            "emoji": emoji,
            "cmd": clean_command,
            "visible": visible,
        }
        if "browserAllowedOrigins" in tile:
            validated_tile["browserAllowedOrigins"] = normalize_browser_allowed_origins(
                tile["browserAllowedOrigins"]
            )
        validated_tiles.append(validated_tile)
    result["tiles"] = validated_tiles

    for field, maximum in (
        ("title", 200),
        ("theme", 64),
        ("parentLabel", 100),
        ("exitLabel", 100),
        ("shutdownLabel", 100),
        ("customBackground", 2048),
        ("browser", 128),
        ("name", 80),
        ("avatar", 32),
    ):
        if field in result:
            result[field] = _bounded_string(result[field], field, maximum)
    if "name" in result and not result["name"]:
        raise ValueError("name must not be empty")

    if "language" in result and result["language"] not in ("de", "en"):
        raise ValueError("language must be 'de' or 'en'")
    if "layoutMode" in result and result["layoutMode"] not in ("gross", "klein"):
        raise ValueError("layoutMode must be 'gross' or 'klein'")
    if "browser" in result and result["browser"] and not re.fullmatch(
        r"[A-Za-z0-9._+-]+",
        result["browser"],
    ):
        raise ValueError("browser must be an executable name")

    for field, minimum, maximum in (
        ("currentPage", 0, 10_000),
        ("timerMinutes", 0, 180),
        ("timerWarningMinutes", 0, 60),
    ):
        if field in result:
            value = result[field]
            if (
                isinstance(value, bool)
                or not isinstance(value, int)
                or not minimum <= value <= maximum
            ):
                raise ValueError(f"{field} must be between {minimum} and {maximum}")

    for field in (
        "autoScanDone",
        "setupCompleted",
        "activityTrackingEnabled",
        "themeMotionEnabled",
        "themeTimeOfDayEnabled",
        "soundFeedbackEnabled",
        "speechFeedbackEnabled",
        "celebrationEnabled",
        "accessibilityLargeText",
        "accessibilityHighContrast",
        "accessibilityReducedMotion",
        "accessibilityKeyboardFocus",
    ):
        if field in result and not isinstance(result[field], bool):
            raise ValueError(f"{field} must be a boolean")

    if "customColors" in result:
        colors = result["customColors"]
        if not isinstance(colors, dict):
            raise ValueError("customColors must be an object")
        result["customColors"] = {
            _bounded_string(key, "customColors key", 40, False):
            _bounded_string(value, f"customColors.{key}", 128)
            for key, value in colors.items()
        }

    if "favorites" in result:
        favorites = result["favorites"]
        if not isinstance(favorites, list) or len(favorites) > MAX_TILES:
            raise ValueError("favorites must be a short list")
        clean_favorites = []
        for index, tile_id in enumerate(favorites):
            tile_id = _bounded_string(
                tile_id,
                f"favorites[{index}]",
                80,
                False,
            )
            if not PROFILE_ID_PATTERN.fullmatch(tile_id):
                raise ValueError(f"favorites[{index}] contains invalid characters")
            if tile_id in clean_favorites:
                raise ValueError(f"Duplicate favorite id: {tile_id}")
            clean_favorites.append(tile_id)
        result["favorites"] = clean_favorites

    if "appLimits" in result:
        limits = result["appLimits"]
        if not isinstance(limits, dict) or len(limits) > MAX_TILES:
            raise ValueError("appLimits must be an object with a bounded size")
        clean_limits = {}
        for tile_id, minutes in limits.items():
            if not isinstance(tile_id, str) or not PROFILE_ID_PATTERN.fullmatch(tile_id):
                raise ValueError("appLimits contains an invalid tile id")
            if (
                isinstance(minutes, bool)
                or not isinstance(minutes, int)
                or not 0 <= minutes <= 180
            ):
                raise ValueError(f"appLimits.{tile_id} must be between 0 and 180")
            clean_limits[tile_id] = minutes
        result["appLimits"] = clean_limits

    if "weeklySchedule" in result:
        result["weeklySchedule"] = validate_schedule(result["weeklySchedule"])

    if "appAvailability" in result:
        result["appAvailability"] = validate_app_availability(
            result["appAvailability"],
            PROFILE_ID_PATTERN,
            MAX_TILES,
        )

    if allow_pin_hash:
        pin_hash = result.get("pinHash", "")
        if pin_hash and not is_supported_pin_hash(pin_hash):
            raise ValueError("pinHash has an unsupported format")
        result["pinHash"] = pin_hash
    else:
        result["pinHash"] = existing_pin_hash
    return result


def validate_stored_config(data, existing_pin_hash="", allow_pin_hash=False):
    """Validate the complete persisted configuration, including every profile."""
    result, _ = migrate_config(data)
    misplaced_fields = sorted(set(PROFILE_FIELDS).intersection(result))
    if misplaced_fields:
        raise ValueError(
            "Profile fields must be stored inside profiles: "
            + ", ".join(misplaced_fields)
        )
    profiles = result.get("profiles")
    if not isinstance(profiles, list) or not 1 <= len(profiles) <= MAX_PROFILES:
        raise ValueError(f"profiles must contain between 1 and {MAX_PROFILES} entries")

    active_profile_id = result.get("activeProfileId")
    if (
        not isinstance(active_profile_id, str)
        or not PROFILE_ID_PATTERN.fullmatch(active_profile_id)
    ):
        raise ValueError("activeProfileId contains invalid characters")

    global_candidate = {
        key: copy.deepcopy(value)
        for key, value in result.items()
        if key not in ("profiles", "activeProfileId")
    }
    global_candidate["tiles"] = []
    validated_global = _validate_flat_config(
        global_candidate,
        existing_pin_hash=existing_pin_hash,
        allow_pin_hash=allow_pin_hash,
    )
    validated_global.pop("tiles", None)

    validated_profiles = []
    seen_ids = set()
    for index, profile in enumerate(profiles):
        if not isinstance(profile, dict):
            raise ValueError(f"profiles[{index}] must be an object")
        profile_id = profile.get("id")
        if (
            not isinstance(profile_id, str)
            or not PROFILE_ID_PATTERN.fullmatch(profile_id)
        ):
            raise ValueError(f"profiles[{index}].id contains invalid characters")
        if profile_id in seen_ids:
            raise ValueError(f"Duplicate profile id: {profile_id}")
        seen_ids.add(profile_id)

        candidate = copy.deepcopy(profile)
        candidate["configVersion"] = result["configVersion"]
        candidate.setdefault("tiles", [])
        candidate.setdefault("favorites", [])
        candidate.setdefault("appLimits", {})
        candidate.setdefault("weeklySchedule", {"enabled": False, "days": {}})
        candidate.setdefault("appAvailability", {})
        validated = _validate_flat_config(candidate)
        validated.pop("configVersion", None)
        validated.pop("pinHash", None)
        validated["id"] = profile_id
        if not validated.get("name"):
            raise ValueError(f"profiles[{index}].name must not be empty")
        validated_profiles.append(validated)

    if active_profile_id not in seen_ids:
        raise ValueError("activeProfileId does not reference an existing profile")

    validated_global["activeProfileId"] = active_profile_id
    validated_global["profiles"] = validated_profiles
    return validated_global


def validate_config(data, existing_pin_hash="", allow_pin_hash=False):
    """Validate untrusted data and return its legacy-compatible active view."""
    if isinstance(data, dict) and "tiles" in data and data.get("configVersion") == 2:
        return _validate_flat_config(data, existing_pin_hash, allow_pin_hash)
    stored = validate_stored_config(data, existing_pin_hash, allow_pin_hash)
    return active_config(stored)


def public_config(data):
    """Return configuration data without exposing the stored PIN hash."""
    result = active_config(data) if "tiles" not in data else copy.deepcopy(data)
    if "profiles" in result and any(
        isinstance(profile, dict) and "tiles" in profile
        for profile in result["profiles"]
    ):
        result["profiles"] = profile_summaries(data)
    result["pinConfigured"] = bool(result.pop("pinHash", ""))
    return result
