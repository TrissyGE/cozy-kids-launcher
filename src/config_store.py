"""Versioned configuration storage for Cozy Kids Launcher."""

import json
import os
import tempfile


CURRENT_CONFIG_VERSION = 1


def migrate_config(data):
    """Return a current config copy and whether a schema migration was applied."""
    if not isinstance(data, dict):
        raise ValueError("Config must be a JSON object")

    result = dict(data)
    version = result.get("configVersion", 0)
    if isinstance(version, bool) or not isinstance(version, int) or version < 0:
        raise ValueError("configVersion must be a non-negative integer")
    if version > CURRENT_CONFIG_VERSION:
        raise ValueError(
            f"Config version {version} is newer than supported version "
            f"{CURRENT_CONFIG_VERSION}"
        )

    migrated = False
    while version < CURRENT_CONFIG_VERSION:
        if version == 0:
            version = 1
            result["configVersion"] = version
            migrated = True
            continue
        raise ValueError(f"No migration path exists from config version {version}")

    return result, migrated


def read_config(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def atomic_write_config(path, data):
    """Write JSON beside its target and atomically replace the old file."""
    config_dir = os.path.dirname(path)
    os.makedirs(config_dir, exist_ok=True)
    descriptor, temp_path = tempfile.mkstemp(
        prefix="config-",
        suffix=".json",
        dir=config_dir,
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise
