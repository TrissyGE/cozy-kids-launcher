"""Bounded, private, local activity records for the Parent dashboard."""

import contextlib
import json
import os
import re
import secrets
import tempfile
import threading
import time

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows uses the in-process lock.
    fcntl = None


ACTIVITY_VERSION = 1
MAX_ACTIVITY_RECORDS = 1000
MAX_ACTIVITY_AGE_SECONDS = 90 * 24 * 60 * 60
MAX_ACTIVITY_DURATION_SECONDS = 24 * 60 * 60
ACTIVITY_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")
_local_lock = threading.Lock()


def _integer(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _activity_id(value, field):
    if not isinstance(value, str) or not ACTIVITY_ID_PATTERN.fullmatch(value):
        raise ValueError(f"{field} contains invalid characters")
    return value


def _prepare_directory(path):
    directory = os.path.dirname(os.fspath(path)) or "."
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    return directory


@contextlib.contextmanager
def _activity_lock(path):
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


def _empty_document(discard_before=0):
    return {
        "activityVersion": ACTIVITY_VERSION,
        "discardBefore": discard_before,
        "records": [],
    }


def _validated_record(record, now):
    if not isinstance(record, dict):
        return None
    try:
        profile_id = _activity_id(record.get("profileId"), "profileId")
        tile_id = _activity_id(record.get("tileId"), "tileId")
    except ValueError:
        return None
    started_at = record.get("startedAt")
    duration = record.get("durationSeconds")
    if (
        not _integer(started_at)
        or not 0 <= started_at <= now + 300
        or not _integer(duration)
        or not 0 <= duration <= MAX_ACTIVITY_DURATION_SECONDS
        or started_at < now - MAX_ACTIVITY_AGE_SECONDS
    ):
        return None
    return {
        "profileId": profile_id,
        "tileId": tile_id,
        "startedAt": started_at,
        "durationSeconds": duration,
    }


def _read_unlocked(path, now):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            document = json.load(handle)
    except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
        return _empty_document()
    if not isinstance(document, dict) or document.get("activityVersion") != ACTIVITY_VERSION:
        return _empty_document()
    discard_before = document.get("discardBefore", 0)
    if not _integer(discard_before) or not 0 <= discard_before <= now + 300:
        discard_before = 0
    records = document.get("records", [])
    if not isinstance(records, list):
        records = []
    validated = []
    for candidate in records[-MAX_ACTIVITY_RECORDS:]:
        record = _validated_record(candidate, now)
        if record and record["startedAt"] > discard_before:
            validated.append(record)
    validated.sort(key=lambda item: item["startedAt"])
    return {
        "activityVersion": ACTIVITY_VERSION,
        "discardBefore": discard_before,
        "records": validated[-MAX_ACTIVITY_RECORDS:],
    }


def _write_unlocked(path, document):
    directory = _prepare_directory(path)
    descriptor, temporary = tempfile.mkstemp(
        prefix="activity-",
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


def read_activity(path, now=None):
    """Return validated retained records in chronological order."""
    if not os.path.exists(path):
        return []
    now = int(time.time() if now is None else now)
    with _activity_lock(path):
        return _read_unlocked(path, now)["records"]


def record_activity(path, profile_id, tile_id, started_at, ended_at=None):
    """Append one completed usage interval without exposing labels or commands."""
    profile_id = _activity_id(profile_id, "profileId")
    tile_id = _activity_id(tile_id, "tileId")
    ended_at = int(time.time() if ended_at is None else ended_at)
    if not _integer(started_at) or started_at < 0 or ended_at < 0:
        raise ValueError("Activity timestamps must be non-negative integers")
    started_at = min(started_at, ended_at)
    duration = min(MAX_ACTIVITY_DURATION_SECONDS, ended_at - started_at)
    with _activity_lock(path):
        document = _read_unlocked(path, ended_at)
        if started_at <= document["discardBefore"]:
            return False
        document["records"].append({
            "profileId": profile_id,
            "tileId": tile_id,
            "startedAt": started_at,
            "durationSeconds": duration,
        })
        document["records"] = document["records"][-MAX_ACTIVITY_RECORDS:]
        _write_unlocked(path, document)
    return True


def activity_payload(path, now=None):
    """Return the bounded Parent API shape with newest activity first."""
    records = read_activity(path, now=now)
    return {
        "recordCount": len(records),
        "totalDurationSeconds": sum(item["durationSeconds"] for item in records),
        "records": list(reversed(records)),
    }


def clear_activity(path, now=None):
    """Remove records and suppress sessions that began before this clear."""
    now = int(time.time() if now is None else now)
    with _activity_lock(path):
        _write_unlocked(path, _empty_document(discard_before=now))


def remove_profile_activity(path, profile_id, now=None):
    """Remove retained activity when its child profile is deleted."""
    profile_id = _activity_id(profile_id, "profileId")
    if not os.path.exists(path):
        return
    now = int(time.time() if now is None else now)
    with _activity_lock(path):
        document = _read_unlocked(path, now)
        document["records"] = [
            record for record in document["records"]
            if record["profileId"] != profile_id
        ]
        _write_unlocked(path, document)


class EmbeddedActivitySessions:
    """Track only opaque, short-lived sessions for embedded browser tiles."""

    def __init__(self, path, clock=time.time, token_factory=None):
        self.path = os.fspath(path)
        self.clock = clock
        self.token_factory = token_factory or (lambda: secrets.token_urlsafe(24))
        self.lock = threading.Lock()
        self.active = {}

    def start(self, profile_id, tile_id):
        profile_id = _activity_id(profile_id, "profileId")
        tile_id = _activity_id(tile_id, "tileId")
        started_at = int(self.clock())
        token = self.token_factory()
        if not isinstance(token, str) or not 16 <= len(token) <= 128:
            raise ValueError("Activity token is invalid")
        with self.lock:
            previous = list(self.active.values())
            self.active.clear()
            self.active[token] = (profile_id, tile_id, started_at)
        self._finish_records(previous)
        return token

    def finish(self, token):
        if not isinstance(token, str) or len(token) > 128:
            return False
        with self.lock:
            record = self.active.pop(token, None)
        if not record:
            return False
        self._finish_records([record])
        return True

    def finish_all(self):
        with self.lock:
            records = list(self.active.values())
            self.active.clear()
        self._finish_records(records)

    def discard_all(self, now=None):
        with self.lock:
            self.active.clear()
        clear_activity(self.path, now=now)

    def _finish_records(self, records):
        if not records:
            return
        ended_at = int(self.clock())
        for profile_id, tile_id, started_at in records:
            try:
                record_activity(
                    self.path,
                    profile_id,
                    tile_id,
                    started_at,
                    ended_at=ended_at,
                )
            except (OSError, ValueError):
                pass
