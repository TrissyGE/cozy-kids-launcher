"""Reviewed Flatpak app identities and shell-free launch recipes."""

import json
from pathlib import Path
import re

APP_ID = re.compile(r"[A-Za-z][A-Za-z0-9_-]*(?:\.[A-Za-z0-9_-]+){2,}")
REF = re.compile(r"(app|runtime)/[A-Za-z0-9_.-]{1,200}/[A-Za-z0-9_-]{1,40}/[A-Za-z0-9_.-]{1,80}")
COMMIT = re.compile(r"[a-f0-9]{64}")
FLATHUB_URL = "https://dl.flathub.org/repo/"


def recipes():
    return json.loads(Path(__file__).with_name("flatpak_catalog.json").read_text(encoding="utf-8"))


def recipe(app_id):
    value = recipes().get(app_id)
    if value is None:
        return None
    if (not APP_ID.fullmatch(value["id"]) or value["branch"] != "stable"
            or not isinstance(value["args"], list) or len(value["args"]) > 10
            or any(not isinstance(arg, str) or len(arg) > 200 or "\0" in arg for arg in value["args"])):
        raise ValueError("Invalid reviewed Flatpak recipe")
    return value


def launch_command(value, arch):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}", arch):
        raise ValueError("Invalid Flatpak architecture")
    return ["flatpak", "run", "--user", "--arch=" + arch,
            "--branch=" + value["branch"], value["id"], *value["args"]]


def catalog_routes():
    """Local-only discovery. Never contact a remote or install during listing."""
    from flatpak_backend import FlatpakBackend
    backend = None
    result = {key: {"mode": "unavailable", "provider": "flatpak", "reason": "flatpak_setup"}
              for key in recipes()}
    try:
        backend = FlatpakBackend()
        backend.trusted_remote()
        for key in result:
            try:
                value = recipe(key)
                installed = backend.installed(value)
                result[key] = {"mode": "direct", "provider": "flatpak", "operations": ["install"],
                               "installed": bool(installed), "appId": value["id"],
                               "cmd": launch_command(value, backend.arch)}
            except Exception as error:
                result[key]["reason"] = getattr(error, "code", "unavailable")
    except Exception:
        pass  # Optional bindings/remote do not disable the native catalog.
    finally:
        if backend:
            backend.close()
    return result
