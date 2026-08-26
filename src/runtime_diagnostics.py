"""Privacy-safe runtime events and diagnostics for Cozy Kids Launcher."""

import json
import logging
import logging.handlers
import os
import platform
import re
import threading
from datetime import datetime, timezone


DEFAULT_MAX_BYTES = 512 * 1024
DEFAULT_BACKUP_COUNT = 3
DEFAULT_EVENT_LIMIT = 200
DIAGNOSTICS_VERSION = 1

_SAFE_EVENT_FIELDS = {
    "auth.failed": set(),
    "auth.succeeded": set(),
    "auth.throttled": set(),
    "config.imported": {"configVersion"},
    "config.migrated": {"configVersion"},
    "config.saved": {"configVersion"},
    "diagnostics.exported": set(),
    "launch.failed": {"actionType", "result"},
    "launch.started": {"actionType"},
    "pin.changed": set(),
    "pin.removed": set(),
    "request.rejected": {"statusCode"},
    "server.crashed": {"exceptionType"},
    "server.duplicate": set(),
    "server.started": {"version"},
    "server.stopped": set(),
    "timer.extended": set(),
    "timer.started": set(),
    "timer.stopped": set(),
    "update.checked": {"source", "updateAvailable", "version"},
    "update.failed": {"exceptionType"},
    "update.triggered": set(),
}
_SAFE_LEVELS = {"debug", "info", "warning", "error", "critical"}
_SAFE_ACTION_TYPES = {"app", "media", "none", "web"}
_SAFE_EXCEPTION_TYPES = {
    "AttributeError",
    "ConnectionError",
    "FileNotFoundError",
    "HTTPError",
    "JSONDecodeError",
    "OSError",
    "PermissionError",
    "RuntimeError",
    "TimeoutError",
    "TypeError",
    "URLError",
    "ValueError",
}
_SAFE_RESULTS = {"blocked", "failure", "missing", "redirect", "success"}
_SAFE_SOURCES = {"legacy-main", "release"}
_TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_.+-]{1,80}$")
_VERSION_PATTERN = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")

_active_logger = None
_active_logger_lock = threading.Lock()


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _safe_token(value, fallback="unknown"):
    if isinstance(value, str) and _TOKEN_PATTERN.fullmatch(value):
        return value
    return fallback


def _safe_timestamp(value):
    if not isinstance(value, str):
        return utc_timestamp()
    try:
        candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
        parsed = datetime.fromisoformat(candidate)
        if parsed.tzinfo is None:
            raise ValueError("Runtime timestamp must include a timezone")
    except (TypeError, ValueError):
        return utc_timestamp()
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _safe_detail(name, value):
    if name == "actionType" and value in _SAFE_ACTION_TYPES:
        return value
    if name == "configVersion" and not isinstance(value, bool):
        if isinstance(value, int) and 0 <= value <= 10_000:
            return value
    if name == "exceptionType":
        return value if value in _SAFE_EXCEPTION_TYPES else "OtherError"
    if name == "result" and value in _SAFE_RESULTS:
        return value
    if name == "source" and value in _SAFE_SOURCES:
        return value
    if name == "statusCode" and not isinstance(value, bool):
        if isinstance(value, int) and 100 <= value <= 599:
            return value
    if name == "updateAvailable" and isinstance(value, bool):
        return value
    if name == "version" and isinstance(value, str):
        if _VERSION_PATTERN.fullmatch(value):
            return value
    raise ValueError(f"Unsafe runtime event detail: {name}")


def sanitize_event(event, level="info", details=None, timestamp=None):
    """Return an allowlisted event or reject data that could reveal family values."""
    if event not in _SAFE_EVENT_FIELDS:
        raise ValueError(f"Unknown runtime event: {event}")
    normalized_level = str(level).lower()
    if normalized_level not in _SAFE_LEVELS:
        raise ValueError(f"Unsupported runtime event level: {level}")
    details = details or {}
    if not isinstance(details, dict):
        raise ValueError("Runtime event details must be an object")
    allowed_fields = _SAFE_EVENT_FIELDS[event]
    if not set(details).issubset(allowed_fields):
        raise ValueError(f"Runtime event contains fields outside its privacy contract: {event}")
    safe_details = {
        name: _safe_detail(name, value)
        for name, value in details.items()
    }
    result = {
        "timestamp": _safe_timestamp(timestamp),
        "level": normalized_level,
        "event": event,
    }
    if safe_details:
        result["details"] = safe_details
    return result


class _JsonLineFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps(record.runtime_event, ensure_ascii=False, separators=(",", ":"))


class _PrivateRotatingFileHandler(logging.handlers.RotatingFileHandler):
    def _open(self):
        stream = super()._open()
        try:
            os.chmod(self.baseFilename, 0o600)
        except OSError:
            pass
        return stream


class RuntimeEventLogger:
    def __init__(
        self,
        path,
        max_bytes=DEFAULT_MAX_BYTES,
        backup_count=DEFAULT_BACKUP_COUNT,
    ):
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, mode=0o700, exist_ok=True)
        try:
            os.chmod(directory, 0o700)
        except OSError:
            pass
        self.path = os.path.abspath(path)
        self.backup_count = backup_count
        self._logger = logging.Logger(
            f"cozy-kids-runtime-{id(self)}",
            level=logging.DEBUG,
        )
        self._logger.propagate = False
        self._handler = _PrivateRotatingFileHandler(
            self.path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
        self._handler.setFormatter(_JsonLineFormatter())
        self._logger.addHandler(self._handler)

    def event(self, event, level="info", **details):
        payload = sanitize_event(event, level=level, details=details)
        self._logger.log(
            getattr(logging, payload["level"].upper()),
            event,
            extra={"runtime_event": payload},
        )

    def close(self):
        self._logger.removeHandler(self._handler)
        self._handler.close()


def configure_runtime_logging(
    path,
    max_bytes=DEFAULT_MAX_BYTES,
    backup_count=DEFAULT_BACKUP_COUNT,
):
    global _active_logger
    logger = RuntimeEventLogger(path, max_bytes=max_bytes, backup_count=backup_count)
    with _active_logger_lock:
        previous = _active_logger
        _active_logger = logger
    if previous:
        previous.close()
    return logger


def close_runtime_logging():
    global _active_logger
    with _active_logger_lock:
        previous = _active_logger
        _active_logger = None
    if previous:
        previous.close()


def log_runtime_event(event, level="info", **details):
    with _active_logger_lock:
        logger = _active_logger
        if not logger:
            return False
        try:
            logger.event(event, level=level, **details)
        except Exception:
            return False
        return True


def _read_safe_events(log_path, backup_count, limit):
    paths = [f"{log_path}.{index}" for index in range(backup_count, 0, -1)]
    paths.append(log_path)
    events = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        for line in lines:
            try:
                raw = json.loads(line)
                safe = sanitize_event(
                    raw.get("event"),
                    level=raw.get("level", "info"),
                    details=raw.get("details", {}),
                    timestamp=raw.get("timestamp"),
                )
            except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                continue
            events.append(safe)
    return events[-limit:]


def build_diagnostics(
    log_path,
    app_version,
    config_readable,
    config_version=None,
    backup_count=DEFAULT_BACKUP_COUNT,
    event_limit=DEFAULT_EVENT_LIMIT,
):
    """Build diagnostics without accepting or exposing configuration values."""
    safe_config_version = None
    if not isinstance(config_version, bool) and isinstance(config_version, int):
        if 0 <= config_version <= 10_000:
            safe_config_version = config_version
    return {
        "diagnosticsVersion": DIAGNOSTICS_VERSION,
        "generatedAt": utc_timestamp(),
        "application": {
            "version": app_version
            if isinstance(app_version, str) and _VERSION_PATTERN.fullmatch(app_version)
            else "unknown"
        },
        "runtime": {
            "pythonVersion": _safe_token(platform.python_version()),
            "system": _safe_token(platform.system()),
            "release": _safe_token(platform.release()),
            "machine": _safe_token(platform.machine()),
        },
        "configuration": {
            "readable": bool(config_readable),
            "schemaVersion": safe_config_version,
        },
        "privacy": {
            "includesConfigurationValues": False,
            "includesCredentials": False,
            "includesPersonalPaths": False,
        },
        "events": _read_safe_events(log_path, backup_count, event_limit),
    }
