"""Report observable Linux device capabilities without launching a game."""

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from package_provider import catalog_package_route, detect_native_provider, mapped_package, read_os_release


@dataclass(frozen=True)
class System:
    name: str
    emulator: str
    catalog: str = ""
    memory: int = 0
    opengl: tuple = ()
    vulkan: tuple = ()
    x86_flag: str = ""
    architectures: tuple = ()
    minimum_bits: int = 0
    extensions: tuple = ()
    sources: tuple = ()


REQUIREMENTS = json.loads(Path(__file__).with_name("retro_requirements.json").read_text(encoding="utf-8"))
SYSTEMS = tuple(System(**{key: tuple(value) if isinstance(value, list) else value
                          for key, value in item.items()}) for item in REQUIREMENTS["systems"])
KNOWN_32_BIT = {"i386", "i486", "i586", "i686", "x86", "armv6l", "armv7l", "armv8l"}
KNOWN_64_BIT = {"x86_64", "aarch64", "ppc64", "ppc64le", "riscv64", "s390x", "loongarch64"}


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
        return result.stdout if len(result.stdout) <= 128 * 1024 else ""
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
    if system.architectures and architecture and architecture not in system.architectures:
        return "incompatible", "architecture"
    if system.minimum_bits == 64 and architecture in KNOWN_32_BIT:
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


def _extensions(output):
    # A complete glxinfo output distinguishes missing extensions from a missing
    # probe. The -B summary alone cannot establish extension availability.
    if not re.search(r"OpenGL (?:core profile )?extensions:", output):
        return None
    return set(re.findall(r"\bGL_[A-Za-z0-9_]+\b", output))


def _checks(system, architecture, flags, memory, opengl, vulkan, extensions):
    architecture_result = "unknown"
    if system.architectures and architecture:
        architecture_result = "pass" if architecture in system.architectures else "fail"
    elif system.minimum_bits:
        architecture_result = "pass" if architecture in KNOWN_64_BIT else "fail" if architecture in KNOWN_32_BIT else "unknown"
    checks = [{"kind": "architecture", "status": architecture_result,
               "required": ", ".join(system.architectures) or ("64-bit" if system.minimum_bits else ""),
               "observed": architecture}]
    if system.x86_flag:
        status = "unknown" if flags is None or architecture != "x86_64" else "pass" if system.x86_flag in flags else "fail"
        checks.append({"kind": "cpu", "status": status, "required": system.x86_flag,
                       "observed": system.x86_flag if status == "pass" else ""})
    if system.memory:
        status = "unknown" if memory is None else "pass" if memory + .5 >= system.memory else "fail"
        checks.append({"kind": "memory", "status": status, "required": f"{system.memory} GiB",
                       "observed": f"{memory} GiB" if memory is not None else ""})
    for kind, available, required in (("opengl", opengl, system.opengl), ("vulkan", vulkan, system.vulkan)):
        if required:
            status = "unknown" if not available else "pass" if available >= required else "fail"
            checks.append({"kind": kind, "status": status,
                           "required": ".".join(map(str, required)), "observed": ".".join(map(str, available))})
    if system.extensions:
        missing = set(system.extensions) - (extensions or set())
        status = "unknown" if extensions is None else "fail" if missing else "pass"
        checks.append({"kind": "extensions", "status": status, "required": ", ".join(system.extensions),
                       "observed": ", ".join(sorted(set(system.extensions) & (extensions or set())))})
    return checks


def _package_version(recipe, provider):
    if not recipe.get("installed"):
        return ""
    try:
        package = mapped_package(recipe, provider)
    except ValueError:
        return ""
    if not package:
        return ""
    commands = {"apt": ("dpkg-query", "-W", "-f=${Version}", package),
                "dnf": ("rpm", "-q", "--queryformat", "%{VERSION}-%{RELEASE}", package),
                "zypper": ("rpm", "-q", "--queryformat", "%{VERSION}-%{RELEASE}", package),
                "pacman": ("pacman", "-Q", package)}
    output = _graphics_output(commands[provider]).strip() if provider in commands else ""
    if provider == "pacman":
        output = output.partition(" ")[2]
    # Do not relay arbitrary package-script output, file paths or control bytes.
    return output if re.fullmatch(r"[0-9A-Za-z.+:~_()-]{1,120}", output) else ""


def _key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]


def retro_device_report(recommendations, core_ready):
    machine = platform.machine().lower()
    architecture = {"amd64": "x86_64", "arm64": "aarch64"}.get(machine, machine)
    flags = _cpu_flags() if architecture == "x86_64" else None
    memory = _memory_gib()
    gl_summary = _graphics_output(("glxinfo", "-B"))
    vk_summary = _graphics_output(("vulkaninfo", "--summary"))
    opengl = _opengl_version(gl_summary)
    vulkan = _vulkan_version(vk_summary)
    extensions = _extensions(_graphics_output(("glxinfo",))) if opengl else None
    release = read_os_release()
    provider = detect_native_provider(release)
    device_key = _key({"architecture": architecture, "flags": sorted(flags) if flags is not None else None,
                       "memory": memory, "gl": gl_summary, "vk": vk_summary,
                       "extensions": sorted(extensions) if extensions is not None else None})
    catalog = {item["id"]: item for item in recommendations if item.get("retroEmulator")}
    rows = []
    for system in SYSTEMS:
        status, reason = _compatibility(system, architecture, flags, memory, opengl, vulkan)
        recipe = catalog.get(system.catalog, {})
        checks = _checks(system, architecture, flags, memory, opengl, vulkan, extensions)
        # A failed OpenGL extension check restricts that renderer, while a
        # working Vulkan alternative keeps the result unmeasured.
        if status == "untested" and system.extensions and extensions is not None and opengl:
            if set(system.extensions) - extensions and not (system.vulkan and vulkan >= system.vulkan):
                status, reason = "limited", "graphics"
        installed = recipe.get("installed") and (system.catalog != "retroarch" or core_ready)
        available = catalog_package_route(recipe, release, provider).get("mode") == "direct"
        if system.catalog == "retroarch" and recipe.get("installed") and architecture == "x86_64":
            available = True  # The Parent panel can supply the core for an existing RetroArch.
        route = "installed" if installed else "available" if available else "unavailable"
        version = _package_version(recipe, provider)
        core = {}
        if system.catalog == "retroarch" and core_ready:
            from retro_games import PS1_CORE_SHA256, PS1_CORE_VERSION
            core = {"version": PS1_CORE_VERSION, "sha256": PS1_CORE_SHA256}
        rows.append({"system": system.name, "emulator": system.emulator, "catalog": system.catalog,
                     "status": status, "reason": reason, "route": route, "checks": checks,
                     "sources": list(system.sources), "reviewed": REQUIREMENTS["reviewed"],
                     "version": version, "core": core, "performanceMeasured": False,
                     "resultKey": _key({"device": device_key, "rules": REQUIREMENTS["revision"],
                                        "emulator": system.emulator, "version": version, "core": core,
                                        "provider": provider, "route": route})})
    return {"architecture": architecture, "memoryGiB": memory,
            "opengl": ".".join(map(str, opengl)), "vulkan": ".".join(map(str, vulkan)), "systems": rows,
            "deviceKey": device_key, "rulesRevision": REQUIREMENTS["revision"],
            "checkedAt": datetime.now(timezone.utc).isoformat(timespec="seconds")}
