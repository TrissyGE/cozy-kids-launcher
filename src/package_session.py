"""Unprivileged first start and reversible entry-point migration for system packages."""

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from language_registry import DEFAULT_LANGUAGE, LANGUAGE_CODES
from translation_data import load_translations
from app_detection import BROWSER_CANDIDATES, find_browser


APP_ID = "cozy-kids-launcher"
SYSTEM_COMMAND = "/usr/bin/cozy-kids-launcher"
WRAPPER = f'#!/bin/sh\nexec {SYSTEM_COMMAND} "$@"\n'


def atomic_text(path, text, mode=0o600):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".cozy-package-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


class PackageSession:
    def __init__(self, home, root, environment):
        self.home, self.root, self.environment = Path(home), Path(root), environment
        self.legacy = self.home / ".local/share" / APP_ID
        self.config = self.home / ".config" / APP_ID / "config.json"
        self.cache = self.home / ".cache" / APP_ID
        self.migration_file = self.home / ".config" / APP_ID / "package-migration.json"

    @contextmanager
    def idle(self):
        self.cache.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.cache / "launcher.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Close the running launcher before changing its installation.") from None
            yield

    def language(self):
        language = self.environment.get("LC_ALL") or self.environment.get("LC_MESSAGES") or self.environment.get("LANG", "")
        code = language.split(".")[0].split("@")[0].replace("-", "_").split("_")[0].lower()
        return code if code in LANGUAGE_CODES else DEFAULT_LANGUAGE

    def first_start(self):
        if os.path.lexists(self.legacy / "server.py"):
            state = json.loads(self.migration_file.read_text(encoding="utf-8")) if self.migration_file.is_file() else {}
            if state.get("status") != "complete":
                raise ValueError(f"Existing script installation found. Close it and run {SYSTEM_COMMAND} --migrate-script-install.")
        # Opening exclusively preserves an existing configuration byte for byte,
        # including a malformed file which must go through normal recovery.
        if os.path.lexists(self.config):
            return
        config = json.loads((self.root / "default-config.json").read_text(encoding="utf-8"))
        language = self.language()
        text = load_translations(language)
        config.update(language=language, parentLabel=text["parent_label"], exitLabel=text["exit_label"], shutdownLabel=text["shutdown_label"])
        profile = config["profiles"][0]
        profile["title"] = text["config_title"]
        for tile, key in zip(profile["tiles"], ("tile_paint", "tile_games", "tile_music", "tile_browser")):
            tile["label"] = text[key]
        self.config.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Link a fully written file into place so a concurrent first launch sees
        # either no config or a complete config, never a partially written JSON.
        descriptor, name = tempfile.mkstemp(dir=self.config.parent, prefix=".cozy-default-")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(config, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
            try:
                os.link(name, self.config)
            except FileExistsError:
                pass
        finally:
            Path(name).unlink(missing_ok=True)

    def entry_points(self):
        entries = {self.home / ".local/bin" / APP_ID: (WRAPPER, 0o755)}
        desktop = (self.root / "cozy-kids-launcher.desktop").read_text(encoding="utf-8")
        entries[self.home / ".local/share/applications/cozy-kids-launcher.desktop"] = (desktop, 0o644)
        for directory in ("Desktop", "Schreibtisch"):
            path = self.home / directory / "Cozy Kids Launcher.desktop"
            if os.path.lexists(path):
                entries[path] = (desktop, 0o755)
        autostart = self.home / ".config/autostart/cozy-kids-launcher-autostart.desktop"
        if os.path.lexists(autostart):
            entries[autostart] = (desktop.replace(f"Exec={SYSTEM_COMMAND}\n", f"Exec={SYSTEM_COMMAND} --autostart\n") + "NoDisplay=true\nX-KDE-autostart-phase=2\n", 0o644)
        service = self.home / ".config/systemd/user/cozy-kids-launcher.service"
        if os.path.lexists(service):
            old = (self.legacy / "cozy-kids-launcher.service").read_text(encoding="utf-8")
            if service.is_symlink() or service.read_text(encoding="utf-8") != old:
                raise ValueError("The local user service was customized. Review it before migration.")
            entries[service] = ((self.root / "cozy-kids-launcher.service").read_text(encoding="utf-8"), 0o644)
        entries[self.legacy / "package-managed"] = ("system-package\n", 0o600)
        return entries

    def migrate(self):
        with self.idle():
            if self.migration_file.is_file():
                state = json.loads(self.migration_file.read_text(encoding="utf-8"))
                if state.get("status") == "complete":
                    return state["backup"]
                raise ValueError("An interrupted migration exists. Run --restore-script-install before retrying.")
            if not (self.legacy / "server.py").is_file():
                raise ValueError("No script installation found for this user.")
            if os.path.lexists(self.legacy / "update-trigger.sh"):
                raise ValueError("A script update is pending. Finish or review it before migration.")
            entries = self.entry_points()
            # Preflight all paths before changing anything. Never replace linked
            # entries or follow a user-selected parent into another directory.
            for path in entries:
                if path.is_symlink() or (path.exists() and not path.is_file()):
                    raise ValueError("Linked or non-file launcher entry requires manual review.")
                if not path.parent.resolve().is_relative_to(self.home.resolve()):
                    raise ValueError("Launcher entry points outside the user home require manual review.")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
            backups = self.home / ".local/share/cozy-kids-launcher-backups"
            backups.mkdir(parents=True, exist_ok=True, mode=0o700)
            backup = Path(tempfile.mkdtemp(prefix=f"script-migration-{stamp}-", dir=backups))
            saved = []
            for index, (path, (text, mode)) in enumerate(entries.items()):
                original = path.exists()
                if original:
                    shutil.copy2(path, backup / str(index))
                saved.append({"path": str(path.relative_to(self.home)), "original": original, "replacement": text, "mode": mode})
            state = {"status": "pending", "backup": str(backup), "entries": saved}
            atomic_text(self.migration_file, json.dumps(state, indent=2) + "\n")
            try:
                for path, (text, mode) in entries.items():
                    atomic_text(path, text, mode)
                state["status"] = "complete"
                atomic_text(self.migration_file, json.dumps(state, indent=2) + "\n")
            except OSError:
                self._restore(state)
                raise
            return str(backup)

    def _restore(self, state):
        backup = Path(state["backup"])
        if not backup.resolve().is_relative_to((self.home / ".local/share/cozy-kids-launcher-backups").resolve()):
            raise ValueError("Migration backup is outside the backup directory.")
        plans = []
        for index, entry in enumerate(state["entries"]):
            path = self.home / entry["path"]
            if not path.resolve().is_relative_to(self.home.resolve()) or path.is_symlink():
                raise ValueError("Migration entry requires manual review.")
            original = backup / str(index)
            current = path.read_text(encoding="utf-8") if path.exists() else None
            previous = original.read_text(encoding="utf-8") if entry["original"] else None
            if current not in (None, entry["replacement"], previous):
                raise ValueError("A migrated entry was changed. Review it before restoring.")
            plans.append((path, original if entry["original"] else None))
        for path, original in reversed(plans):
            if original:
                atomic_text(path, original.read_text(encoding="utf-8"), original.stat().st_mode & 0o777)
            else:
                path.unlink(missing_ok=True)
        self.migration_file.unlink(missing_ok=True)

    def restore(self):
        with self.idle():
            self._restore(json.loads(self.migration_file.read_text(encoding="utf-8")))


def main():
    if os.geteuid() == 0:
        sys.exit("Start Cozy Kids from your regular desktop account.")
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--browser", choices=BROWSER_CANDIDATES)
    parser.add_argument("--launch-mode", choices=("kiosk", "fullscreen", "window"))
    options = parser.add_mutually_exclusive_group()
    options.add_argument("--migrate-script-install", action="store_true")
    options.add_argument("--restore-script-install", action="store_true")
    options.add_argument("--initialize-only", action="store_true")
    args, remaining = parser.parse_known_args()
    root = Path(__file__).resolve().parent
    session = PackageSession(Path.home(), root, os.environ)
    try:
        if args.migrate_script_install:
            print("Script entry points backed up in " + session.migrate())
            print("Run systemctl --user daemon-reload if the optional user service is enabled.")
            return
        if args.restore_script_install:
            session.restore()
            print("Script entry points restored. Reload the optional user service before starting it.")
            return
        session.first_start()
        if not args.initialize_only:
            browser = args.browser or find_browser()
            if browser:
                os.environ["COZY_KIDS_PACKAGE_BROWSER"] = browser
            if args.launch_mode:
                os.environ["COZY_KIDS_PACKAGE_MODE"] = args.launch_mode
            os.execv("/bin/bash", ["bash", str(root / "launcher.sh"), *remaining])
    except (OSError, ValueError, KeyError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
