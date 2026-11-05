#!/usr/bin/env python3
"""Build a reproducible, rootless system package without publishing a release."""

import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
APP_ID = "cozy-kids-launcher"
SYSTEM_ROOT = f"/usr/share/{APP_ID}"
DESKTOP = """[Desktop Entry]
Type=Application
Version=1.0
Name=Cozy Kids Launcher
Comment=A local family launcher
Exec=/usr/bin/cozy-kids-launcher
TryExec=/usr/bin/cozy-kids-launcher
Icon=preferences-desktop-theme
Terminal=false
Categories=Education;Game;
"""


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def write(path, text, mode=0o644):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(mode)


def build(output, version=None):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    epoch = int(os.environ.get("SOURCE_DATE_EPOCH") or git("show", "-s", "--format=%ct", "HEAD"))
    version = version or (ROOT / "VERSION").read_text(encoding="utf-8").strip() + "+git" + git("rev-parse", "--short=12", "HEAD") + "-1"
    if not re.fullmatch(r"[0-9][0-9A-Za-z.+~:-]*", version):
        raise ValueError("Invalid Debian version")
    with tempfile.TemporaryDirectory(prefix="cozy-deb-") as temporary:
        temporary = Path(temporary)
        home, package = temporary / "home", temporary / "package"
        home.mkdir()
        result = subprocess.run([
            "bash", str(ROOT / "scripts/install.sh"), "--user", getpass.getuser(),
            "--home", str(home), "--lang", "en", "--skip-browser-check", "--force",
        ], cwd=ROOT, input="", text=True, capture_output=True,
            env={**os.environ, "COZY_KIDS_PACKAGE_STAGE": "1"})
        if result.returncode:
            raise RuntimeError(result.stdout + result.stderr)
        runtime = package / "usr/share" / APP_ID
        shutil.copytree(home / ".local/share" / APP_ID, runtime)
        for name in ("uninstall.txt", "update.sh"):
            (runtime / name).unlink(missing_ok=True)
        shutil.copyfile(ROOT / "src/package_session.py", runtime / "package_session.py")
        launcher = (home / ".local/bin" / APP_ID).read_text(encoding="utf-8")
        launcher = launcher.replace('APP_ROOT="$HOME/.local/share/cozy-kids-launcher"', f'APP_ROOT="{SYSTEM_ROOT}"', 1)
        launcher = re.sub(r'^BROWSER_CMD="[^"]*"$', 'BROWSER_CMD="${COZY_KIDS_PACKAGE_BROWSER:-firefox}"', launcher, count=1, flags=re.MULTILINE)
        launcher = launcher.replace('LAUNCH_MODE="kiosk"', 'LAUNCH_MODE="${COZY_KIDS_PACKAGE_MODE:-kiosk}"', 1)
        if f'APP_ROOT="{SYSTEM_ROOT}"' not in launcher:
            raise ValueError("Installer launcher layout changed")
        write(runtime / "launcher.sh", launcher, 0o755)
        service = (runtime / "cozy-kids-launcher.service").read_text(encoding="utf-8")
        write(runtime / "cozy-kids-launcher.service", service.replace("%h/.local/bin/cozy-kids-launcher", "/usr/bin/cozy-kids-launcher"))
        shutil.copyfile(home / ".config" / APP_ID / "config.json", runtime / "default-config.json")
        write(runtime / "package-managed", "system-package\n")
        write(runtime / "cozy-kids-launcher.desktop", DESKTOP)
        write(package / "usr/share/applications/cozy-kids-launcher.desktop", DESKTOP)
        write(package / "usr/bin" / APP_ID, f'#!/bin/sh\nexec python3 {SYSTEM_ROOT}/package_session.py "$@"\n', 0o755)
        doc = package / "usr/share/doc" / APP_ID
        doc.mkdir(parents=True)
        shutil.copyfile(ROOT / "LICENSE", doc / "copyright")
        shutil.copyfile(ROOT / "docs/PACKAGING.md", doc / "README.Packaging")
        installed_size = sum(path.stat().st_size for path in package.rglob("*") if path.is_file())
        write(package / "DEBIAN/control", f"""Package: {APP_ID}
Version: {version}
Section: education
Priority: optional
Architecture: all
Maintainer: TrissyGE <noreply@github.com>
Homepage: https://github.com/TrissyGE/cozy-kids-launcher
Installed-Size: {(installed_size + 1023) // 1024}
Depends: bash, python3 (>= 3.9), python3-tk, util-linux
Recommends: firefox | chromium | chromium-browser, packagekit, python3-dbus, xdotool, wmctrl, zenity
Description: Local family launcher with Parent controls
 A browser-based Linux launcher for family profiles, approved applications,
 local media and optional emulators. Configuration stays in the user's home.
""")
        # Normalize all modes and timestamps after the installer. The temporary
        # home, backup timestamp, builder uid and wall clock never enter the deb.
        for path in sorted(package.rglob("*")):
            if path.is_symlink():
                raise ValueError("Unexpected symlink in package payload")
            executable = path.name in (APP_ID, "launcher.sh", "process_supervisor.py", "overlay.py", "timer_watchdog.py")
            path.chmod(0o755 if path.is_dir() or executable else 0o644)
            os.utime(path, (epoch, epoch))
        os.utime(package, (epoch, epoch))
        destination = output / f"{APP_ID}_{version}_all.deb"
        environment = {**os.environ, "SOURCE_DATE_EPOCH": str(epoch), "LC_ALL": "C", "TZ": "UTC"}
        subprocess.run(["dpkg-deb", "--root-owner-group", "--threads-max=1", "-Zxz", "-z6", "--build", str(package), str(destination)], check=True, env=environment)
        digest = hashlib.sha256(destination.read_bytes()).hexdigest()
        write(output / (destination.name + ".sha256"), f"{digest}  {destination.name}\n")
        return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--version", help="Debian package version only, without changing VERSION or tags")
    args = parser.parse_args()
    print(build(args.output, args.version))
