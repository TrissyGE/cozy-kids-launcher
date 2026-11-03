"""Bounded local ROM discovery for the first managed emulator."""

import hashlib
import io
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
    ".m3u": ("retroarch", "", "Sony - PlayStation"),
    ".cue": ("retroarch", "", "Sony - PlayStation"),
}
PS1_EXTENSIONS = {".chd", ".m3u", ".cue"}
MAX_ROM_BYTES = 32 * 1024 * 1024
MAX_CHD_BYTES = 1024 * 1024 * 1024
MAX_PLAYLIST_BYTES = 16 * 1024
MAX_PLAYLIST_DISCS = 8
MAX_CUE_BYTES = 32 * 1024
RAW_CD_SECTOR_BYTES = 2352
CUE_FILE = re.compile(r'FILE\s+(?:"([^"]+)"|([^"\s]+))\s+BINARY', re.IGNORECASE)
CUE_TRACK = re.compile(r'TRACK\s+([0-9]{2})\s+(MODE[12]/2352|AUDIO)', re.IGNORECASE)
CUE_TIME = re.compile(r'(INDEX\s+0[01]|PREGAP|POSTGAP)\s+([0-9]{2}):([0-5][0-9]):([0-7][0-9])',
                      re.IGNORECASE)
CHD_HEADER = struct.Struct(">8sII")
PS1_CORE_FILENAME = "pcsx_rearmed_libretro.so"
PS1_CORE_VERSION = "r26 (7b0e8f8)"
PS1_CORE_BYTES = 2250248
PS1_CORE_SHA256 = "b81ce0d92b66fac94788a94836430530cebed2f2ee77e384db87eb0273e49c3c"
PS1_CORE_UPLOAD_BYTES = 4 * 1024 * 1024
PS1_CORE_URL = f"https://buildbot.libretro.com/nightly/linux/x86_64/latest/{PS1_CORE_FILENAME}.zip"
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
    _install_ps1_file(state_root, "ps1-bios", filename, payload)


def _install_ps1_file(state_root, folder, filename, payload):
    directory = prepare_profile_resume_directory(state_root, folder)
    descriptor, temporary = tempfile.mkstemp(prefix=".install-", dir=directory)
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


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


@lru_cache(maxsize=32)
def _download_cover(system, name, cache_hour):
    url = f"https://thumbnails.libretro.com/{quote(system, safe='')}/Named_Boxarts/{quote(name, safe='')}.png"
    try:
        with build_opener(_NoRedirect()).open(url, timeout=4) as response:
            payload = response.read(MAX_COVER_BYTES + 1)
    except OSError:
        return b""
    if len(payload) <= MAX_COVER_BYTES and payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return payload
    return b""


def retro_cover(game, download=False):
    stem, extension = os.path.splitext(game["path"])
    directory, name = os.path.split(stem)
    for path in (stem + ".png", os.path.join(directory, "Imgs", name + ".png")):
        try:
            with _open_local_regular(path) as cover:
                info = os.fstat(cover.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_COVER_BYTES:
                    continue
                payload = cover.read(MAX_COVER_BYTES + 1)
            if len(payload) <= MAX_COVER_BYTES and payload.startswith(b"\x89PNG\r\n\x1a\n"):
                return payload
        except OSError:
            continue
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
                    or rom.suffix.casefold() in PS1_EXTENSIONS
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


def _read_local_descriptor(path, maximum):
    with _open_local_regular(path) as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
            raise ValueError("Invalid disc descriptor")
        payload = handle.read(maximum + 1)
        if len(payload) > maximum:
            raise ValueError("Oversized disc descriptor")
        return payload


def _ps1_reference(descriptor, entry, extension):
    parts = entry.split("/")
    if (any(not part or part.startswith(".") for part in parts)
            or PurePosixPath(entry).suffix.casefold() != extension
            or any(char in entry for char in "\\:#")
            or not entry.isprintable()):
        raise ValueError("Invalid disc reference")
    path = os.path.join(os.path.dirname(descriptor), *parts)
    if any(char in path for char in "#\r\n") or os.path.realpath(path) != path:
        raise ValueError("Invalid disc path")
    return path


def _cue_metadata(path):
    """Return approved BIN paths, canonical CUE text and an approval fingerprint."""
    try:
        payload = _read_local_descriptor(path, MAX_CUE_BYTES)
        fingerprint = hashlib.sha256(payload)
        lines = []
        files = []
        seen = set()
        total_bytes = 0
        tracks = 0
        file_has_track = False
        last_index = -1
        times = {}
        for line in payload.decode("utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.split()[0].upper() in {"REM", "TITLE", "PERFORMER", "CATALOG", "ISRC", "SONGWRITER"}:
                continue
            if match := CUE_FILE.fullmatch(line):
                if files and (not file_has_track or "INDEX 01" not in times):
                    return None
                track_file = _ps1_reference(path, match[1] or match[2], ".bin")
                canonical = f'FILE "{track_file}" BINARY'
                # The pinned core reads CUE lines with a 256-byte fgets buffer.
                if '"' in track_file or len(os.fsencode(canonical)) > 254:
                    return None
                with _open_local_regular(track_file) as handle:
                    info = os.fstat(handle.fileno())
                identity = (info.st_dev, info.st_ino)
                total_bytes += info.st_size
                if (not stat.S_ISREG(info.st_mode) or not info.st_size or info.st_size % RAW_CD_SECTOR_BYTES
                        or total_bytes > MAX_CHD_BYTES or identity in seen):
                    return None
                seen.add(identity)
                files.append(track_file)
                fingerprint.update(f"{info.st_dev}:{info.st_ino}:{info.st_size}:"
                                   f"{info.st_mtime_ns}:{info.st_ctime_ns}\n".encode("ascii"))
                file_sectors = info.st_size // RAW_CD_SECTOR_BYTES
                file_has_track = False
                last_index = -1
                lines.append(canonical)
            elif match := CUE_TRACK.fullmatch(line):
                if not files or (file_has_track and "INDEX 01" not in times):
                    return None
                tracks += 1
                mode = match[2].upper()
                expected_modes = ("MODE1/2352", "MODE2/2352") if tracks == 1 else ("AUDIO",)
                if int(match[1]) != tracks or mode not in expected_modes:
                    return None
                file_has_track = True
                times = {}
                lines.append(f"  TRACK {tracks:02d} {mode}")
            elif match := CUE_TIME.fullmatch(line):
                if not file_has_track:
                    return None
                label = " ".join(match[1].upper().split())
                minute, second, frame = map(int, match.groups()[1:])
                sector = (minute * 60 + second) * 75 + frame
                if label in times or frame >= 75:
                    return None
                if label.startswith("INDEX") and not last_index < sector < file_sectors:
                    return None
                if label == "INDEX 00" and "INDEX 01" in times:
                    return None
                if label == "INDEX 01":
                    if sector < times.get("INDEX 00", 0):
                        return None
                    last_index = sector
                times[label] = sector
                lines.append(f"    {label} {minute:02d}:{second:02d}:{frame:02d}")
            else:
                return None
        if file_has_track and "INDEX 01" in times:
            return files, "\n".join(lines) + "\n", fingerprint.digest()
    except (OSError, UnicodeError, ValueError):
        return None
    return None


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


def _ps1_disc_set(path, verify=False):
    try:
        payload = _read_local_descriptor(path, MAX_PLAYLIST_BYTES)
        entries = [line.strip() for line in payload.decode("utf-8-sig").split("\n")]
        entries = [line for line in entries if line and not line.startswith("#")]
        if not 2 <= len(entries) <= MAX_PLAYLIST_DISCS:
            return None
        discs = []
        cue_discs = {}
        seen = set()
        fingerprint = hashlib.sha256(payload)
        for entry in entries:
            # Miyoo playlists use /_hidden/ relative to the playlist's directory.
            if entry.startswith("/_hidden/"):
                entry = entry[1:]
            extension = PurePosixPath(entry).suffix.casefold()
            if extension not in (".chd", ".cue"):
                return None
            disc = _ps1_reference(path, entry, extension)
            info = os.stat(disc, follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) in seen:
                return None
            seen.add((info.st_dev, info.st_ino))
            identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if extension == ".cue":
                cue = _cue_metadata(disc)
                if cue is None:
                    return None
                tracks, contents, member = cue
                cue_discs[disc] = tracks, contents
            else:
                member = _chd_fingerprint(disc) if verify else _chd_metadata(disc, identity)
            if member is None:
                return None
            discs.append(disc)
            fingerprint.update(member)
        return discs, cue_discs, fingerprint.digest()
    except (OSError, UnicodeError, ValueError):
        return None


def _game_id(path, fingerprint):
    return hashlib.sha256(os.fsencode(path) + b"\0" + fingerprint).hexdigest()[:24]


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
                        maximum = {".zip": MAX_ZIP_BYTES, ".chd": MAX_CHD_BYTES,
                                   ".m3u": MAX_PLAYLIST_BYTES, ".cue": MAX_CUE_BYTES}.get(extension, MAX_ROM_BYTES)
                        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= maximum:
                            continue
                        fingerprint = f"{info.st_size}:{info.st_mtime_ns}".encode("ascii")
                        member = None
                        discs = None
                        identity = (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                        if extension == ".chd":
                            fingerprint = _chd_metadata(item.path, identity)
                            if fingerprint is None:
                                continue
                        elif extension == ".m3u":
                            disc_set = _ps1_disc_set(item.path)
                            if disc_set is None:
                                continue
                            discs, _, fingerprint = disc_set
                        elif extension == ".cue":
                            cue = _cue_metadata(item.path)
                            if cue is None:
                                continue
                            _, _, fingerprint = cue
                        elif extension == ".zip":
                            member = _zip_metadata(item.path, identity)
                            if member is None:
                                continue
                            fingerprint += repr(member).encode("utf-8")
                            rom = PurePosixPath(member[0])
                            stem, extension = rom.stem, rom.suffix.casefold()
                        identifier = _game_id(item.path, fingerprint)
                        if identifier not in games and len(games) >= MAX_ROMS:
                            return games, sources["unavailableSources"], True
                        games[identifier] = {
                            "id": identifier,
                            "title": stem[:160],
                            "path": item.path,
                            "romExtension": extension,
                            "zipMember": member,
                        }
                        if discs:
                            games[identifier]["discPaths"] = discs
            except OSError:
                continue
    return games, sources["unavailableSources"], False


def emulator_binary(game):
    return ROM_SYSTEMS[game["romExtension"]][0]


def ps1_core_supported():
    return platform.machine().lower() in ("x86_64", "amd64")


def _reviewed_ps1_core(payload):
    return len(payload) == PS1_CORE_BYTES and hashlib.sha256(payload).hexdigest() == PS1_CORE_SHA256


def import_ps1_core(state_root, payload):
    if not ps1_core_supported() or not 0 < len(payload) <= PS1_CORE_UPLOAD_BYTES:
        raise ValueError("Unsupported PS1 core")
    if payload.startswith(b"PK\x03\x04"):
        try:
            with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                entries = archive.infolist()
                if (len(entries) != 1 or entries[0].filename != PS1_CORE_FILENAME
                        or entries[0].file_size != PS1_CORE_BYTES):
                    raise ValueError("Unexpected PS1 core archive")
                with archive.open(entries[0]) as member:
                    payload = member.read(PS1_CORE_BYTES + 1)
        except (zipfile.BadZipFile, RuntimeError, NotImplementedError, zlib.error) as error:
            raise ValueError("Invalid PS1 core archive") from error
    if not _reviewed_ps1_core(payload):
        raise ValueError("PS1 core does not match the reviewed build")
    _install_ps1_file(state_root, "ps1-cores", PS1_CORE_FILENAME, payload)


def download_ps1_core(state_root):
    if not ps1_core_supported():
        raise ValueError("Unsupported PS1 core platform")
    if ps1_core_path(state_root):
        return
    with build_opener(_NoRedirect()).open(PS1_CORE_URL, timeout=10) as response:
        payload = response.read(PS1_CORE_UPLOAD_BYTES + 1)
    import_ps1_core(state_root, payload)


def ps1_core_path(state_root):
    if not ps1_core_supported():
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
    return path if _reviewed_ps1_core(payload) else None


def _write_private_text(path, contents):
    descriptor, temporary = tempfile.mkstemp(prefix=".retroarch-", dir=os.path.dirname(path))
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(contents)
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)


def _ps1_command(executable, game, state_root, game_directory):
    core = ps1_core_path(state_root)
    if core is None:
        raise ValueError("Reviewed PS1 core is unavailable")
    path = game["path"]
    playlist = game["romExtension"] == ".m3u"
    cue_discs = {}
    if playlist:
        disc_set = _ps1_disc_set(path, verify=True)
        if disc_set is None:
            raise ValueError("Approved PS1 disc set has changed")
        discs, cue_discs, fingerprint = disc_set
    elif game["romExtension"] == ".cue":
        cue = _cue_metadata(path)
        if cue is None:
            raise ValueError("Approved PS1 tracks have changed")
        tracks, cue_text, fingerprint = cue
        discs = [path]
        cue_discs[path] = tracks, cue_text
    else:
        discs, fingerprint = [path], _chd_fingerprint(path)
    if fingerprint is None or _game_id(path, fingerprint) != game["id"]:
        raise ValueError("Approved PS1 disc has changed")
    # PCSX ReARMed can automatically open metadata alongside a CHD.
    sidecars = [(disc, (".sbi", ".lsd", ".sub", ".toc", ".ccd", ".mds", ".cue"))
                for disc in discs if disc not in cue_discs]
    sidecars.extend((file, (".sbi", ".lsd", ".sub"))
                    for disc, (tracks, _) in cue_discs.items() for file in (disc, *tracks))
    if any(os.path.lexists(os.path.splitext(file)[0] + extension)
           for file, extensions in sidecars for extension in extensions):
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
    disc_controls = ""
    content_paths = []
    for index, disc in enumerate(discs, 1):
        if disc in cue_discs:
            name = f"disc-{index:02d}.cue" if playlist else "disc.cue"
            _write_private_text(os.path.join(game_directory, name), cue_discs[disc][1])
            content_paths.append(name)
        else:
            content_paths.append(disc)
    if playlist:
        path = os.path.join(game_directory, "disc-set.m3u")
        _write_private_text(path, "\n".join(content_paths) + "\n")
        disc_controls = (
            'input_audio_mute = "nul"\n'
            'input_disk_eject_toggle = "f9"\n'
            'input_disk_next = "f10"\n'
        )
    elif cue_discs:
        path = os.path.join(game_directory, content_paths[0])
    _write_private_text(config, (
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
        # A stalled PulseAudio sink must not block input or saving on close.
        'audio_sync = "false"\n'
        'menu_driver = "rgui"\n'
        'input_menu_toggle = "nul"\n'
        'input_menu_toggle_gamepad_combo = "0"\n'
        'kiosk_mode_enable = "true"\n'
        'desktop_menu_enable = "false"\n'
    ) + disc_controls)
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
    if game["romExtension"] in PS1_EXTENSIONS:
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
