"""Linux process identity records that are safe against stale PID reuse."""

import argparse
import json
import os
import re
import signal
import tempfile
import time


PROCESS_RECORD_VERSION = 1
_ROLE_PATTERN = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def _process_stat(pid):
    try:
        with open(f"/proc/{int(pid)}/stat", "r", encoding="utf-8") as handle:
            stat_line = handle.read()
        closing_parenthesis = stat_line.rfind(")")
        if closing_parenthesis < 0:
            return None
        fields_after_command = stat_line[closing_parenthesis + 2:].split()
        return fields_after_command[0], int(fields_after_command[19])
    except (IndexError, OSError, TypeError, ValueError):
        return None


def process_start_time(pid):
    """Return Linux kernel start ticks for a process, or None when it is gone."""
    status = _process_stat(pid)
    return status[1] if status else None


def process_command(pid):
    try:
        with open(f"/proc/{int(pid)}/cmdline", "rb") as handle:
            return [
                part.decode("utf-8", errors="replace")
                for part in handle.read().split(b"\0")
                if part
            ]
    except (OSError, TypeError, ValueError):
        return []


def _validate_role(role):
    if not isinstance(role, str) or not _ROLE_PATTERN.fullmatch(role):
        raise ValueError("Process role must use lowercase letters, digits, and hyphens")
    return role


def _atomic_write(path, data):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, mode=0o700, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(
        prefix="process-",
        suffix=".json",
        dir=directory,
    )
    try:
        os.chmod(temp_path, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def write_process_record(path, pid, role, marker=""):
    """Record a live process together with its non-reusable kernel identity."""
    role = _validate_role(role)
    if isinstance(pid, bool):
        raise ValueError("PID must be a positive integer")
    pid = int(pid)
    if pid <= 0:
        raise ValueError("PID must be a positive integer")
    status = _process_stat(pid)
    if status is None or status[0] == "Z":
        raise ProcessLookupError(f"Process {pid} is not running")
    start_time = status[1]
    if marker:
        if not isinstance(marker, str) or marker not in process_command(pid):
            raise ProcessLookupError(f"Process {pid} does not match its owner marker")
    record = {
        "recordVersion": PROCESS_RECORD_VERSION,
        "pid": pid,
        "startTime": start_time,
        "role": role,
    }
    if marker:
        record["marker"] = marker
    _atomic_write(path, record)
    return record


def read_process_record(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            record = json.load(handle)
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(record, dict):
        return None
    if record.get("recordVersion") != PROCESS_RECORD_VERSION:
        return None
    pid = record.get("pid")
    start_time = record.get("startTime")
    role = record.get("role")
    marker = record.get("marker", "")
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    if isinstance(start_time, bool) or not isinstance(start_time, int):
        return None
    try:
        _validate_role(role)
    except ValueError:
        return None
    if not isinstance(marker, str):
        return None
    return record


def owned_process(path, expected_role=None, expected_marker=None):
    """Return a record only while PID, start time, role, and marker still match."""
    record = read_process_record(path)
    if not record:
        return None
    if expected_role is not None and record["role"] != expected_role:
        return None
    if expected_marker is not None and record.get("marker", "") != expected_marker:
        return None
    status = _process_stat(record["pid"])
    if not status or status[0] == "Z" or status[1] != record["startTime"]:
        return None
    marker = record.get("marker", "")
    if marker and marker not in process_command(record["pid"]):
        return None
    return record


def owned_process_alive(path, expected_role=None, expected_marker=None):
    return owned_process(path, expected_role, expected_marker) is not None


def remove_process_record(path, expected_pid=None):
    if expected_pid is not None:
        record = read_process_record(path)
        if not record or record["pid"] != expected_pid:
            return False
    try:
        os.unlink(path)
        return True
    except FileNotFoundError:
        return False


def terminate_owned_process(
    path,
    expected_role=None,
    expected_marker=None,
    timeout=2.0,
):
    """Terminate only the exact recorded process, never a reused numeric PID."""
    record = owned_process(path, expected_role, expected_marker)
    if not record:
        remove_process_record(path)
        return False
    pid = record["pid"]
    try:
        os.kill(pid, signal.SIGTERM)
    except ProcessLookupError:
        remove_process_record(path, expected_pid=pid)
        return True
    deadline = time.monotonic() + max(0.0, timeout)
    while time.monotonic() < deadline:
        if not owned_process(path, expected_role, expected_marker):
            remove_process_record(path, expected_pid=pid)
            return True
        time.sleep(0.05)
    if owned_process(path, expected_role, expected_marker):
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    remove_process_record(path, expected_pid=pid)
    return True


def _cli_parser():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    alive = subparsers.add_parser("alive")
    alive.add_argument("path")
    alive.add_argument("role")
    alive.add_argument("--marker")
    record = subparsers.add_parser("record")
    record.add_argument("path")
    record.add_argument("pid", type=int)
    record.add_argument("role")
    record.add_argument("--marker", default="")
    terminate = subparsers.add_parser("terminate")
    terminate.add_argument("path")
    terminate.add_argument("role")
    terminate.add_argument("--marker")
    remove = subparsers.add_parser("remove")
    remove.add_argument("path")
    remove.add_argument("--pid", type=int)
    return parser


def main(argv=None):
    args = _cli_parser().parse_args(argv)
    try:
        if args.command == "alive":
            return 0 if owned_process_alive(args.path, args.role, args.marker) else 1
        if args.command == "record":
            write_process_record(args.path, args.pid, args.role, marker=args.marker)
            return 0
        if args.command == "terminate":
            return 0 if terminate_owned_process(
                args.path,
                args.role,
                args.marker,
            ) else 1
        if args.command == "remove":
            remove_process_record(args.path, expected_pid=args.pid)
            return 0
    except (OSError, ValueError):
        return 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
