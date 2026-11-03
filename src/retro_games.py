"""Bounded local ROM discovery for the first managed emulator."""

import hashlib
import os
import platform
import re
import stat
import struct
import tempfile
import threading
import time
import zipfile
import zlib
from functools import lru_cache
from pathlib import PurePosixPath
from urllib.parse import quote
from urllib.request import HTTPRedirectHandler, build_opener

from media_library import managed_media_sources
from media_resume import prepare_profile_resume_directory


RETRO_PREFIX = "special:retro:"
HUB_COMMAND = "special:retro-library"
HUB_ID = "retro-corner"
ROM_SYSTEMS = {
    ".gb": ("mgba-qt", "", "Nintendo - Game Boy"),
    ".gbc": ("mgba-qt", "", "Nintendo - Game Boy Color"),
    ".gba": ("mgba-qt", "", "Nintendo - Game Boy Advance"),
    ".nes": ("mednafen", "nes", "Nintendo - Nintendo Entertainment System"),
    ".sfc": ("mednafen", "snes", "Nintendo - Super Nintendo Entertainment System"),
    ".smc": ("mednafen", "snes", "Nintendo - Super Nintendo Entertainment System"),
    ".sms": ("mednafen", "sms", "Sega - Master System - Mark III"),
    ".gg": ("mednafen", "gg", "Sega - Game Gear"),
    ".chd": ("retroarch", "", "Sony - PlayStation"),
}
MAX_ROM_BYTES = 32 * 1024 * 1024
MAX_CHD_BYTES = 1024 * 1024 * 1024
CHD_HEADER = struct.Struct(">8sII")
PS1_CORE_FILENAME = "pcsx_rearmed_libretro.so"
PS1_CORE_BYTES = 2250248
PS1_CORE_SHA256 = "b81ce0d92b66fac94788a94836430530cebed2f2ee77e384db87eb0273e49c3c"
MAX_ZIP_BYTES = 40 * 1024 * 1024
MAX_ZIP_DIRECTORY_BYTES = 64 * 1024
MAX_ZIP_ENTRIES = 32
ZIP_END = struct.Struct("<4s4H2IH")
MAX_ROMS = 512
MAX_SCAN_DIRECTORIES = 250
MAX_SCAN_ENTRIES = 2500
ROM_ID = re.compile(r"[a-f0-9]{24}")
MAX_COVER_BYTES = 1024 * 1024
PS1_BIOS_BYTES = 512 * 1024
# The three regional PS1 images and the PSP image supported by PCSX ReARMed.
PS1_BIOS = {
    "jp": ("scph5500.bin", "9c0421858e217805f4abe18698afea8d5aa36ff0727eb8484944e00eb5e7eadb"),
    "na": ("scph5501.bin", "11052b6499e466bbf0a709b1f9cb6834a9418e66680387912451e971cf8a1fef"),
    "eu": ("scph5502.bin", "1faaa18fa820a0225e488d9f086296b8e6c46df739666093987ff7d8fd352c09"),
    "psp": ("psxonpsp660.bin", "cbe758e1c8ece593c8e14ce1e8b3436428a01c608032a02613b3a4b442b4d712"),
}
_cover_slots = threading.BoundedSemaphore(2)


def ps1_bios_status(state_root):
    directory = os.path.join(state_root, "ps1-bios")
    statuses = dict.fromkeys(PS1_BIOS, "missing")
    for region, (filename, expected) in PS1_BIOS.items():
        path = os.path.join(directory, filename)
        if not os.path.lexists(path):
            continue
        statuses[region] = "invalid"
        try:
            with _open_local_regular(path) as handle:
                info = os.fstat(handle.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size != PS1_BIOS_BYTES:
                    continue
                payload = handle.read(PS1_BIOS_BYTES + 1)
        except OSError:
            continue
        if len(payload) == PS1_BIOS_BYTES and hashlib.sha256(payload).hexdigest() == expected:
            statuses[region] = "ready"
    return statuses


def import_ps1_bios(state_root, payload):
    """Identify a supplied BIOS by content and store it under the known filename."""
    if len(payload) != PS1_BIOS_BYTES:
        raise ValueError("Invalid PS1 BIOS size")
    digest = hashlib.sha256(payload).hexdigest()
    filename = next((name for name, expected in PS1_BIOS.values() if digest == expected), None)
    if filename is None:
        raise ValueError("Unrecognized PS1 BIOS")
    directory = prepare_profile_resume_directory(state_root, "ps1-bios")
    descriptor, temporary = tempfile.mkstemp(prefix="bios-", dir=directory)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, os.path.join(directory, filename))
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def retro_hub(cfg, require_visible=True):
    return next((tile for tile in cfg["tiles"] if tile["id"] == HUB_ID
                 and tile["cmd"] == [HUB_COMMAND] and (not require_visible or tile["visible"])), None)


def approved_retro_ids(cfg):
    return {identifier: tile for tile in cfg["tiles"] if tile["visible"]
            if (identifier := retro_id(tile["cmd"]))}


class _NoCoverRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@lru_cache(maxsize=32)
def _download_cover(system, name, cache_hour):
    url = f"https://thumbnails.libretro.com/{quote(system, safe='')}/Named_Boxarts/{quote(name, safe='')}.png"
    try:
        with build_opener(_NoCoverRedirect()).open(url, timeout=4) as response:
            payload = response.read(MAX_COVER_BYTES + 1)
    except OSError:
        return b""
    if len(payload) <= MAX_COVER_BYTES and payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return payload
    return b""


def retro_cover(game, download=False):
    stem, extension = os.path.splitext(game["path"])
    sidecar = stem + ".png"
    try:
        if os.path.realpath(sidecar) == sidecar and os.path.isfile(sidecar):
            with open(sidecar, "rb") as cover:
                payload = cover.read(MAX_COVER_BYTES + 1)
            if len(payload) <= MAX_COVER_BYTES and payload.startswith(b"\x89PNG\r\n\x1a\n"):
                return payload
    except OSError:
        pass
    if not download or not _cover_slots.acquire(timeout=15):
        return b""
    try:
        title = re.sub(r'[&*/:`<>?\\|]', "_", game["title"])
        system = ROM_SYSTEMS[game.get("romExtension", extension.casefold())][2]
        return _download_cover(system, title, int(time.time() // 3600))
    finally:
        _cover_slots.release()


def retro_id(command):
    if len(command) == 1 and command[0].startswith(RETRO_PREFIX):
        identifier = command[0][len(RETRO_PREFIX):]
        if ROM_ID.fullmatch(identifier):
            return identifier
    return None


def _zip_directory_is_bounded(handle, size):
    """Check the ZIP end record before zipfile allocates its central directory."""
    tail_size = min(size, ZIP_END.size + 65535)
    handle.seek(size - tail_size)
    tail = handle.read(tail_size)
    offset = tail.rfind(b"PK\x05\x06")
    if offset < 0 or offset + ZIP_END.size > len(tail):
        return False
    if offset >= 20 and tail[offset - 20:offset - 16] == b"PK\x06\x07":
        return False
    _, disk, directory_disk, disk_entries, entries, length, start, comment = ZIP_END.unpack_from(tail, offset)
    return (
        disk == directory_disk == 0
        and disk_entries == entries
        and 1 <= entries <= MAX_ZIP_ENTRIES
        and length <= MAX_ZIP_DIRECTORY_BYTES
        and start + length == size - tail_size + offset
        and offset + ZIP_END.size + comment == len(tail)
    )


def inspect_rom_zip(path, verify=False):
    """Read one supported member's metadata and optionally verify its payload."""
    try:
        with _open_local_regular(path) as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_ZIP_BYTES
                    or not _zip_directory_is_bounded(handle, info.st_size)):
                return None
            with zipfile.ZipFile(handle) as archive:
                entries = archive.infolist()
                if len(entries) > MAX_ZIP_ENTRIES:
                    return None
                for entry in entries:
                    name = entry.orig_filename
                    parts = name.rstrip("/").split("/")
                    if any(part in ("", ".", "..") for part in parts) or any(
                        character in name for character in ("\x00", "\\", ":")
                    ):
                        return None
                    if stat.S_ISLNK(entry.external_attr >> 16) or (entry.is_dir() and entry.file_size):
                        return None
                files = [entry for entry in entries if not entry.is_dir()]
                if len(files) != 1:
                    return None
                member = files[0]
                mode = stat.S_IFMT(member.external_attr >> 16)
                rom = PurePosixPath(member.filename)
                if (
                    any(part.startswith(".") for part in rom.parts)
                    or rom.suffix.casefold() not in ROM_SYSTEMS
                    or rom.suffix.casefold() == ".chd"
                    or mode not in (0, stat.S_IFREG)
                    or member.flag_bits & 0x41
                    or member.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
                    or not 0 < member.compress_size <= info.st_size
                    or not 0 < member.file_size <= MAX_ROM_BYTES
                ):
                    return None
                if verify:
                    with archive.open(member) as stream:
                        remaining = member.file_size
                        while remaining:
                            chunk = stream.read(min(remaining, 64 * 1024))
                            if not chunk:
                                return None
                            remaining -= len(chunk)
                return member.filename, member.CRC, member.file_size
    except (OSError, ValueError, RuntimeError, EOFError, zipfile.BadZipFile, zlib.error):
        return None


@lru_cache(maxsize=MAX_SCAN_ENTRIES)
def _zip_metadata(path, identity):
    return inspect_rom_zip(path)


def _open_local_regular(path):
    if os.path.realpath(path) != path:
        raise OSError("File path must not contain symbolic links")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    return os.fdopen(os.open(path, flags | getattr(os, "O_BINARY", 0)), "rb")


def _chd_fingerprint(path):
    try:
        with _open_local_regular(path) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or not 124 < info.st_size <= MAX_CHD_BYTES:
                return None
            header = handle.read(124)
            if len(header) != 124 or CHD_HEADER.unpack_from(header) != (b"MComprHD", 124, 5):
                return None
            logical, map_offset, metadata, hunk, sector = struct.unpack_from(">QQQII", header, 32)
            if (sector != 2448 or not 0 < logical <= MAX_CHD_BYTES or logical % sector
                    or not 0 < hunk <= 1024 * 1024 or hunk % sector
                    or not 124 <= map_offset < info.st_size or not 124 <= metadata < info.st_size
                    or any(header[104:])):
                return None
    except OSError:
        return None
    return f"{info.st_dev}:{info.st_ino}:{info.st_size}:{info.st_mtime_ns}:{info.st_ctime_ns}".encode() + header


@lru_cache(maxsize=MAX_SCAN_ENTRIES)
def _chd_metadata(path, identity):
    return _chd_fingerprint(path)


def scan_retro_games(roots):
    available, sources = managed_media_sources(roots)
    games = {}
    directories = 0
    entries = 0
    for root in available:
        pending = [root]
        while pending:
            directory = pending.pop()
            directories += 1
            if directories > MAX_SCAN_DIRECTORIES:
                return games, sources["unavailableSources"], True
            if os.path.realpath(directory) != directory:
                continue
            try:
                with os.scandir(directory) as files:
                    for item in files:
                        entries += 1
                        if entries > MAX_SCAN_ENTRIES:
                            return games, sources["unavailableSources"], True
                        if item.name.startswith(".") or item.is_symlink():
                            continue
                        if any("\ud800" <= character <= "\udfff" for character in item.name):
                            continue
                        if item.is_dir(follow_symlinks=False):
                            pending.append(item.path)
                            continue
                        stem, extension = os.path.splitext(item.name)
                        extension = extension.casefold()
                        if extension not in ROM_SYSTEMS and extension != ".zip":
                            continue
                        info = item.stat(follow_symlinks=False)
                        maximum = {".zip": MAX_ZIP_BYTES, ".chd": MAX_CHD_BYTES}.get(extension, MAX_ROM_BYTES)
                        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
                            continue
                        fingerprint = f"{info.st_size}:{info.st_mtime_ns}".encode("ascii")
                        member = None
                        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                        if extension == ".chd":
                            fingerprint = _chd_metadata(item.path, identity)
                            if fingerprint is None:
                                continue
                        elif extension == ".zip":
                            member = _zip_metadata(item.path, identity)
                            if member is None:
                                continue
                            fingerprint += repr(member).encode("utf-8")
                            rom = PurePosixPath(member[0])
                            stem, extension = rom.stem, rom.suffix.casefold()
                        identifier = hashlib.sha256(os.fsencode(item.path) + b"\0" + fingerprint).hexdigest()[:24]
                        if identifier not in games and len(games) >= MAX_ROMS:
                            return games, sources["unavailableSources"], True
                        games[identifier] = {
                            "id": identifier,
                            "title": stem[:160],
                            "path": item.path,
                            "romExtension": extension,
                            "zipMember": member,
                        }
            except OSError:
                continue
    return games, sources["unavailableSources"], False


def emulator_binary(game):
    return ROM_SYSTEMS[game["romExtension"]][0]


def ps1_core_path(state_root):
    if platform.machine().lower() not in ("x86_64", "amd64"):
        return None
    path = os.path.join(state_root, "ps1-cores", PS1_CORE_FILENAME)
    try:
        with _open_local_regular(path) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size != PS1_CORE_BYTES:
                return None
            payload = handle.read(PS1_CORE_BYTES + 1)
    except OSError:
        return None
    return path if hashlib.sha256(payload).hexdigest() == PS1_CORE_SHA256 else None


def _ps1_command(executable, game, state_root, game_directory):
    core = ps1_core_path(state_root)
    if core is None:
        raise ValueError("Reviewed PS1 core is unavailable")
    path = game["path"]
    fingerprint = _chd_fingerprint(path)
    if fingerprint is None or hashlib.sha256(os.fsencode(path) + b"\0" + fingerprint).hexdigest()[:24] != game["id"]:
        raise ValueError("Approved PS1 disc has changed")
    if any(os.path.lexists(os.path.splitext(path)[0] + extension) for extension in (".sbi", ".lsd")):
        raise ValueError("PS1 disc sidecars require approval support")
    statuses = ps1_bios_status(state_root)
    system_directory = os.path.join(state_root, "ps1-bios")
    expected = {filename for region, (filename, _) in PS1_BIOS.items() if statuses[region] == "ready"}
    if not expected or set(os.listdir(system_directory)) != expected:
        raise ValueError("Verified PS1 firmware is unavailable")
    if any(character in system_directory + game_directory for character in '\\"\r\n'):
        raise ValueError("Unsupported character in RetroArch configuration path")
    config_home = prepare_profile_resume_directory(game_directory, "config")
    config = os.path.join(game_directory, "retroarch.cfg")
    descriptor, temporary = tempfile.mkstemp(prefix="retroarch-", dir=game_directory)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(
                f'system_directory = "{system_directory}"\n'
                f'savefile_directory = "{game_directory}"\n'
                f'savestate_directory = "{game_directory}"\n'
                f'screenshot_directory = "{game_directory}"\n'
                f'core_options_path = "{game_directory}/core-options.cfg"\n'
                'config_save_on_exit = "false"\n'
                'auto_overrides_enable = "false"\n'
                'auto_remaps_enable = "false"\n'
                'video_driver = "gl"\n'
                'video_context_driver = "x"\n'
                'menu_driver = "rgui"\n'
                'input_menu_toggle = "nul"\n'
                'input_menu_toggle_gamepad_combo = "0"\n'
                'kiosk_mode_enable = "true"\n'
                'desktop_menu_enable = "false"\n'
            )
        os.replace(temporary, config)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)
    return ["kstart", "--fullscreen", "/usr/bin/env", f"XDG_CONFIG_HOME={config_home}",
            executable, "--fullscreen", "--config", config, "--no-patch", "-L", core, "--", path]


def emulator_command(executable, game, save_root, profile_id):
    """Keep battery saves and state slots in a private child/game directory."""
    if game.get("zipMember") is not None and inspect_rom_zip(game["path"], verify=True) != game["zipMember"]:
        raise ValueError("ROM archive is unavailable or damaged")
    _, module, _ = ROM_SYSTEMS[game["romExtension"]]
    if module and os.path.lexists(game["path"] + ".ips"):
        raise ValueError("Mednafen would apply an unapproved IPS patch")
    profile = prepare_profile_resume_directory(save_root, profile_id)
    game_directory = prepare_profile_resume_directory(profile, game["id"])
    if game["romExtension"] == ".chd":
        return _ps1_command(executable, game, os.path.dirname(save_root), game_directory)
    if module:
        # Keep fullscreen observable by the supervisor and visible while the overlay has focus.
        return [
            "kstart", "--fullscreen", "/usr/bin/env", "SDL_VIDEODRIVER=x11",
            "SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS=0",
            f"MEDNAFEN_HOME={game_directory}", executable,
            "-force_module", module, "-video.driver", "softfb", "-video.fs", "1",
            f"-{module}.stretch", "aspect",
            game["path"],
        ]
    config_directory = prepare_profile_resume_directory(game_directory, "config")
    # Request mGBA's own fullscreen layout and keep compositor confirmation in the supervisor.
    return [
        "kstart", "--fullscreen",
        "/usr/bin/env", f"XDG_CONFIG_HOME={config_directory}", executable,
        "--fullscreen",
        "-C", f"savegamePath={game_directory}",
        "-C", f"savestatePath={game_directory}",
        game["path"],
    ]
