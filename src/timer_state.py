"""Persistent screen-timer state and status calculation."""

import json
import os
import time


def load_timer(path):
    """Load timer JSON, returning None for missing or unreadable state."""
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def save_timer(path, data):
    """Persist timer data using the existing on-disk JSON format."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def clear_timer(path):
    """Best-effort removal used by parent controls and recovery paths."""
    try:
        if os.path.isfile(path):
            os.remove(path)
    except Exception:
        pass


def timer_status(data, config, now=None):
    """Return the stable public timer status payload."""
    if not data or not isinstance(data, dict):
        return {
            "active": False,
            "expired": False,
            "warning": False,
            "remainingSeconds": 0,
            "totalMinutes": 0,
        }
    end_time = data.get("end_time", 0)
    total_minutes = data.get("totalMinutes", 0)
    warning_minutes = config.get("timerWarningMinutes", 5)
    current_time = time.time() if now is None else now
    remaining = int(end_time - current_time)
    if remaining <= 0:
        return {
            "active": True,
            "expired": True,
            "warning": False,
            "remainingSeconds": 0,
            "totalMinutes": total_minutes,
        }
    warning_seconds = warning_minutes * 60
    return {
        "active": True,
        "expired": False,
        "warning": remaining <= warning_seconds,
        "remainingSeconds": remaining,
        "totalMinutes": total_minutes,
    }
