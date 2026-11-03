"""Bounded local media discovery and media-player command construction."""

import glob
import hashlib
import os
import shutil
import stat
from pathlib import PurePosixPath


SUPPORTED_MEDIA_PATTERNS = (
    "*.mp4",
    "*.mkv",
    "*.webm",
    "*.avi",
    "*.mov",
    "*.mp3",
    "*.ogg",
    "*.wav",
    "*.flac",
    "*.m4a",
)

MEDIA_PLAYER_CANDIDATES = ("vlc", "mpv", "celluloid", "totem")
INDIVIDUAL_MEDIA_PLAYER_CANDIDATES = ("mpv", "vlc", "celluloid", "totem")
MAX_MEDIA_ITEMS = 2000
MAX_MEDIA_COVER_BYTES = 10 * 1024 * 1024
MAX_MEDIA_SCAN_DIRECTORIES = 5000
MAX_MEDIA_SCAN_FILES = 20000
MAX_MEDIA_ROOTS = 8
SUPPORTED_VIDEO_EXTENSIONS = frozenset({".avi", ".mkv", ".mov", ".mp4", ".webm"})
SUPPORTED_AUDIO_EXTENSIONS = frozenset({".flac", ".m4a", ".mp3", ".ogg", ".wav"})
SUPPORTED_COVER_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


def validate_media_roots(value):
    """Validate parent-entered Linux paths without requiring storage to be online."""
    if not isinstance(value, list) or len(value) > MAX_MEDIA_ROOTS:
        raise ValueError("A maximum of eight media folders is supported")
    roots = []
    for path in value:
        if (
            not isinstance(path, str)
            or len(path) > 2048
            or any(
                ord(character) < 32 or ord(character) == 127 or "\ud800" <= character <= "\udfff"
                for character in path
            )
        ):
            raise ValueError("Invalid media folder")
        directory = PurePosixPath(path)
        if (
            not directory.is_absolute()
            or directory.anchor != "/"
            or len(directory.parts) < 2
            or any(part.startswith(".") for part in directory.parts[1:])
        ):
            raise ValueError("Media folders must be absolute, non-hidden paths")
        normalized = str(directory)
        if normalized not in roots:
            roots.append(normalized)
    return roots


def managed_media_sources(roots):
    """Return usable roots and a path-free snapshot of their availability."""
    available = []
    signatures = []
    for root in roots:
        try:
            info = os.stat(root)
            if (
                not stat.S_ISDIR(info.st_mode)
                or os.path.realpath(root) != root
                or not os.access(root, os.R_OK | os.X_OK)
            ):
                raise OSError("Media folder unavailable")
        except OSError:
            signatures.append(None)
        else:
            available.append(root)
            signatures.append((info.st_dev, info.st_ino, info.st_mtime_ns))
    revision = hashlib.sha256(repr(signatures).encode("ascii")).hexdigest()[:24]
    return available, {
        "sourceRevision": revision,
        "unavailableSources": len(roots) - len(available),
    }


def has_media(path, patterns=SUPPORTED_MEDIA_PATTERNS):
    """Return whether a directory recursively contains supported media."""
    if not os.path.isdir(path):
        return False
    for pattern in patterns:
        if glob.glob(os.path.join(path, "**", pattern), recursive=True):
            return True
    return False


def media_locations(locations, has_media_fn=None):
    """Return unique candidate directories that contain supported media."""
    contains_media = has_media if has_media_fn is None else has_media_fn
    result = []
    seen = set()
    for location in locations:
        normalized = os.path.realpath(location)
        if normalized not in seen and contains_media(location):
            result.append(location)
            seen.add(normalized)
    return result


def media_location(locations, has_media_fn=None):
    """Return the first populated media directory, if one exists."""
    populated = media_locations(locations, has_media_fn=has_media_fn)
    return populated[0] if populated else None


def _inside_root(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except (OSError, ValueError):
        return False


def _cover_path(directory, media_stem, root, filenames=None):
    """Return an adjacent sidecar or conventional folder cover, if present."""
    if filenames is None:
        try:
            filenames = os.listdir(directory)
        except OSError:
            return ""
    available = {
        filename.casefold(): filename
        for filename in filenames
        if not filename.startswith(".")
    }
    candidates = (
        *(f"{media_stem}{extension}" for extension in SUPPORTED_COVER_EXTENSIONS),
        *(f"cover{extension}" for extension in SUPPORTED_COVER_EXTENSIONS),
        *(f"folder{extension}" for extension in SUPPORTED_COVER_EXTENSIONS),
    )
    for candidate in candidates:
        filename = available.get(candidate.casefold())
        if not filename:
            continue
        path = os.path.realpath(os.path.join(directory, filename))
        if _inside_root(path, root) and os.path.isfile(path):
            return path
    return ""


def _media_id(path):
    """Create a stable identifier without exposing the local path."""
    return hashlib.sha256(os.fsencode(path)).hexdigest()[:24]


def scan_media_catalog(locations, limit=MAX_MEDIA_ITEMS):
    """Return deterministic local media entries and whether the result was capped.

    Symbolic links that resolve outside a configured media root are ignored. Hidden
    directories and files are skipped so private application data does not
    accidentally become part of the child-facing catalog.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Media catalog limit must be a positive integer")

    entries = []
    seen_files = set()
    seen_roots = set()
    scanned_directories = 0
    scanned_files = 0
    supported_extensions = SUPPORTED_VIDEO_EXTENSIONS | SUPPORTED_AUDIO_EXTENSIONS
    for location in locations:
        root = os.path.realpath(os.fspath(location))
        if root in seen_roots or not os.path.isdir(root):
            continue
        seen_roots.add(root)
        for directory, dirnames, filenames in os.walk(root, followlinks=False):
            scanned_directories += 1
            if scanned_directories > MAX_MEDIA_SCAN_DIRECTORIES:
                return entries, True
            dirnames[:] = sorted(
                name for name in dirnames
                if not name.startswith(".")
                and _inside_root(os.path.realpath(os.path.join(directory, name)), root)
            )
            for filename in sorted(filenames):
                scanned_files += 1
                if scanned_files > MAX_MEDIA_SCAN_FILES:
                    return entries, True
                if filename.startswith("."):
                    continue
                extension = os.path.splitext(filename)[1].casefold()
                if extension not in supported_extensions:
                    continue
                path = os.path.realpath(os.path.join(directory, filename))
                if (
                    path in seen_files
                    or not _inside_root(path, root)
                    or not os.path.isfile(path)
                ):
                    continue
                if len(entries) >= limit:
                    return entries, True
                seen_files.add(path)
                title = " ".join(
                    os.path.splitext(filename)[0].replace("_", " ").split()
                )
                entries.append({
                    "id": _media_id(path),
                    "title": title or filename,
                    "kind": "video" if extension in SUPPORTED_VIDEO_EXTENSIONS else "audio",
                    "path": path,
                    "coverPath": _cover_path(
                        directory,
                        os.path.splitext(filename)[0],
                        root,
                        filenames=filenames,
                    ),
                })

    entries.sort(key=lambda item: (item["title"].casefold(), item["id"]))
    return entries, False


def public_media_catalog(entries, cover_url_prefix="/api/media/cover?id="):
    """Project internal catalog entries without leaking filesystem paths."""
    result = []
    for entry in entries:
        item = {
            "id": entry["id"],
            "title": entry["title"],
            "kind": entry["kind"],
            "coverUrl": "",
        }
        if entry.get("coverPath"):
            item["coverUrl"] = f"{cover_url_prefix}{entry['id']}"
        result.append(item)
    return result


def catalog_item(entries, media_id):
    """Resolve one exact opaque identifier from an already bounded catalog."""
    if not isinstance(media_id, str) or len(media_id) != 24:
        return None
    return next((entry for entry in entries if entry["id"] == media_id), None)


def find_media_player(candidates=MEDIA_PLAYER_CANDIDATES, which=None):
    """Return the first supported media player available on PATH."""
    executable = shutil.which if which is None else which
    for candidate in candidates:
        if executable(candidate):
            return candidate
    return None


def media_player_command(player, locations, resume_directory=None):
    """Build a fullscreen command, optionally isolating MPV resume state."""
    if player == "vlc":
        return [
            player,
            "--fullscreen",
            "--play-and-exit",
            "--no-video-title-show",
            *locations,
        ]
    if player == "mpv":
        command = [player, "--fullscreen"]
        if resume_directory:
            command.extend([
                "--save-position-on-quit",
                f"--watch-later-dir={os.fspath(resume_directory)}",
                "--watch-later-options=start",
                "--resume-playback=yes",
                "--resume-playback-check-mtime=yes",
            ])
        return [*command, *locations]
    return [player, *locations]
