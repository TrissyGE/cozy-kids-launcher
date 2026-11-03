"""Bounded local ROM discovery for the first managed emulator."""

import hashlib
import os
import re
import stat

from media_library import managed_media_sources
from media_resume import prepare_profile_resume_directory


RETRO_PREFIX = "special:retro:"
ROM_EXTENSIONS = frozenset({".gb", ".gbc", ".gba"})
MAX_ROMS = 100
MAX_SCAN_DIRECTORIES = 250
MAX_SCAN_ENTRIES = 2500
ROM_ID = re.compile(r"[a-f0-9]{24}")


def retro_id(command):
    if len(command) == 1 and command[0].startswith(RETRO_PREFIX):
        identifier = command[0][len(RETRO_PREFIX):]
        if ROM_ID.fullmatch(identifier):
            return identifier
    return None


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
                        if extension.casefold() not in ROM_EXTENSIONS:
                            continue
                        info = item.stat(follow_symlinks=False)
                        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= 32 * 1024 * 1024:
                            continue
                        fingerprint = f"{info.st_size}:{info.st_mtime_ns}".encode("ascii")
                        identifier = hashlib.sha256(os.fsencode(item.path) + b"\0" + fingerprint).hexdigest()[:24]
                        if identifier not in games and len(games) >= MAX_ROMS:
                            return games, sources["unavailableSources"], True
                        games[identifier] = {
                            "id": identifier,
                            "title": stem[:160],
                            "path": item.path,
                        }
            except OSError:
                continue
    return games, sources["unavailableSources"], False


def emulator_command(executable, game, save_root, profile_id):
    """Keep battery saves and state slots in a private child/game directory."""
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
