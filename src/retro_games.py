"""Bounded local ROM discovery for the first managed emulator."""

import hashlib
import os
import re
import stat
import struct
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
ROM_EXTENSIONS = frozenset({".gb", ".gbc", ".gba"})
MAX_ROM_BYTES = 32 * 1024 * 1024
MAX_ZIP_BYTES = 40 * 1024 * 1024
MAX_ZIP_DIRECTORY_BYTES = 64 * 1024
MAX_ZIP_ENTRIES = 32
ZIP_END = struct.Struct("<4s4H2IH")
MAX_ROMS = 512
MAX_SCAN_DIRECTORIES = 250
MAX_SCAN_ENTRIES = 2500
ROM_ID = re.compile(r"[a-f0-9]{24}")
COVER_SYSTEMS = {
    ".gb": "Nintendo - Game Boy",
    ".gbc": "Nintendo - Game Boy Color",
    ".gba": "Nintendo - Game Boy Advance",
}
MAX_COVER_BYTES = 1024 * 1024
_cover_slots = threading.BoundedSemaphore(2)


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
        system = COVER_SYSTEMS[game.get("romExtension", extension.casefold())]
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
        if os.path.realpath(path) != path:
            return None
        flags = (os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                 | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0))
        with os.fdopen(os.open(path, flags), "rb") as handle:
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
                    or rom.suffix.casefold() not in ROM_EXTENSIONS
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
                        if extension not in ROM_EXTENSIONS and extension != ".zip":
                            continue
                        info = item.stat(follow_symlinks=False)
                        maximum = MAX_ZIP_BYTES if extension == ".zip" else MAX_ROM_BYTES
                        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
                            continue
                        fingerprint = f"{info.st_size}:{info.st_mtime_ns}".encode("ascii")
                        member = None
                        if extension == ".zip":
                            identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
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


def emulator_command(executable, game, save_root, profile_id):
    """Keep battery saves and state slots in a private child/game directory."""
    if game.get("zipMember") is not None and inspect_rom_zip(game["path"], verify=True) != game["zipMember"]:
        raise ValueError("ROM archive is unavailable or damaged")
    profile = prepare_profile_resume_directory(save_root, profile_id)
    game_directory = prepare_profile_resume_directory(profile, game["id"])
    config_directory = prepare_profile_resume_directory(game_directory, "config")
    return [
        "kstart", "--fullscreen",
        "/usr/bin/env", f"XDG_CONFIG_HOME={config_directory}", executable,
        "-C", f"savegamePath={game_directory}",
        "-C", f"savestatePath={game_directory}",
        game["path"],
    ]
