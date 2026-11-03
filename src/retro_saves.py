"""Find, export and remove saves written by the managed RetroGameCorner runtimes."""

import os
import re
import shutil
import stat
import tempfile
import zipfile
from itertools import islice
from pathlib import Path

from media_resume import PROFILE_ID_PATTERN
from retro_games import ROM_ID, _open_local_regular


MAX_SAVE_BYTES = 128 * 1024 * 1024
MAX_SAVE_FILES = 256
MAX_SAVE_DIRECTORY_ENTRIES = 1024
SAVE_FOLDERS = ("", "PCSX-ReARMed", "sav", "mcs", "b")
SAVE_NAME = re.compile(r".+\.(?:sav|ss[0-9]|srm|mcd|state(?:[0-9]+|\.auto)?)", re.IGNORECASE)


def _private_directory(path):
    return path.is_dir() and os.path.realpath(path) == str(path)


def _profile_directory(root, profile_id):
    if not PROFILE_ID_PATTERN.fullmatch(profile_id):
        raise ValueError("Invalid profile")
    return Path(root).absolute() / profile_id


def _save_files(directory):
    if not _private_directory(directory):
        return []
    files = []
    for folder in SAVE_FOLDERS:
        parent = directory / folder
        if not _private_directory(parent):
            continue
        with os.scandir(parent) as entries:
            for index, entry in enumerate(entries):
                if index >= MAX_SAVE_DIRECTORY_ENTRIES:
                    raise ValueError("Save directory limit exceeded")
                if (not entry.is_file(follow_symlinks=False)
                        or any(char in entry.name for char in ":\\\r\n")
                        or any(0xD800 <= ord(char) <= 0xDFFF for char in entry.name)):
                    continue
                # Mednafen dedicates these directories to saves and states.
                if folder in ("", "PCSX-ReARMed") and not SAVE_NAME.fullmatch(entry.name):
                    continue
                files.append(Path(folder) / entry.name)
                if len(files) > MAX_SAVE_FILES:
                    raise ValueError("Too many save files")
    return sorted(files)


def retro_save_ids(root, profile_id):
    profile = _profile_directory(root, profile_id)
    if not _private_directory(profile):
        return []
    with os.scandir(profile) as entries:
        return sorted(entry.name for entry in islice(entries, 1024)
                      if ROM_ID.fullmatch(entry.name) and _save_files(Path(entry.path)))


def _game_saves(root, profile_id, game_id):
    if not ROM_ID.fullmatch(game_id):
        raise ValueError("Invalid game")
    directory = _profile_directory(root, profile_id) / game_id
    files = _save_files(directory)
    if not files:
        raise FileNotFoundError("No saves")
    return directory, files


def backup_retro_saves(root, profile_id, game_id, output):
    directory, files = _game_saves(root, profile_id, game_id)
    remaining = MAX_SAVE_BYTES
    with zipfile.ZipFile(output, "w") as archive:
        for relative in files:
            with _open_local_regular(str(directory / relative)) as source:
                info = os.fstat(source.fileno())
                if not stat.S_ISREG(info.st_mode) or info.st_size > remaining:
                    raise ValueError("Save backup limit exceeded")
                with archive.open(relative.as_posix(), "w") as member:
                    while chunk := source.read(64 * 1024):
                        remaining -= len(chunk)
                        if remaining < 0:
                            raise ValueError("Save backup limit exceeded")
                        member.write(chunk)


def remove_retro_saves(root, profile_id, game_id):
    directory, files = _game_saves(root, profile_id, game_id)
    staging = Path(tempfile.mkdtemp(prefix=".removed-saves-", dir=directory))
    moved = []
    try:
        for index, relative in enumerate(files):
            staged = staging / str(index)
            os.replace(directory / relative, staged)
            moved.append((staged, relative))
    except OSError:
        for staged, relative in reversed(moved):
            os.replace(staged, directory / relative)
        staging.rmdir()
        raise
    shutil.rmtree(staging)
