"""Private, bounded per-profile storage for media-player resume data."""

import contextlib
import json
import os
import re
import shutil
import stat
import tempfile
import threading

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses the in-process lock.
    fcntl = None


PROFILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")
MEDIA_ID_PATTERN = re.compile(r"[a-f0-9]{24}")
RESUME_STATE_VERSION = 1
MAX_RESUME_ITEMS = 200
MAX_RESUME_STATE_BYTES = 64 * 1024
MAX_RESUME_SECONDS = 366 * 24 * 60 * 60
MIN_RESUME_SECONDS = 5
END_RESUME_MARGIN_SECONDS = 10
_local_lock = threading.Lock()


def _profile_id(value):
    if not isinstance(value, str) or not PROFILE_ID_PATTERN.fullmatch(value):
        raise ValueError("profileId contains invalid characters")
    return value


def _media_id(value):
    if not isinstance(value, str) or not MEDIA_ID_PATTERN.fullmatch(value):
        raise ValueError("mediaId is invalid")
    return value


def _profile_path(root, profile_id):
    root = os.path.abspath(os.fspath(root))
    profile = os.path.abspath(os.path.join(root, _profile_id(profile_id)))
    if os.path.commonpath((root, profile)) != root:
        raise ValueError("profileId escapes the resume root")
    return root, profile


def _secure_directory(path):
    if os.name != "posix":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
        return
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        os.fchmod(descriptor, 0o700)
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISDIR(mode) or stat.S_IMODE(mode) != 0o700:
            raise OSError("media resume path is not a private directory")
    finally:
        os.close(descriptor)


def prepare_profile_resume_directory(root, profile_id):
    """Create and return one private directory for a player's native state."""
    root, profile = _profile_path(root, profile_id)
    if os.path.islink(root):
        raise OSError("media resume root must not be a symbolic link")
    if os.path.islink(profile):
        raise OSError("media resume directory must not be a symbolic link")
    os.makedirs(root, mode=0o700, exist_ok=True)
    if os.path.islink(root):
        raise OSError("media resume root must not be a symbolic link")
    _secure_directory(root)
    os.makedirs(profile, mode=0o700, exist_ok=True)
    if os.path.islink(profile) or not os.path.isdir(profile):
        raise OSError("media resume directory is not a private directory")
    _secure_directory(profile)
    return profile


def _state_path(root, profile_id):
    profile = prepare_profile_resume_directory(root, profile_id)
    return os.path.join(profile, "vlc-positions.json")


@contextlib.contextmanager
def _state_lock(path):
    lock_path = f"{path}.lock"
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


def _empty_state():
    return {"resumeStateVersion": RESUME_STATE_VERSION, "items": []}


def _clean_item(candidate):
    if not isinstance(candidate, dict):
        return None
    try:
        media_id = _media_id(candidate.get("id"))
    except ValueError:
        return None
    position = candidate.get("positionSeconds")
    modified = candidate.get("mtimeNs")
    size = candidate.get("size")
    if any(isinstance(value, bool) or not isinstance(value, int) for value in (
        position,
        modified,
        size,
    )):
        return None
    if not MIN_RESUME_SECONDS <= position <= MAX_RESUME_SECONDS:
        return None
    if modified < 0 or size < 0:
        return None
    return {
        "id": media_id,
        "positionSeconds": position,
        "mtimeNs": modified,
        "size": size,
    }


def _read_unlocked(path):
    try:
        with open(path, "rb") as handle:
            payload = handle.read(MAX_RESUME_STATE_BYTES + 1)
        if len(payload) > MAX_RESUME_STATE_BYTES:
            return _empty_state()
        document = json.loads(payload.decode("utf-8"))
    except (FileNotFoundError, OSError, UnicodeError, ValueError, json.JSONDecodeError):
        return _empty_state()
    if (
        not isinstance(document, dict)
        or document.get("resumeStateVersion") != RESUME_STATE_VERSION
        or not isinstance(document.get("items"), list)
    ):
        return _empty_state()
    items = []
    seen = set()
    for candidate in document["items"]:
        item = _clean_item(candidate)
        if not item or item["id"] in seen:
            continue
        items.append(item)
        seen.add(item["id"])
        if len(items) >= MAX_RESUME_ITEMS:
            break
    return {"resumeStateVersion": RESUME_STATE_VERSION, "items": items}


def _write_unlocked(path, document):
    directory = os.path.dirname(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix="vlc-resume-",
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


def _fingerprint(media_path):
    status = os.stat(media_path)
    if not stat.S_ISREG(status.st_mode):
        raise OSError("media resume source is not a regular file")
    return status.st_mtime_ns, status.st_size


def load_resume_position(root, profile_id, media_id, media_path):
    """Return a VLC start time only when the exact local file still matches."""
    media_id = _media_id(media_id)
    path = _state_path(root, profile_id)
    modified, size = _fingerprint(media_path)
    with _state_lock(path):
        for item in _read_unlocked(path)["items"]:
            if item["id"] == media_id:
                if item["mtimeNs"] == modified and item["size"] == size:
                    return item["positionSeconds"]
                break
    return 0


def save_resume_position(
    root,
    profile_id,
    media_id,
    media_path,
    position_seconds,
    duration_seconds=0,
):
    """Store or clear one recent VLC position without retaining its path."""
    media_id = _media_id(media_id)
    for name, value in (
        ("position", position_seconds),
        ("duration", duration_seconds),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    modified, size = _fingerprint(media_path)
    path = _state_path(root, profile_id)
    with _state_lock(path):
        document = _read_unlocked(path)
        existing = [item for item in document["items"] if item["id"] != media_id]
        near_end = duration_seconds > 0 and (
            duration_seconds - position_seconds <= END_RESUME_MARGIN_SECONDS
        )
        if MIN_RESUME_SECONDS <= position_seconds <= MAX_RESUME_SECONDS and not near_end:
            existing.insert(0, {
                "id": media_id,
                "positionSeconds": position_seconds,
                "mtimeNs": modified,
                "size": size,
            })
        document["items"] = existing[:MAX_RESUME_ITEMS]
        if document["items"] or os.path.exists(path):
            _write_unlocked(path, document)


def remove_profile_resume_directory(root, profile_id):
    """Remove only the native resume data belonging to one deleted profile."""
    root, profile = _profile_path(root, profile_id)
    if os.path.islink(root):
        raise OSError("media resume root must not be a symbolic link")
    if os.path.islink(profile):
        os.unlink(profile)
    elif os.path.isdir(profile):
        shutil.rmtree(profile)
    elif os.path.exists(profile):
        os.unlink(profile)
