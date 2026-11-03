"""Private per-profile daily usage, independent of optional activity history."""

from dataclasses import dataclass
from datetime import date, datetime, time as midnight, timedelta
import json
from pathlib import Path
import re
import secrets
import time

from config_store import atomic_write_config


CHECKPOINT_MS = 2_000
HEARTBEAT_SECONDS = 15
# Keep the remaining seconds exactly representable in browser JSON.
MAX_EXTRA_MINUTES = (2**53 - 1) // 60 - 1440


@dataclass
class Session:
    profile: str
    tile: str
    token: str
    last_ms: int
    day: str
    alive: object
    heartbeat: float


class DailyBudget:
    """One tracked tile. Callers serialize admissions, checkpoints and policy edits."""

    def __init__(self, path, clock=time.monotonic, wall=datetime.now):
        self.path = Path(path)
        self.clock = clock
        self.wall = wall
        self.session = None

    def _read(self):
        try:
            with self.path.open(encoding="utf-8") as stream:
                data = json.loads(stream.read(16385))
        except FileNotFoundError:
            return {}
        if not isinstance(data, dict) or len(data) > 20:
            raise ValueError("Invalid daily budget storage")
        for profile, entry in data.items():
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", profile) or not isinstance(entry, dict):
                raise ValueError("Invalid budget profile")
            day = entry.get("day", "")
            if not isinstance(day, str) or date.fromisoformat(day).isoformat() != day or day >= "9999-12-31":
                raise ValueError("Invalid budget day")
            for key, maximum in (("usedMs", 172_800_000), ("extra", MAX_EXTRA_MINUTES)):
                if type(entry.get(key)) is not int or not 0 <= entry[key] <= maximum:
                    raise ValueError("Invalid budget value")
        return data

    def _write(self, data):
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        atomic_write_config(str(self.path), data)

    def _entry(self, data, profile):
        today = self.wall().date().isoformat()
        entry = data.get(profile)
        if entry is None or entry["day"] < today:
            entry = {"day": today, "usedMs": 0, "extra": 0}
            data[profile] = entry
        return entry

    def _now_ms(self):
        return int(self.clock() * 1000)

    def status(self, profile, minutes):
        if not minutes:
            return {"enabled": False}
        try:
            entry = self._entry(self._read(), profile)
        except (OSError, ValueError):
            return {"enabled": True, "remainingSeconds": 0, "unavailable": True}
        used = entry["usedMs"]
        session = self.session
        if session and session.profile == profile and session.day == entry["day"]:
            used = max(0, used + self._now_ms() - session.last_ms - CHECKPOINT_MS)
        remaining = max(0, (minutes + entry["extra"]) * 60_000 - used)
        result = {"enabled": True, "remainingSeconds": (remaining + 999) // 1000}
        if not remaining:
            next_day = date.fromisoformat(entry["day"]) + timedelta(days=1)
            result["nextAvailableAt"] = int(datetime.combine(next_day, midnight.min).timestamp())
        return result

    def begin(self, profile, tile, minutes, alive=None):
        if self.session:
            raise ValueError("Finish the previous budget session before starting another")
        if not minutes:
            return ""
        data = self._read()
        entry = self._entry(data, profile)
        if entry["usedMs"] >= (minutes + entry["extra"]) * 60_000:
            raise ValueError("The daily budget is exhausted")
        entry["usedMs"] += CHECKPOINT_MS
        self._write(data)
        token = secrets.token_urlsafe(24) if alive is None else ""
        self.session = Session(profile, tile, token, self._now_ms(), entry["day"], alive, self.clock())
        return token

    def _checkpoint(self, ending):
        session = self.session
        now = self._now_ms()
        elapsed = max(0, now - session.last_ms)
        data = self._read()
        entry = self._entry(data, session.profile)
        credit = CHECKPOINT_MS if session.day == entry["day"] else 0
        reserve = 0 if ending else CHECKPOINT_MS
        entry["usedMs"] = min(172_800_000, max(0, entry["usedMs"] + elapsed - credit + reserve))
        self._write(data)
        session.day = entry["day"]
        session.last_ms = now

    def finish(self):
        if self.session:
            try:
                self._checkpoint(ending=True)
            finally:
                self.session = None

    def matches(self, token, profile, tile=None):
        session = self.session
        return bool(session and isinstance(token, str) and re.fullmatch(r"[A-Za-z0-9_-]{1,64}", token) and session.token
                    and session.profile == profile and (tile is None or session.tile == tile)
                    and self.clock() - session.heartbeat <= HEARTBEAT_SECONDS
                    and secrets.compare_digest(token, session.token))

    def heartbeat(self, token, profile, finished=False):
        if not self.matches(token, profile):
            return False
        if finished:
            self.finish()
        else:
            self.session.heartbeat = self.clock()
        return True

    def tick(self, profile, minutes):
        """Return whether a tracked native app must be stopped."""
        session = self.session
        if not session:
            return False
        if session.alive is not None and not session.alive():
            self.finish()
            return False
        if session.token and self.clock() - session.heartbeat > HEARTBEAT_SECONDS:
            self.finish()
            return False
        state = self.status(profile, minutes)
        if session.profile != profile or (minutes and not state.get("remainingSeconds")):
            self.finish()
            return session.alive is not None
        if not minutes:
            self.finish()
            return False
        if self._now_ms() - session.last_ms >= CHECKPOINT_MS:
            self._checkpoint(ending=False)
        return False

    def extend(self, profile, minutes, extra_minutes):
        if not minutes:
            raise ValueError("This profile has no daily budget")
        data = self._read()
        entry = self._entry(data, profile)
        if type(extra_minutes) is not int or not 1 <= extra_minutes <= MAX_EXTRA_MINUTES - entry["extra"]:
            raise ValueError("Invalid extra time")
        entry["extra"] += extra_minutes
        self._write(data)
        return self.status(profile, minutes)

    def retain_profiles(self, profile_ids):
        data = self._read()
        retained = {profile: entry for profile, entry in data.items() if profile in profile_ids}
        if len(retained) != len(data):
            self._write(retained)

    def forget(self, profile):
        data = self._read()
        if profile in data:
            del data[profile]
            self._write(data)
