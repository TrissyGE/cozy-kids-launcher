"""Update discovery and launcher-trigger creation."""

import json
import os
import re
import shlex
from urllib.request import Request, urlopen


class MissingUpdaterError(FileNotFoundError):
    """Raised when an installed launcher has no updater script."""


def read_version(path):
    """Read the installed version, preserving the legacy fallback value."""
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return handle.read().strip()
    except Exception:
        return "0.0.0"


def parse_semver(value):
    """Return a comparable three-part version tuple, or None."""
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]+\.[0-9]+\.[0-9]+",
        value,
    ):
        return None
    return tuple(int(part) for part in value.split("."))


def version_is_newer(candidate, installed):
    candidate_parts = parse_semver(candidate)
    installed_parts = parse_semver(installed)
    return bool(
        candidate_parts
        and installed_parts
        and candidate_parts > installed_parts
    )


def fetch_remote_json(url, timeout=5):
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "cozy-kids-launcher",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def fetch_remote_text(url, timeout=5):
    request = Request(url, headers={"User-Agent": "cozy-kids-launcher"})
    with urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8").strip()


def resolve_update_status(
    installed,
    release_api_url,
    legacy_version_url,
    update_channel_file,
    timeout=5,
    fetch_json=fetch_remote_json,
    fetch_text=fetch_remote_text,
):
    """Prefer a verified stable release, retaining the legacy main fallback."""
    release_error = None
    try:
        release = fetch_json(release_api_url, timeout=timeout)
    except Exception as exc:
        release_error = exc
    else:
        try:
            tag = release.get("tag_name", "")
            latest = tag[1:] if tag.startswith("v") else tag
            archive_name = f"cozy-kids-launcher-{latest}.tar.gz"
            asset_names = {
                asset.get("name")
                for asset in release.get("assets", [])
                if isinstance(asset, dict)
            }
            if release.get("draft") or release.get("prerelease"):
                raise ValueError("Latest release is not stable")
            if not parse_semver(latest):
                raise ValueError(
                    "Release tag is not a supported semantic version"
                )
            if (
                archive_name not in asset_names
                or "SHA256SUMS" not in asset_names
            ):
                raise ValueError("Release is missing verified update assets")
        except (AttributeError, TypeError, ValueError) as exc:
            raise RuntimeError(
                "Update check failed: invalid release metadata"
            ) from exc
        return {
            "installedVersion": installed,
            "latestVersion": latest,
            "source": "release",
            "tag": tag,
            "updateAvailable": version_is_newer(latest, installed),
        }

    try:
        if os.path.isfile(update_channel_file):
            with open(update_channel_file, "r", encoding="utf-8") as handle:
                if handle.read().strip() == "release":
                    raise RuntimeError(
                        "Verified release channel is temporarily unavailable"
                    ) from release_error
        latest = fetch_text(legacy_version_url, timeout=timeout)
        if not parse_semver(latest):
            raise ValueError("Legacy VERSION is invalid")
        return {
            "installedVersion": installed,
            "latestVersion": latest,
            "source": "legacy-main",
            "updateAvailable": version_is_newer(latest, installed),
        }
    except Exception as legacy_error:
        raise RuntimeError("Update check failed") from legacy_error


def write_update_trigger(app_root, update_script):
    """Create the launcher-owned trigger without starting the updater here."""
    app_root = os.fspath(app_root)
    update_script = os.fspath(update_script)
    if not os.path.isfile(update_script):
        raise MissingUpdaterError("Installed updater is missing")
    trigger_path = os.path.join(app_root, "update-trigger.sh")
    trigger_script = (
        "#!/usr/bin/env bash\n"
        "set -euo pipefail\n"
        f"exec bash {shlex.quote(update_script)}\n"
    )
    with open(trigger_path, "w", encoding="utf-8") as handle:
        handle.write(trigger_script)
    os.chmod(trigger_path, 0o755)
    return trigger_path
