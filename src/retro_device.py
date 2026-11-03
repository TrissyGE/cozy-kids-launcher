"""Report observable Linux device capabilities without launching a game."""

from dataclasses import dataclass
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from package_provider import detect_native_provider, read_os_release


@dataclass(frozen=True)
class System:
    name: str
    emulator: str
    catalog: str = ""
    memory: int = 0
    opengl: tuple = ()
    vulkan: tuple = ()
    x86_flag: str = ""


SYSTEMS = (
    System("Game Boy / Game Boy Color / Game Boy Advance", "mGBA", "mgba-qt"),
    System("NES / Super Nintendo / Master System / Game Gear", "Mednafen", "mednafen"),
    System("PlayStation", "RetroArch / PCSX ReARMed", "retroarch"),
    System("PlayStation 2", "PCSX2", memory=8, opengl=(3, 3), vulkan=(1, 1), x86_flag="sse4_1"),
    System("GameCube / Wii", "Dolphin", memory=2),
    System("Xbox", "xemu", opengl=(4, 0)),
    System("Wii U", "Cemu", memory=4, opengl=(4, 5), vulkan=(1, 2)),
    System("PlayStation 3", "RPCS3"),
)


def _cpu_flags():
    try:
        with Path("/proc/cpuinfo").open(encoding="ascii", errors="replace") as handle:
            text = handle.read(256 * 1024)
    except OSError:
        return None
    groups = [set(line.split()) for line in re.findall(r"^flags\s*:\s*(.+)$", text, re.MULTILINE)]
    return set.intersection(*groups) if groups else None


def _memory_gib():
    try:
        size = os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
        return round(size / (1024 ** 3), 1) if size > 0 else None
    except (AttributeError, OSError, ValueError):
        return None


def _graphics_output(command):
    executable = shutil.which(command[0])
    if executable is None:
        return ""
    try:
        result = subprocess.run(
            [executable, *command[1:]], capture_output=True, text=True, errors="replace",
            env={**os.environ, "LC_ALL": "C"}, timeout=2, check=True,
        )
        return result.stdout[:128 * 1024]
    except (OSError, subprocess.SubprocessError):
        return ""


def _opengl_version(output):
    if re.search(r"Accelerated:\s+no|llvmpipe|softpipe|swrast", output, re.IGNORECASE):
        return ()
    match = re.search(r"^OpenGL (?:core profile )?version string:\s+(\d+)\.(\d+)", output, re.MULTILINE)
    return tuple(map(int, match.groups())) if match else ()


def _vulkan_version(output):
    versions = []
    for device in re.split(r"^GPU\d+:\s*$", output, flags=re.MULTILINE)[1:]:
        if not re.search(r"deviceType\s*=\s*(?:PHYSICAL_DEVICE_TYPE_)?(?:DISCRETE|INTEGRATED|VIRTUAL)_GPU", device):
            continue
        match = re.search(r"apiVersion\s*=\s*(\d+)\.(\d+)", device)
        if match:
            versions.append(tuple(map(int, match.groups())))
    return max(versions, default=())


def _compatibility(system, architecture, flags, memory, opengl, vulkan):
    if system.catalog == "retroarch" and architecture and architecture != "x86_64":
        return "incompatible", "architecture"
    if system.x86_flag and architecture == "x86_64" and flags is not None and system.x86_flag not in flags:
        return "incompatible", "cpu"
    # Linux reports usable RAM after reserving some of the installed memory.
    if system.memory and memory is not None and memory + 0.5 < system.memory:
        return "limited", "memory"
    graphics = [(available, required) for available, required in
                ((opengl, system.opengl), (vulkan, system.vulkan)) if required]
    if graphics and all(available and available < required for available, required in graphics):
        return "limited", "graphics"
    return "untested", "performance"


def retro_device_report(recommendations, core_ready):
    machine = platform.machine().lower()
    architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    flags = _cpu_flags() if architecture == "x86_64" else None
    memory = _memory_gib()
    opengl = _opengl_version(_graphics_output(("glxinfo", "-B")))
    vulkan = _vulkan_version(_graphics_output(("vulkaninfo", "--summary")))
    release = read_os_release()
    apt_route = release.get("ID") in {"ubuntu", "linuxmint", "zorin"} and detect_native_provider(release) == "apt"
    catalog = {item["id"]: item for item in recommendations if item.get("retroEmulator")}
    rows = []
    for system in SYSTEMS:
        status, reason = _compatibility(system, architecture, flags, memory, opengl, vulkan)
        recipe = catalog.get(system.catalog, {})
        installed = recipe.get("installed") and (system.catalog != "retroarch" or core_ready)
        available = apt_route and recipe.get("package")
        if system.catalog == "retroarch" and recipe.get("installed") and architecture == "x86_64":
            available = True  # The Parent panel can supply the core for an existing RetroArch.
        route = "installed" if installed else "available" if available else "unavailable"
        rows.append({"system": system.name, "emulator": system.emulator, "catalog": system.catalog,
                     "status": status, "reason": reason, "route": route})
    return {"architecture": architecture, "memoryGiB": memory,
            "opengl": ".".join(map(str, opengl)), "vulkan": ".".join(map(str, vulkan)), "systems": rows}
