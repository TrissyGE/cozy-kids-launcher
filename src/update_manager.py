"""Update discovery and launcher-trigger creation."""

import json
import os
import re
import shlex
import sys
import tempfile
from pathlib import Path
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


def version_order(value):
    """Order numeric releases, with release candidates before their final version."""
    if not isinstance(value, str):
        return None
    match = re.fullmatch(r"([0-9]{1,9})\.([0-9]{1,9})\.([0-9]{1,9})(?:-rc\.([1-9][0-9]{0,8}))?", value)
    if match is None:
        return None
    major, minor, patch, candidate = match.groups()
    return int(major), int(minor), int(patch), candidate is None, int(candidate or 0)


def version_is_newer(candidate, installed):
    candidate_parts = version_order(candidate)
    installed_parts = version_order(installed)
    return bool(candidate_parts and installed_parts and candidate_parts > installed_parts)


def read_update_track(path):
    try:
        if path is not None and Path(path).read_text(encoding="utf-8").strip() == "preview":
            return "preview"
    except (OSError, ValueError):
        pass
    return "stable"


def write_update_track(path, track):
    if track not in ("stable", "preview"):
        raise ValueError("Expected stable or preview")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, mode="w", encoding="utf-8", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(track + "\n")
            stream.close()
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def select_release(metadata, track):
    """Choose a stable release or the highest eligible immutable preview-track release."""
    if track == "preview":
        if not isinstance(metadata, list):
            raise ValueError("Expected a release list")
        eligible = []
        for release in metadata:
            if not isinstance(release, dict) or release.get("draft") or release.get("immutable") is not True:
                continue
            tag = release.get("tag_name")
            if not isinstance(tag, str) or not tag.startswith("v"):
                continue
            order = version_order(tag[1:])
            if order is None or bool(release.get("prerelease")) == order[3]:
                continue
            eligible.append((order, release))
        if not eligible:
            raise ValueError("No immutable release is available on the preview track")
        _, release = max(eligible, key=lambda entry: entry[0])
    else:
        release = metadata
        if not isinstance(release, dict) or release.get("draft") or release.get("prerelease"):
            raise ValueError("Latest release is not stable")

    tag = release.get("tag_name", "")
    if not isinstance(tag, str):
        raise ValueError("Invalid release tag")
    version = tag.removeprefix("v")
    if track == "stable" and not parse_semver(version):
        raise ValueError("Release tag is not a supported semantic version")
    name = f"cozy-kids-launcher-{version}.tar.gz"
    assets = {
        asset.get("name"): asset.get("browser_download_url")
        for asset in release.get("assets", []) if isinstance(asset, dict)
    }
    if name not in assets or "SHA256SUMS" not in assets:
        raise ValueError("Release is missing verified update assets")
    return version, tag, name, assets[name], assets["SHA256SUMS"]


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
    preview_api_url=None,
    track_file=None,
):
    """Prefer a verified stable release, retaining the legacy main fallback."""
    track = read_update_track(track_file)
    release_error = None
    try:
        endpoint = preview_api_url if track == "preview" else release_api_url
        release = fetch_json(endpoint, timeout=timeout)
    except Exception as exc:
        release_error = exc
    else:
        try:
            latest, tag, _, _, _ = select_release(release, track)
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

    if track == "preview":
        raise RuntimeError("Update check failed: preview releases unavailable") from release_error
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


def main(argv):
    command, *args = argv
    if command == "compare":
        left, right = map(version_order, args)
        if left is None or right is None:
            raise ValueError("Invalid version")
        print((left > right) - (left < right))
    elif command == "track":
        print(read_update_track(args[0]))
    elif command == "set-track":
        write_update_track(*args)
    elif command == "select":
        path, track = args
        with open(path, encoding="utf-8") as stream:
            version, _, name, archive, checksums = select_release(json.load(stream), track)
        if any(not isinstance(url, str) or not re.fullmatch(r"https?://[^\s]+", url)
               for url in (archive, checksums)):
            raise ValueError("Release assets have invalid download URLs")
        print(version, name, archive, checksums, sep="\n")
    else:
        raise ValueError("Unknown update command")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (AttributeError, OSError, TypeError, ValueError) as error:
        sys.exit(str(error))
