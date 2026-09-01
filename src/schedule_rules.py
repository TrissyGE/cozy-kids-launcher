"""Validation and local-time evaluation for child availability schedules."""

from datetime import datetime
import re


WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
MAX_WINDOWS_PER_DAY = 4
_TIME_PATTERN = re.compile(r"(?:[01][0-9]|2[0-3]):[0-5][0-9]")


def _minute_of_day(value, field, allow_end_of_day=False):
    if allow_end_of_day and value == "24:00":
        return 24 * 60
    if not isinstance(value, str) or not _TIME_PATTERN.fullmatch(value):
        raise ValueError(f"{field} must use HH:MM in local time")
    hour, minute = (int(part) for part in value.split(":"))
    return hour * 60 + minute


def validate_schedule(value, field="weeklySchedule"):
    """Return a bounded, normalized weekly availability schedule."""
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object")
    unknown = set(value).difference(("enabled", "days"))
    if unknown:
        raise ValueError(f"{field} contains unsupported fields")
    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError(f"{field}.enabled must be a boolean")
    days = value.get("days", {})
    if not isinstance(days, dict) or len(days) > len(WEEKDAYS):
        raise ValueError(f"{field}.days must be a weekly object")

    normalized_days = {}
    for day in WEEKDAYS:
        if day not in days:
            continue
        windows = days[day]
        if not isinstance(windows, list) or len(windows) > MAX_WINDOWS_PER_DAY:
            raise ValueError(
                f"{field}.days.{day} must contain at most "
                f"{MAX_WINDOWS_PER_DAY} windows"
            )
        normalized = []
        previous_end = -1
        for index, window in enumerate(windows):
            window_field = f"{field}.days.{day}[{index}]"
            if not isinstance(window, dict) or set(window) != {"start", "end"}:
                raise ValueError(f"{window_field} must contain start and end")
            start = window["start"]
            end = window["end"]
            start_minute = _minute_of_day(start, f"{window_field}.start")
            end_minute = _minute_of_day(
                end,
                f"{window_field}.end",
                allow_end_of_day=True,
            )
            if start_minute >= end_minute:
                raise ValueError(f"{window_field} must end after it starts")
            if start_minute < previous_end:
                raise ValueError(f"{field}.days.{day} windows must not overlap")
            normalized.append({"start": start, "end": end})
            previous_end = end_minute
        normalized_days[day] = normalized

    unknown_days = set(days).difference(WEEKDAYS)
    if unknown_days:
        raise ValueError(f"{field}.days contains an invalid weekday")
    return {"enabled": enabled, "days": normalized_days}


def validate_app_availability(value, tile_id_pattern, maximum):
    """Validate the per-tile schedules stored in one child profile."""
    if not isinstance(value, dict) or len(value) > maximum:
        raise ValueError("appAvailability must be an object with a bounded size")
    normalized = {}
    for tile_id, schedule in value.items():
        if not isinstance(tile_id, str) or not tile_id_pattern.fullmatch(tile_id):
            raise ValueError("appAvailability contains an invalid tile id")
        normalized[tile_id] = validate_schedule(
            schedule,
            field=f"appAvailability.{tile_id}",
        )
    return normalized


def schedule_is_open(schedule, when=None):
    """Return whether a validated schedule permits the supplied local time."""
    if not schedule or not schedule.get("enabled", False):
        return True
    current = datetime.now().astimezone() if when is None else when
    day = WEEKDAYS[current.weekday()]
    minute = current.hour * 60 + current.minute
    for window in schedule.get("days", {}).get(day, []):
        start = _minute_of_day(window["start"], "schedule.start")
        end = _minute_of_day(
            window["end"],
            "schedule.end",
            allow_end_of_day=True,
        )
        if start <= minute < end:
            return True
    return False


def tile_availability(config, tile_id, when=None):
    """Evaluate profile-wide and per-tile rules without starting any process."""
    if not schedule_is_open(config.get("weeklySchedule"), when=when):
        return {"allowed": False, "reason": "profile_schedule"}
    app_schedule = config.get("appAvailability", {}).get(tile_id)
    if not schedule_is_open(app_schedule, when=when):
        return {"allowed": False, "reason": "app_schedule"}
    return {"allowed": True, "reason": ""}


def availability_summary(config, when=None):
    """Return the child-safe status used by the launcher interface."""
    profile_allowed = schedule_is_open(config.get("weeklySchedule"), when=when)
    blocked = []
    for tile in config.get("tiles", []):
        tile_id = tile.get("id")
        if tile_id and not tile_availability(config, tile_id, when=when)["allowed"]:
            blocked.append(tile_id)
    return {
        "profileAllowed": profile_allowed,
        "blockedTileIds": blocked,
    }
