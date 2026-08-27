"""Validated, privacy-safe launcher lifecycle state storage."""

import argparse
import json
import os
import tempfile
import time
from datetime import datetime, timezone


LIFECYCLE_SCHEMA_VERSION = 1
REQUEST_MAX_AGE_SECONDS = 60

STATE_REASONS = {
    "starting": {"initial-start", "recovery", "update-complete"},
    "running": {"ready", "recovered", "update-complete"},
    "recovering": {"server-failed", "startup-failed"},
    "updating": {"update-requested"},
    "stopping": {
        "browser-exited",
        "logout",
        "manual-stop",
        "parent-exit",
        "session-ended",
        "shutdown",
    },
    "stopped": {
        "browser-exited",
        "logout",
        "manual-stop",
        "parent-exit",
        "session-ended",
        "shutdown",
    },
    "failed": {
        "browser-start-failed",
        "recovery-exhausted",
        "startup-failed",
        "unexpected-exit",
        "update-failed",
    },
}

ALLOWED_TRANSITIONS = {
    "starting": {"running", "recovering", "stopping", "failed"},
    "running": {"recovering", "updating", "stopping", "failed"},
    "recovering": {"starting", "stopping", "failed"},
    "updating": {"starting", "stopping", "failed"},
    "stopping": {"stopped", "failed"},
    "stopped": {"starting"},
    "failed": {"starting"},
}

REQUEST_REASONS = {"parent-exit", "shutdown"}


def utc_timestamp(now=None):
    value = now or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def _atomic_private_json(path, data):
    path = os.path.abspath(path)
    directory = os.path.dirname(path)
    os.makedirs(directory, mode=0o700, exist_ok=True)
    try:
        os.chmod(directory, 0o700)
    except OSError:
        pass
    descriptor, temp_path = tempfile.mkstemp(
        prefix=f".{os.path.basename(path)}-",
        dir=directory,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def validate_lifecycle_state(data):
    if not isinstance(data, dict):
        raise ValueError("Lifecycle state must be an object")
    if data.get("schemaVersion") != LIFECYCLE_SCHEMA_VERSION:
        raise ValueError("Unsupported lifecycle state schema")
    state = data.get("state")
    reason = data.get("reason")
    if (
        not isinstance(state, str)
        or not isinstance(reason, str)
        or state not in STATE_REASONS
        or reason not in STATE_REASONS[state]
    ):
        raise ValueError("Invalid lifecycle state or reason")
    updated_at = data.get("updatedAt")
    if not isinstance(updated_at, str) or len(updated_at) > 40:
        raise ValueError("Invalid lifecycle timestamp")
    attempt = data.get("attempt")
    if attempt is not None:
        if isinstance(attempt, bool) or not isinstance(attempt, int):
            raise ValueError("Invalid lifecycle recovery attempt")
        if not 1 <= attempt <= 10:
            raise ValueError("Invalid lifecycle recovery attempt")
        if state not in {"starting", "running", "recovering"}:
            raise ValueError("Recovery attempt is invalid for this lifecycle state")
    return {
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "state": state,
        "reason": reason,
        "updatedAt": updated_at,
        **({"attempt": attempt} if attempt is not None else {}),
    }


def read_lifecycle_state(path):
    with open(path, "r", encoding="utf-8") as handle:
        return validate_lifecycle_state(json.load(handle))


def begin_lifecycle(path, reason="initial-start", now=None):
    """Begin a new launcher run, replacing state left by an unclean exit."""
    data = validate_lifecycle_state({
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "state": "starting",
        "reason": reason,
        "updatedAt": utc_timestamp(now),
    })
    _atomic_private_json(path, data)
    return data


def transition_lifecycle(path, state, reason, attempt=None, now=None):
    current = read_lifecycle_state(path)
    if state not in ALLOWED_TRANSITIONS[current["state"]]:
        raise ValueError(
            f"Invalid lifecycle transition: {current['state']} -> {state}"
        )
    data = {
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "state": state,
        "reason": reason,
        "updatedAt": utc_timestamp(now),
    }
    if attempt is not None:
        data["attempt"] = attempt
    data = validate_lifecycle_state(data)
    _atomic_private_json(path, data)
    return data


def write_lifecycle_request(path, reason, now=None):
    if not isinstance(reason, str) or reason not in REQUEST_REASONS:
        raise ValueError("Invalid lifecycle request")
    created_at = int(time.time() if now is None else now)
    _atomic_private_json(path, {
        "schemaVersion": LIFECYCLE_SCHEMA_VERSION,
        "reason": reason,
        "createdAt": created_at,
    })


def clear_lifecycle_request(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def consume_lifecycle_request(
    path,
    now=None,
    max_age_seconds=REQUEST_MAX_AGE_SECONDS,
):
    current_time = int(time.time() if now is None else now)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        clear_lifecycle_request(path)
        return None
    clear_lifecycle_request(path)
    if not isinstance(data, dict):
        return None
    if data.get("schemaVersion") != LIFECYCLE_SCHEMA_VERSION:
        return None
    reason = data.get("reason")
    created_at = data.get("createdAt")
    if not isinstance(reason, str) or reason not in REQUEST_REASONS:
        return None
    if isinstance(created_at, bool) or not isinstance(created_at, int):
        return None
    age = current_time - created_at
    if age < 0 or age > max_age_seconds:
        return None
    return reason


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    begin_parser = subparsers.add_parser("begin")
    begin_parser.add_argument("path")
    begin_parser.add_argument("reason")

    transition_parser = subparsers.add_parser("transition")
    transition_parser.add_argument("path")
    transition_parser.add_argument("state")
    transition_parser.add_argument("reason")
    transition_parser.add_argument("--attempt", type=int)

    request_parser = subparsers.add_parser("request")
    request_parser.add_argument("path")
    request_parser.add_argument("reason")

    consume_parser = subparsers.add_parser("consume-request")
    consume_parser.add_argument("path")

    args = parser.parse_args()
    if args.command == "begin":
        begin_lifecycle(args.path, args.reason)
    elif args.command == "transition":
        transition_lifecycle(
            args.path,
            args.state,
            args.reason,
            attempt=args.attempt,
        )
    elif args.command == "request":
        write_lifecycle_request(args.path, args.reason)
    elif args.command == "consume-request":
        reason = consume_lifecycle_request(args.path)
        if reason:
            print(reason)


if __name__ == "__main__":
    main()
