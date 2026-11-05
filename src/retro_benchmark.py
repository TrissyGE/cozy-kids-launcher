"""One bounded, opt-in, Parent-only local core benchmark with private results."""

import copy
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
import secrets
import signal
import statistics
import subprocess
import sys
import tempfile
import threading

from config_store import atomic_write_config
import retro_games
from retro_workload import TRIANGLES, WORKLOAD_VERSION, workload_sha256


TIMEOUT_SECONDS = 25
MAX_RESULT_BYTES = 16384
FRAMES = 240
WARMUP = 60
ACTIVE = {"running", "canceling"}
ERRORS = {"failed", "timeout", "interrupted", "canceled"}
HEX24 = re.compile(r"[0-9a-f]{24}")
HEX16 = re.compile(r"[0-9a-f]{16}")


class BenchmarkError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _finite(value, minimum, maximum):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def summarize_worker(data):
    """Validate actual workload execution before deriving any performance result."""
    if not isinstance(data, dict):
        raise ValueError("Invalid result")
    if (data.get("workload") != WORKLOAD_VERSION or data.get("workloadSha256") != workload_sha256()
            or data.get("coreSha256") != retro_games.PS1_CORE_SHA256
            or data.get("frames") != FRAMES or type(data["frames"]) is not int
            or data.get("warmupFrames") != WARMUP
            or data.get("videoFrames") != FRAMES or data.get("advancedFrames") != FRAMES
            or type(data.get("distinctImages")) is not int or not 24 <= data["distinctImages"] <= FRAMES
            or not _finite(data.get("targetFps"), 59, 61)
            or not _finite(data.get("elapsedMs"), .001, TIMEOUT_SECONDS * 1000)):
        raise ValueError("Unvalidated workload")
    expected_options = {"pcsx_rearmed_bios": "HLE", "pcsx_rearmed_region": "NTSC",
                        "pcsx_rearmed_drc": "enabled", "pcsx_rearmed_frameskip_type": "disabled"}
    modes = data.get("videoModes")
    if (data.get("options") != expected_options or not isinstance(modes, list) or len(modes) != 1
            or modes[0] not in ([320, 240, 0], [320, 240, 1], [320, 240, 2])):
        raise ValueError("Unexpected workload settings")
    samples = data.get("frameTimesMs")
    if (not isinstance(samples, list) or len(samples) != FRAMES
            or any(not _finite(value, 0, TIMEOUT_SECONDS * 1000) for value in samples)
            or sum(samples) <= 0 or data["elapsedMs"] + 1 < sum(samples)):
        raise ValueError("Invalid frame measurements")
    version = data.get("coreLibraryVersion")
    if not isinstance(version, str) or not re.fullmatch(r"[0-9A-Za-z ._()-]{1,64}", version):
        raise ValueError("Invalid core version")
    fps = round(FRAMES * 1000 / data["elapsedMs"], 2)
    p95 = round(sorted(samples)[math.ceil(FRAMES * .95) - 1], 4)
    target = data["targetFps"]
    # This is a result for this workload only, never a per-game recommendation.
    result = {"workload": WORKLOAD_VERSION, "workloadSha256": workload_sha256(),
              "coreVersion": retro_games.PS1_CORE_VERSION, "coreLibraryVersion": version,
              "coreSha256": retro_games.PS1_CORE_SHA256, "frames": FRAMES, "warmupFrames": WARMUP,
              "videoFrames": FRAMES, "advancedFrames": FRAMES, "distinctImages": int(data["distinctImages"]),
              "throughputFps": fps, "targetFps": target,
              "medianFrameMs": round(statistics.median(samples), 4), "p95FrameMs": round(p95, 4),
              "maxFrameMs": round(max(samples), 4), "elapsedMs": data["elapsedMs"],
              "status": "within-budget" if fps >= target * 1.2 and p95 <= 1000 / target else "limited",
              "settings": {"frontend": "headless-libretro-validation", "renderer": "software",
                           "bios": "HLE", "region": "NTSC", "video": modes[0], "audio": "discard",
                           "trianglesPerFrame": TRIANGLES, "paced": False, "options": expected_options},
              "desktopRenderingMeasured": False, "gameCompatibility": "unknown"}
    return result


def _stored_result(result):
    """Discard malformed private state without echoing arbitrary saved fields."""
    if not isinstance(result, dict):
        return None
    scalar_keys = {"workload", "workloadSha256", "coreVersion", "coreLibraryVersion", "coreSha256",
                   "frames", "warmupFrames", "videoFrames", "advancedFrames", "distinctImages", "throughputFps",
                   "targetFps", "medianFrameMs", "p95FrameMs", "maxFrameMs", "elapsedMs", "status", "settings",
                   "desktopRenderingMeasured", "gameCompatibility"}
    if set(result) != scalar_keys:
        return None
    # Revalidate stored results against the same arithmetic/identity boundary.
    # The per-frame samples are intentionally not persisted.
    if (result.get("workload") != WORKLOAD_VERSION or result.get("workloadSha256") != workload_sha256()
            or result.get("coreSha256") != retro_games.PS1_CORE_SHA256
            or result.get("coreVersion") != retro_games.PS1_CORE_VERSION
            or result.get("frames") != FRAMES or result.get("warmupFrames") != WARMUP
            or result.get("videoFrames") != FRAMES or result.get("advancedFrames") != FRAMES
            or result.get("desktopRenderingMeasured") is not False or result.get("gameCompatibility") != "unknown"
            or result.get("status") not in {"within-budget", "limited"}):
        return None
    for key in ("throughputFps", "targetFps", "medianFrameMs", "p95FrameMs", "maxFrameMs", "elapsedMs", "distinctImages"):
        if not _finite(result.get(key), 0, 1_000_000):
            return None
    if (not _finite(result["elapsedMs"], .001, TIMEOUT_SECONDS * 1000)
            or not _finite(result["targetFps"], 59, 61)
            or type(result["distinctImages"]) is not int or not 24 <= result["distinctImages"] <= FRAMES
            or abs(result["throughputFps"] - FRAMES * 1000 / result["elapsedMs"]) > .1
            or not result["medianFrameMs"] <= result["p95FrameMs"] <= result["maxFrameMs"]):
        return None
    status = "within-budget" if result["throughputFps"] >= result["targetFps"] * 1.2 and result["p95FrameMs"] <= 1000 / result["targetFps"] else "limited"
    if result["status"] != status:
        return None
    expected_settings = {"frontend": "headless-libretro-validation", "renderer": "software", "bios": "HLE",
                         "region": "NTSC", "audio": "discard", "trianglesPerFrame": TRIANGLES, "paced": False,
                         "options": {"pcsx_rearmed_bios": "HLE", "pcsx_rearmed_region": "NTSC",
                                     "pcsx_rearmed_drc": "enabled", "pcsx_rearmed_frameskip_type": "disabled"}}
    settings = result.get("settings")
    if not isinstance(settings, dict) or settings.get("video") not in ([320, 240, 0], [320, 240, 1], [320, 240, 2]):
        return None
    if {key: value for key, value in settings.items() if key != "video"} != expected_settings:
        return None
    if not isinstance(result.get("coreLibraryVersion"), str) or not re.fullmatch(r"[0-9A-Za-z ._()-]{1,64}", result["coreLibraryVersion"]):
        return None
    return copy.deepcopy(result)


class RetroBenchmark:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.worker = None
        self.process = None
        self.cancel_requested = False
        self.closed = False
        self.state = {"status": "idle"}
        self._load()

    def _load(self):
        try:
            with self.path.open("rb") as stream:
                payload = stream.read(MAX_RESULT_BYTES + 1)
            if len(payload) > MAX_RESULT_BYTES:
                return
            data = json.loads(payload)
            if (not isinstance(data, dict) or data.get("format") != 1 or not isinstance(data.get("job"), dict)):
                return
            job = data["job"]
            if (not isinstance(job.get("jobId"), str) or not HEX16.fullmatch(job["jobId"])
                    or not isinstance(job.get("scopeKey"), str) or not HEX24.fullmatch(job["scopeKey"])
                    or not isinstance(job.get("startedAt"), str) or len(job["startedAt"]) > 40):
                return
            datetime.fromisoformat(job["startedAt"])
            base = {key: job[key] for key in ("jobId", "scopeKey", "startedAt")}
            status = job.get("status")
            if status in ACTIVE:
                self.state = {**base, "status": "error", "error": "interrupted"}
                self._save()
            elif status == "complete" and (result := _stored_result(job.get("result"))):
                self.state = {**base, "status": status, "result": result}
            elif status in {"error", "canceled"} and job.get("error") in ERRORS:
                self.state = {**base, "status": status, "error": job["error"]}
        except (OSError, ValueError, TypeError):
            return

    def _save(self):
        atomic_write_config(str(self.path), {"format": 1, "job": self.state})

    def snapshot(self):
        with self.lock:
            return copy.deepcopy(self.state)

    def start(self, state_root, scope_key):
        with self.lock:
            if self.closed:
                raise BenchmarkError("unavailable")
            if sys.platform != "linux":
                raise BenchmarkError("unavailable")
            if self.state["status"] in ACTIVE or (self.worker is not None and self.worker.is_alive()):
                raise BenchmarkError("busy")
            if not isinstance(scope_key, str) or not HEX24.fullmatch(scope_key):
                raise ValueError("Invalid benchmark scope")
            payload = retro_games.load_ps1_core_payload(state_root)
            if payload is None:
                raise BenchmarkError("unavailable")
            # Use immutable verified bytes. A later edit to the installed core
            # cannot change executable code after the Parent started this job.
            self.cancel_requested = False
            previous = self.state
            self.state = {"status": "running", "jobId": secrets.token_hex(8), "scopeKey": scope_key,
                          "startedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
            try:
                self._save()
            except OSError:
                self.state = previous
                raise
            self.worker = threading.Thread(target=self._run, args=(payload,), daemon=True)
            try:
                self.worker.start()
            except RuntimeError:
                self.worker = None
                self.state = previous
                self._save()
                raise BenchmarkError("failed") from None
            return self.snapshot()

    def _command(self, directory):
        return [sys.executable, str(Path(__file__).with_name("retro_benchmark_worker.py")),
                str(directory), "--parent", str(os.getpid())]

    def _run(self, payload):
        try:
            with tempfile.TemporaryDirectory(prefix="cozy-core-test-") as temporary, tempfile.TemporaryFile() as output:
                directory = Path(temporary)
                (directory / retro_games.PS1_CORE_FILENAME).write_bytes(payload)
                environment = {**os.environ, "HOME": temporary, "XDG_CONFIG_HOME": temporary,
                               "XDG_DATA_HOME": temporary, "XDG_CACHE_HOME": temporary, "XDG_STATE_HOME": temporary,
                               "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"}
                with self.lock:
                    if self.cancel_requested:
                        raise BenchmarkError("canceled")
                    self.process = subprocess.Popen(self._command(directory), cwd=directory, env=environment,
                                                    stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.DEVNULL,
                                                    start_new_session=True)
                    process = self.process
                try:
                    code = process.wait(timeout=TIMEOUT_SECONDS)
                except subprocess.TimeoutExpired:
                    self._signal(signal.SIGKILL)
                    process.wait(timeout=3)
                    raise BenchmarkError("timeout") from None
                if code:
                    raise BenchmarkError("timeout" if code in (-signal.SIGXCPU, -signal.SIGKILL) else "failed")
                output.seek(0)
                value = output.read(MAX_RESULT_BYTES + 1)
                if len(value) > MAX_RESULT_BYTES:
                    raise BenchmarkError("failed")
                result = summarize_worker(json.loads(value))
            with self.lock:
                if self.cancel_requested:
                    raise BenchmarkError("canceled")
                self.state.update(status="complete", result=result)
                self._save()
        except (OSError, ValueError, BenchmarkError, subprocess.SubprocessError) as error:
            with self.lock:
                code = "canceled" if self.cancel_requested else error.code if isinstance(error, BenchmarkError) else "failed"
                self.state.pop("result", None)
                self.state.update(status="canceled" if code == "canceled" else "error", error=code)
                try:
                    self._save()
                except OSError:
                    pass
        finally:
            with self.lock:
                self.process = None

    def _signal(self, signum):
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                try:
                    os.killpg(self.process.pid, signum)
                except ProcessLookupError:
                    pass

    def cancel(self, job_id=None):
        with self.lock:
            if job_id is not None and job_id != self.state.get("jobId"):
                raise BenchmarkError("stale")
            if self.state["status"] in ACTIVE:
                self.cancel_requested = True
                self.state["status"] = "canceling"
                self._signal(signal.SIGTERM)
            return self.snapshot()

    def clear(self, job_id):
        with self.lock:
            if job_id != self.state.get("jobId"):
                raise BenchmarkError("stale")
            if self.state["status"] in ACTIVE:
                raise BenchmarkError("busy")
            previous = self.state
            self.state = {"status": "idle"}
            try:
                self._save()
            except OSError:
                self.state = previous
                raise
            return self.snapshot()

    def close(self):
        with self.lock:
            self.closed = True
            self.cancel()
        worker = self.worker
        if worker is not None:
            worker.join(timeout=2)
            if worker.is_alive():
                self._signal(signal.SIGKILL)
                worker.join(timeout=3)


def attach_benchmark(report, snapshot):
    """Use a previous result only for the same observed device/core/package scope."""
    result = _stored_result(snapshot.get("result")) if snapshot.get("status") == "complete" else None
    if result is not None:
        for row in report["systems"]:
            if row["catalog"] == "retroarch" and row["resultKey"] == snapshot.get("scopeKey"):
                row["performanceMeasured"] = True
                row["performance"] = result
                if row["status"] == "untested":
                    row["status"] = "measured"
    return report
