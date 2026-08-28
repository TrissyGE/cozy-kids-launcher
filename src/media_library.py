"""Local media discovery and media-player command construction."""

import glob
import os
import shutil


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


def find_media_player(candidates=MEDIA_PLAYER_CANDIDATES, which=None):
    """Return the first supported media player available on PATH."""
    executable = shutil.which if which is None else which
    for candidate in candidates:
        if executable(candidate):
            return candidate
    return None


def media_player_command(player, locations):
    """Build the existing fullscreen command for a supported media player."""
    if player == "vlc":
        return [
            player,
            "--fullscreen",
            "--play-and-exit",
            "--no-video-title-show",
            *locations,
        ]
    if player == "mpv":
        return [player, "--fullscreen", *locations]
    return [player, *locations]
