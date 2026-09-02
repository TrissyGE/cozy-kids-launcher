"""Private per-profile storage boundaries for native media-player resume data."""

import os
import re
import shutil
import stat


PROFILE_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,80}")


def _profile_id(value):
    if not isinstance(value, str) or not PROFILE_ID_PATTERN.fullmatch(value):
        raise ValueError("profileId contains invalid characters")
    return value


def _profile_path(root, profile_id):
    root = os.path.abspath(os.fspath(root))
    profile = os.path.abspath(os.path.join(root, _profile_id(profile_id)))
    if os.path.commonpath((root, profile)) != root:
        raise ValueError("profileId escapes the resume root")
    return root, profile


def _secure_directory(path):
    if os.name != "posix":
        try:
            os.chmod(path, 0o700)
        except OSError:
            pass
        return
    flags = (
        os.O_RDONLY
        | getattr(os, "O_DIRECTORY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
    )
    descriptor = os.open(path, flags)
    try:
        os.fchmod(descriptor, 0o700)
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISDIR(mode) or stat.S_IMODE(mode) != 0o700:
            raise OSError("media resume path is not a private directory")
    finally:
        os.close(descriptor)


def prepare_profile_resume_directory(root, profile_id):
    """Create and return one private directory for a player's native state."""
    root, profile = _profile_path(root, profile_id)
    if os.path.islink(root):
        raise OSError("media resume root must not be a symbolic link")
    if os.path.islink(profile):
        raise OSError("media resume directory must not be a symbolic link")
    os.makedirs(root, mode=0o700, exist_ok=True)
    if os.path.islink(root):
        raise OSError("media resume root must not be a symbolic link")
    _secure_directory(root)
    os.makedirs(profile, mode=0o700, exist_ok=True)
    if os.path.islink(profile) or not os.path.isdir(profile):
        raise OSError("media resume directory is not a private directory")
    _secure_directory(profile)
    return profile


def remove_profile_resume_directory(root, profile_id):
    """Remove only the native resume data belonging to one deleted profile."""
    root, profile = _profile_path(root, profile_id)
    if os.path.islink(root):
        raise OSError("media resume root must not be a symbolic link")
    if os.path.islink(profile):
        os.unlink(profile)
    elif os.path.isdir(profile):
        shutil.rmtree(profile)
    elif os.path.exists(profile):
        os.unlink(profile)
