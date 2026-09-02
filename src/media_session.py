#!/usr/bin/env python3
"""Supervise one VLC item and persist a bounded, path-free resume position."""

import argparse
import os
import re
import signal
import subprocess
import time

from media_resume import load_resume_position, save_resume_position


RC_INTEGER_PATTERN = re.compile(rb"^(?:>\s*)?([0-9]+)\s*$")
POLL_SECONDS = 1.0
QUERY_TIMEOUT_SECONDS = 0.4
_termination_signal = None


def _handle_termination(signum, _frame):
    global _termination_signal
    _termination_signal = signum


def parse_rc_integer(payload):
    """Return the last standalone non-negative integer in VLC RC output."""
    result = None
    for line in payload.splitlines():
        match = RC_INTEGER_PATTERN.fullmatch(line.strip())
        if match:
            result = int(match.group(1))
    return result


def controlled_vlc_command(command, start_seconds=0):
    """Add a private stdin RC channel and disable VLC's global history."""
    if not command or os.path.basename(command[0]) != "vlc":
        raise ValueError("VLC command is required")
    control = [
        "--extraintf=oldrc",
        "--rc-fake-tty",
        "--no-one-instance",
        "--no-media-library",
        "--no-qt-recentplay",
        "--qt-continue=0",
    ]
    if start_seconds:
        control.append(f"--start-time={int(start_seconds)}")
    return [command[0], *control, *command[1:]]


class VlcRemote:
    def __init__(self, process):
        self.process = process
        os.set_blocking(process.stdout.fileno(), False)

    def drain(self):
        chunks = []
        while True:
            try:
                chunk = os.read(self.process.stdout.fileno(), 8192)
            except OSError:
                break
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def query(self, command, timeout=QUERY_TIMEOUT_SECONDS):
        self.drain()
        try:
            self.process.stdin.write(os.fsencode(command) + b"\n")
            self.process.stdin.flush()
        except (BrokenPipeError, OSError):
            return None
        deadline = time.monotonic() + timeout
        response = bytearray()
        while time.monotonic() < deadline:
            response.extend(self.drain())
            value = parse_rc_integer(response)
            if value is not None:
                return value
            if self.process.poll() is not None:
                break
            time.sleep(0.02)
        response.extend(self.drain())
        return parse_rc_integer(response)


def monitor_vlc(command, resume_root, profile_id, media_id, media_path):
    """Run VLC, sample its local RC channel, and save only on process exit."""
    global _termination_signal
    _termination_signal = None
    try:
        start_seconds = load_resume_position(
            resume_root,
            profile_id,
            media_id,
            media_path,
        )
    except (OSError, ValueError):
        start_seconds = 0
    child = subprocess.Popen(
        controlled_vlc_command(command, start_seconds),
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=0,
        env=dict(os.environ),
    )
    position_seconds = start_seconds
    duration_seconds = 0
    try:
        remote = VlcRemote(child)
        next_poll = time.monotonic() + 0.5
        while child.poll() is None and _termination_signal is None:
            now = time.monotonic()
            if now >= next_poll:
                position = remote.query("get_time")
                if position is not None:
                    position_seconds = position
                if not duration_seconds:
                    duration = remote.query("get_length")
                    if duration is not None:
                        duration_seconds = duration
                next_poll = time.monotonic() + POLL_SECONDS
            time.sleep(0.05)
    finally:
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=1)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait()
        try:
            save_resume_position(
                resume_root,
                profile_id,
                media_id,
                media_path,
                position_seconds,
                duration_seconds,
            )
        except (OSError, ValueError):
            pass
        streams = (
            getattr(child, "stdin", None),
            getattr(child, "stdout", None),
        )
        for stream in streams:
            if stream is None:
                continue
            try:
                stream.close()
            except OSError:
                pass
    return 0 if _termination_signal is not None else (child.returncode or 0)


def _parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("--resume-root", required=True)
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--media-id", required=True)
    parser.add_argument("--media-path", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv=None):
    args = _parser().parse_args(argv)
    command = args.command
    if command and command[0] == "--":
        command = command[1:]
    if not command:
        return 2
    for signum in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, _handle_termination)
    try:
        return monitor_vlc(
            command,
            args.resume_root,
            args.profile_id,
            args.media_id,
            args.media_path,
        )
    except (OSError, ValueError):
        return 127


if __name__ == "__main__":
    raise SystemExit(main())
