"""Bounded, private, per-profile state for the local media library."""

import contextlib
import json
import os
import re
import tempfile
import threading

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses the in-process lock.
    fcntl = None


MEDIA_STATE_VERSION = 1
MAX_MEDIA_STATE_PROFILES = 20
MAX_MEDIA_FAVORITES = 200
MAX_MEDIA_RECENTS = 50
MAX_MEDIA_STATE_BYTES = 256 * 1024
MEDIA_ID_PATTERN = re.compile(r"[a-f0-9]{24}")
PROFILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")
_local_lock = threading.Lock()


def _profile_id(value):
    if not isinstance(value, str) or not PROFILE_ID_PATTERN.fullmatch(value):
        raise ValueError("profileId contains invalid characters")
    return value


def _media_id(value):
    if not isinstance(value, str) or not MEDIA_ID_PATTERN.fullmatch(value):
        raise ValueError("mediaId is invalid")
    return value


def _clean_ids(values, maximum):
    if not isinstance(values, list):
        return []
    result = []
    seen = set()
    for value in values[:maximum]:
        try:
            value = _media_id(value)
        except ValueError:
            continue
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _empty_document():
    return {"mediaStateVersion": MEDIA_STATE_VERSION, "profiles": {}}


def _prepare_directory(path):
    directory = os.path.dirname(os.fspath(path)) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


@contextlib.contextmanager
def _media_state_lock(path):
    directory = _prepare_directory(path)
    lock_path = os.path.join(directory, os.path.basename(os.fspath(path)) + ".lock")
    with _local_lock:
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
        with os.fdopen(descriptor, "a+b") as handle:
            try:
                os.chmod(lock_path, 0o600)
            except OSError:
                pass
            if fcntl is not None:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_unlocked(path):
    try:
        with open(path, "rb") as handle:
            payload = handle.read(MAX_MEDIA_STATE_BYTES + 1)
        if len(payload) > MAX_MEDIA_STATE_BYTES:
            return _empty_document()
        document = json.loads(payload.decode("utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return _empty_document()
    if (
        not isinstance(document, dict)
        or document.get("mediaStateVersion") != MEDIA_STATE_VERSION
        or not isinstance(document.get("profiles"), dict)
    ):
        return _empty_document()

    profiles = {}
    for profile_id in document["profiles"]:
        if len(profiles) >= MAX_MEDIA_STATE_PROFILES:
            break
        candidate = document["profiles"][profile_id]
        try:
            clean_profile_id = _profile_id(profile_id)
        except ValueError:
            continue
        if not isinstance(candidate, dict):
            continue
        profiles[clean_profile_id] = {
            "favorites": _clean_ids(candidate.get("favorites"), MAX_MEDIA_FAVORITES),
            "recents": _clean_ids(candidate.get("recents"), MAX_MEDIA_RECENTS),
        }
    return {"mediaStateVersion": MEDIA_STATE_VERSION, "profiles": profiles}


def _write_unlocked(path, document):
    directory = _prepare_directory(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix="media-state-",
        suffix=".json",
        dir=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _profile_state(document, profile_id):
    profiles = document["profiles"]
    if profile_id not in profiles and len(profiles) >= MAX_MEDIA_STATE_PROFILES:
        profiles.pop(next(iter(profiles)))
    return profiles.setdefault(profile_id, {"favorites": [], "recents": []})


def media_state_payload(path, profile_id, available_ids=None):
    """Return path-free favorites and recents for one child profile."""
    profile_id = _profile_id(profile_id)
    if not os.path.exists(path):
        state = {"favorites": [], "recents": []}
    else:
        with _media_state_lock(path):
            state = _read_unlocked(path)["profiles"].get(
                profile_id,
                {"favorites": [], "recents": []},
            )
    if available_ids is None:
        allowed = None
    else:
        allowed = {_media_id(media_id) for media_id in available_ids}
    return {
        "favoriteIds": [
            media_id for media_id in state["favorites"]
            if allowed is None or media_id in allowed
        ],
        "recentIds": [
            media_id for media_id in state["recents"]
            if allowed is None or media_id in allowed
        ],
    }


def set_media_favorite(path, profile_id, media_id, favorite):
    """Add or remove one opaque media ID from one profile's favorites."""
    profile_id = _profile_id(profile_id)
    media_id = _media_id(media_id)
    if not isinstance(favorite, bool):
        raise ValueError("favorite must be a boolean")
    with _media_state_lock(path):
        document = _read_unlocked(path)
        state = _profile_state(document, profile_id)
        state["favorites"] = [
            candidate for candidate in state["favorites"] if candidate != media_id
        ]
        if favorite:
            state["favorites"].insert(0, media_id)
            state["favorites"] = state["favorites"][:MAX_MEDIA_FAVORITES]
        _write_unlocked(path, document)
    return favorite


def record_media_play(path, profile_id, media_id):
    """Move one successfully launched item to the front of recent media."""
    profile_id = _profile_id(profile_id)
    media_id = _media_id(media_id)
    with _media_state_lock(path):
        document = _read_unlocked(path)
        state = _profile_state(document, profile_id)
        state["recents"] = [
            candidate for candidate in state["recents"] if candidate != media_id
        ]
        state["recents"].insert(0, media_id)
        state["recents"] = state["recents"][:MAX_MEDIA_RECENTS]
        _write_unlocked(path, document)


def remove_profile_media_state(path, profile_id):
    """Remove retained media preferences when a child profile is deleted."""
    profile_id = _profile_id(profile_id)
    if not os.path.exists(path):
        return
    with _media_state_lock(path):
        document = _read_unlocked(path)
        document["profiles"].pop(profile_id, None)
        _write_unlocked(path, document)
