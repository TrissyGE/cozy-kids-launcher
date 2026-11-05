"""Run only the reviewed PS1 core and generated workload in a disposable process."""

import argparse
import ctypes as c
import hashlib
import json
import math
import os
from pathlib import Path
import resource
import sys
import time

from retro_games import PS1_CORE_BYTES, PS1_CORE_FILENAME, PS1_CORE_SHA256
from retro_workload import SIGNATURE, SIGNATURE_OFFSET, WORKLOAD_VERSION, generated_ps1_exe, workload_sha256


WARMUP_FRAMES = 60
MEASURED_FRAMES = 240
OPTIONS = {
    b"pcsx_rearmed_bios": b"HLE", b"pcsx_rearmed_region": b"NTSC",
    b"pcsx_rearmed_drc": b"enabled",
    b"pcsx_rearmed_frameskip_type": b"disabled",
}


class GameInfo(c.Structure):
    _fields_ = [("path", c.c_char_p), ("data", c.c_void_p), ("size", c.c_size_t), ("meta", c.c_char_p)]


class Variable(c.Structure):
    _fields_ = [("key", c.c_char_p), ("value", c.c_char_p)]


class SystemInfo(c.Structure):
    _fields_ = [("name", c.c_char_p), ("version", c.c_char_p), ("extensions", c.c_char_p),
                ("fullpath", c.c_bool), ("extract", c.c_bool)]


class Geometry(c.Structure):
    _fields_ = [("width", c.c_uint), ("height", c.c_uint), ("max_width", c.c_uint),
                ("max_height", c.c_uint), ("aspect", c.c_float)]


class Timing(c.Structure):
    _fields_ = [("fps", c.c_double), ("sample_rate", c.c_double)]


class AVInfo(c.Structure):
    _fields_ = [("geometry", Geometry), ("timing", Timing)]


Environment = c.CFUNCTYPE(c.c_bool, c.c_uint, c.c_void_p)
Video = c.CFUNCTYPE(None, c.c_void_p, c.c_uint, c.c_uint, c.c_size_t)
Audio = c.CFUNCTYPE(None, c.c_int16, c.c_int16)
AudioBatch = c.CFUNCTYPE(c.c_size_t, c.c_void_p, c.c_size_t)
InputPoll = c.CFUNCTYPE(None)
InputState = c.CFUNCTYPE(c.c_int16, c.c_uint, c.c_uint, c.c_uint, c.c_uint)


def limits(parent):
    # Set this inside the new process, never with preexec_fn in the threaded server.
    libc = c.CDLL(None, use_errno=True)
    if libc.prctl(1, 15, 0, 0, 0) != 0 or os.getppid() != parent:
        raise RuntimeError("Benchmark parent is unavailable")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (15, 16))
    resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024, 768 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024 * 1024, 8 * 1024 * 1024))


def measure(directory):
    directory = Path(directory).resolve()
    core_path = directory / PS1_CORE_FILENAME
    payload = core_path.read_bytes()
    if len(payload) != PS1_CORE_BYTES or hashlib.sha256(payload).hexdigest() != PS1_CORE_SHA256:
        raise ValueError("Unreviewed core")
    content = directory / "cozy-generated.exe"
    content.write_bytes(generated_ps1_exe())
    options, queried = {}, {}
    pointers = {9: bytes(directory), 30: bytes(directory), 31: bytes(directory)}
    video_frames, image_hashes, measuring = 0, set(), False
    pixel_format, video_modes = 0, set()

    @Environment
    def environment(command, data):
        nonlocal pixel_format
        if command in pointers and data:
            c.cast(data, c.POINTER(c.c_char_p))[0] = pointers[command]
            return True
        if command == 3 and data:  # frame duplication API
            c.cast(data, c.POINTER(c.c_bool))[0] = True
            return True
        if command == 52 and data:  # use the bounded legacy option definitions
            c.cast(data, c.POINTER(c.c_uint))[0] = 0
            return True
        if command == 17 and data:
            c.cast(data, c.POINTER(c.c_bool))[0] = False
            return True
        if command == 16 and data:
            entries = c.cast(data, c.POINTER(Variable))
            for index in range(256):
                entry = entries[index]
                if not entry.key:
                    return True
                description = entry.value or b""
                choices = description.partition(b"; ")[2].split(b"|")
                selected = OPTIONS.get(entry.key, choices[0])
                if selected in choices:
                    options[entry.key] = selected
            return False
        if command == 15 and data:
            entry = c.cast(data, c.POINTER(Variable)).contents
            entry.value = options.get(entry.key)
            if entry.value is not None:
                queried[entry.key] = entry.value
            return True
        if command == 10 and data:
            value = c.cast(data, c.POINTER(c.c_int))[0]
            if value not in (0, 1, 2):
                return False
            pixel_format = value
            return True
        if command in (11, 37):
            return True
        return False

    @Video
    def video(data, width, height, pitch):
        nonlocal video_frames
        if measuring and data and data != c.c_void_p(-1).value and (
                0 < width <= 1024 and 0 < height <= 1024 and 0 < pitch <= 8192):
            video_frames += 1
            video_modes.add((width, height, pixel_format))
            image_hashes.add(hashlib.sha256(c.string_at(data, height * pitch)).digest())

    callbacks = {"environment": environment, "video_refresh": video,
                 "audio_sample": Audio(lambda *_: None),
                 "audio_sample_batch": AudioBatch(lambda _, count: count),
                 "input_poll": InputPoll(lambda: None), "input_state": InputState(lambda *_: 0)}
    core = c.CDLL(str(core_path))
    for name, callback in callbacks.items():
        setter = getattr(core, "retro_set_" + name)
        setter.argtypes, setter.restype = [type(callback)], None
        setter(callback)
    for name in ("init", "run", "unload_game", "deinit"):
        function = getattr(core, "retro_" + name)
        function.argtypes, function.restype = [], None
    for name, arguments, result in (
        ("api_version", [], c.c_uint), ("get_system_info", [c.POINTER(SystemInfo)], None),
        ("load_game", [c.POINTER(GameInfo)], c.c_bool),
        ("get_system_av_info", [c.POINTER(AVInfo)], None),
        ("get_memory_data", [c.c_uint], c.c_void_p), ("get_memory_size", [c.c_uint], c.c_size_t),
    ):
        function = getattr(core, "retro_" + name)
        function.argtypes, function.restype = arguments, result
    if core.retro_api_version() != 1:
        raise ValueError("Unsupported libretro API")
    info = SystemInfo()
    core.retro_get_system_info(c.byref(info))
    core.retro_init()
    loaded = False
    try:
        game = GameInfo(bytes(content), None, 0, None)
        loaded = core.retro_load_game(c.byref(game))
        if not loaded:
            raise ValueError("Generated content rejected")
        av = AVInfo()
        core.retro_get_system_av_info(c.byref(av))
        if not math.isfinite(av.timing.fps) or not 59 <= av.timing.fps <= 61:
            raise ValueError("Unexpected frame timing")
        for _ in range(WARMUP_FRAMES):
            core.retro_run()
        # Settings are reported from options actually queried by this core,
        # rather than assuming that it accepted a desired configuration.
        for key, value in OPTIONS.items():
            if queried.get(key) != value:
                raise ValueError(f"Required benchmark setting is unavailable: {key!r}, {queried.get(key)!r}")
        ram, size = core.retro_get_memory_data(2), core.retro_get_memory_size(2)
        if not ram or size < SIGNATURE_OFFSET + 8:
            raise ValueError("System RAM unavailable")
        def counter():
            if c.c_uint32.from_address(ram + SIGNATURE_OFFSET).value != SIGNATURE:
                raise ValueError("Workload signature missing")
            return c.c_uint32.from_address(ram + SIGNATURE_OFFSET + 4).value
        before = counter()
        samples, measuring = [], True
        started = time.perf_counter_ns()
        for _ in range(MEASURED_FRAMES):
            frame_started = time.perf_counter_ns()
            core.retro_run()
            samples.append((time.perf_counter_ns() - frame_started) / 1_000_000)
        elapsed = (time.perf_counter_ns() - started) / 1_000_000
        advanced = counter() - before
        return {"workload": WORKLOAD_VERSION, "workloadSha256": workload_sha256(),
                "coreSha256": PS1_CORE_SHA256, "coreLibraryVersion": (info.version or b"").decode("ascii"),
                "frames": MEASURED_FRAMES, "warmupFrames": WARMUP_FRAMES,
                "videoFrames": video_frames, "distinctImages": len(image_hashes), "advancedFrames": advanced,
                "videoModes": sorted(video_modes),
                "targetFps": av.timing.fps, "elapsedMs": elapsed, "frameTimesMs": samples,
                "options": {key.decode(): value.decode() for key, value in OPTIONS.items()}}
    finally:
        if loaded:
            core.retro_unload_game()
        core.retro_deinit()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    parser.add_argument("--parent", type=int, required=True)
    args = parser.parse_args()
    output = os.dup(1)
    # Native core logging must never corrupt the private machine-readable result.
    with open(os.devnull, "wb") as null:
        os.dup2(null.fileno(), 1)
        os.dup2(null.fileno(), 2)
    limits(args.parent)
    os.chdir(args.directory)
    result = measure(args.directory)
    with os.fdopen(output, "w", encoding="utf-8") as stream:
        json.dump(result, stream, allow_nan=False)
        stream.write("\n")


if __name__ == "__main__":
    main()
