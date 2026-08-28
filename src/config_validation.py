"""Validation and public projection for launcher configuration data."""

import re

from config_store import migrate_config
from parent_auth import is_supported_pin_hash


MAX_TILES = 200


def _bounded_string(value, field, maximum, allow_empty=True):
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    if not allow_empty and not value:
        raise ValueError(f"{field} must not be empty")
    if len(value) > maximum:
        raise ValueError(f"{field} is too long")
    return value


def validate_config(data, existing_pin_hash="", allow_pin_hash=False):
    """Validate untrusted config data while preserving future-compatible keys."""
    result, _ = migrate_config(data)
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
        validated_tiles.append({
            **tile,
            "id": tile_id,
            "label": label,
            "emoji": emoji,
            "cmd": clean_command,
            "visible": visible,
        })
    result["tiles"] = validated_tiles

    for field, maximum in (
        ("title", 200),
        ("theme", 64),
        ("parentLabel", 100),
        ("exitLabel", 100),
        ("shutdownLabel", 100),
        ("customBackground", 2048),
        ("browser", 128),
    ):
        if field in result:
            result[field] = _bounded_string(result[field], field, maximum)

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

    if "autoScanDone" in result and not isinstance(result["autoScanDone"], bool):
        raise ValueError("autoScanDone must be a boolean")

    if "customColors" in result:
        colors = result["customColors"]
        if not isinstance(colors, dict):
            raise ValueError("customColors must be an object")
        result["customColors"] = {
            _bounded_string(key, "customColors key", 40, False):
            _bounded_string(value, f"customColors.{key}", 128)
            for key, value in colors.items()
        }

    if allow_pin_hash:
        pin_hash = result.get("pinHash", "")
        if pin_hash and not is_supported_pin_hash(pin_hash):
            raise ValueError("pinHash has an unsupported format")
        result["pinHash"] = pin_hash
    else:
        result["pinHash"] = existing_pin_hash
    return result


def public_config(data):
    """Return configuration data without exposing the stored PIN hash."""
    result = dict(data)
    result["pinConfigured"] = bool(result.pop("pinHash", ""))
    return result
