"""Safe discovery and creation of local configuration backups."""

import json
import os
import re
import secrets
import stat
from datetime import datetime

from config_store import atomic_write_config


MAX_BACKUP_BYTES = 512 * 1024
MAX_DISCOVERED_BACKUPS = 50
_INSTALLER_ID = re.compile(r"^[0-9]{8}-[0-9]{6}$")
_RESTORE_ID = re.compile(r"^restore-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}$")


def _backup_metadata(backup_id):
    if _INSTALLER_ID.fullmatch(backup_id):
        timestamp = backup_id
        source = "installer"
    elif _RESTORE_ID.fullmatch(backup_id):
        timestamp = backup_id.split("-", 1)[1].rsplit("-", 1)[0]
        source = "pre-restore"
    else:
        raise ValueError("Invalid backup identifier")
    try:
        created = datetime.strptime(timestamp, "%Y%m%d-%H%M%S")
    except ValueError as exc:
        raise ValueError("Invalid backup timestamp") from exc
    return {
        "id": backup_id,
        "createdAt": created.isoformat(timespec="seconds"),
        "source": source,
    }


def _checked_root(root, create=False):
    root = os.path.abspath(root)
    if create:
        os.makedirs(root, mode=0o700, exist_ok=True)
    try:
        root_stat = os.lstat(root)
    except FileNotFoundError:
        raise
    if stat.S_ISLNK(root_stat.st_mode) or not stat.S_ISDIR(root_stat.st_mode):
        raise ValueError("Backup root must be a real directory")
    try:
        os.chmod(root, 0o700)
    except OSError:
        pass
    return root


def _checked_config_path(root, backup_id):
    metadata = _backup_metadata(backup_id)
    root = _checked_root(root)
    directory = os.path.join(root, backup_id)
    try:
        directory_stat = os.lstat(directory)
    except FileNotFoundError:
        raise FileNotFoundError("Backup does not exist") from None
    if stat.S_ISLNK(directory_stat.st_mode) or not stat.S_ISDIR(directory_stat.st_mode):
        raise ValueError("Backup directory is unsafe")
    config_path = os.path.join(directory, "config.json")
    try:
        config_stat = os.lstat(config_path)
    except FileNotFoundError:
        raise FileNotFoundError("Backup has no configuration") from None
    if stat.S_ISLNK(config_stat.st_mode) or not stat.S_ISREG(config_stat.st_mode):
        raise ValueError("Backup configuration is unsafe")
    if config_stat.st_size > MAX_BACKUP_BYTES:
        raise ValueError("Backup configuration is too large")
    return metadata, config_path


def discover_config_backups(root, limit=MAX_DISCOVERED_BACKUPS):
    """Return safe backup metadata without exposing filesystem paths."""
    try:
        root = _checked_root(root)
        names = os.listdir(root)
    except (FileNotFoundError, OSError, ValueError):
        return []
    candidates = []
    for name in names:
        try:
            metadata, _config_path = _checked_config_path(root, name)
        except (FileNotFoundError, OSError, ValueError):
            continue
        candidates.append(metadata)
    candidates.sort(key=lambda item: (item["createdAt"], item["id"]), reverse=True)
    return candidates[:max(0, int(limit))]


def read_config_backup(root, backup_id):
    """Read one strictly identified, regular backup configuration file."""
    _metadata, config_path = _checked_config_path(root, backup_id)
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Backup configuration is invalid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError("Backup configuration must be an object")
    return data


def create_pre_restore_backup(root, data, now=None, token=None):
    """Atomically snapshot current settings before replacing them."""
    root = _checked_root(root, create=True)
    timestamp = (now or datetime.now()).strftime("%Y%m%d-%H%M%S")
    for _attempt in range(10):
        suffix = token or secrets.token_hex(4)
        backup_id = f"restore-{timestamp}-{suffix}"
        _backup_metadata(backup_id)
        directory = os.path.join(root, backup_id)
        try:
            os.mkdir(directory, mode=0o700)
            break
        except FileExistsError:
            if token:
                raise
    else:
        raise OSError("Could not allocate a backup directory")
    atomic_write_config(os.path.join(directory, "config.json"), data)
    return _backup_metadata(backup_id)
