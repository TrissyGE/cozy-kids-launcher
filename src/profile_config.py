"""Profile-aware configuration helpers for Cozy Kids Launcher."""

import copy
import re
import uuid


DEFAULT_PROFILE_ID = "default"
MAX_PROFILES = 20
PROFILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+")
PROFILE_FIELDS = (
    "name",
    "avatar",
    "title",
    "theme",
    "customColors",
    "customBackground",
    "layoutMode",
    "currentPage",
    "timerMinutes",
    "timerWarningMinutes",
    "tiles",
    "favorites",
    "appLimits",
)


def migrate_legacy_profile(data):
    """Move the former single-child settings into a default profile."""
    result = copy.deepcopy(data)
    profile = {
        "id": DEFAULT_PROFILE_ID,
        "name": "Kiddo",
        "avatar": "🌈",
        "favorites": [],
        "appLimits": {},
    }
    for field in PROFILE_FIELDS:
        if field in result:
            profile[field] = result.pop(field)
    profile.setdefault("tiles", [])
    result["activeProfileId"] = DEFAULT_PROFILE_ID
    result["profiles"] = [profile]
    return result


def profile_summaries(data):
    """Return the non-sensitive fields needed by a future profile picker."""
    return [
        {
            "id": profile["id"],
            "name": profile["name"],
            "avatar": profile.get("avatar", ""),
        }
        for profile in data.get("profiles", [])
    ]


def active_profile(data):
    profile_id = data.get("activeProfileId")
    for profile in data.get("profiles", []):
        if profile.get("id") == profile_id:
            return profile
    raise ValueError("activeProfileId does not reference an existing profile")


def active_config(data):
    """Project stored multi-profile data into the legacy-compatible runtime view."""
    result = copy.deepcopy(data)
    profile = copy.deepcopy(active_profile(result))
    result.pop("profiles", None)
    result.update({key: value for key, value in profile.items() if key != "id"})
    result["profiles"] = profile_summaries(data)
    return result


def merge_active_config(data, runtime_config):
    """Merge a validated flat runtime config into only the active profile."""
    result = copy.deepcopy(data)
    target = active_profile(result)
    for field in PROFILE_FIELDS:
        if field in runtime_config:
            target[field] = copy.deepcopy(runtime_config[field])

    ignored = {"profiles", "pinConfigured", *PROFILE_FIELDS}
    for key, value in runtime_config.items():
        if key not in ignored and key != "activeProfileId":
            result[key] = copy.deepcopy(value)
    return result


def add_profile(data, name, avatar="", profile_id=None):
    """Clone the active profile so a new child starts with usable settings."""
    result = copy.deepcopy(data)
    profiles = result.setdefault("profiles", [])
    if len(profiles) >= MAX_PROFILES:
        raise ValueError(f"A maximum of {MAX_PROFILES} profiles is supported")

    new_id = profile_id or f"child-{uuid.uuid4().hex[:12]}"
    if not isinstance(new_id, str) or not PROFILE_ID_PATTERN.fullmatch(new_id):
        raise ValueError("Profile id contains invalid characters")
    if any(profile.get("id") == new_id for profile in profiles):
        raise ValueError("Profile id already exists")

    profile = copy.deepcopy(active_profile(result))
    profile["id"] = new_id
    profile["name"] = name
    profile["avatar"] = avatar
    profile["title"] = name
    profile["currentPage"] = 0
    profile["favorites"] = []
    profile["appLimits"] = {}
    profiles.append(profile)
    return result, new_id


def select_profile(data, profile_id):
    result = copy.deepcopy(data)
    if not any(profile.get("id") == profile_id for profile in result.get("profiles", [])):
        raise ValueError("Unknown profile")
    result["activeProfileId"] = profile_id
    return result


def remove_profile(data, profile_id):
    result = copy.deepcopy(data)
    profiles = result.get("profiles", [])
    if profile_id == result.get("activeProfileId"):
        raise ValueError("The active profile cannot be deleted")
    if len(profiles) <= 1:
        raise ValueError("The last profile cannot be deleted")
    remaining = [profile for profile in profiles if profile.get("id") != profile_id]
    if len(remaining) == len(profiles):
        raise ValueError("Unknown profile")
    result["profiles"] = remaining
    return result
