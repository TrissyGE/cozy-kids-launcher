#!/usr/bin/env python3
"""Create the four real UI screenshots used by the GitHub README.

The command installs the current checkout into a temporary home directory,
starts its local server, captures deterministic 1440x900 views through a
Chromium-family browser, and removes the temporary profile afterwards.
It never reads or changes the developer's installed launcher configuration.
"""

import argparse
import getpass
import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
CAPTURE_SCRIPT = REPOSITORY_ROOT / "scripts" / "wsl" / "capture-page.py"
INSTALL_SCRIPT = REPOSITORY_ROOT / "scripts" / "install.sh"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "screenshots"


def find_browser(requested):
    candidates = [requested] if requested else [
        "google-chrome",
        "google-chrome-stable",
        "chromium",
        "chromium-browser",
    ]
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return candidate
    names = ", ".join(candidate for candidate in candidates if candidate)
    raise RuntimeError(f"No screenshot browser found ({names})")


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_server(port, process, timeout=15):
    deadline = time.monotonic() + timeout
    last_error = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Launcher server exited early ({process.returncode})")
        connection = None
        try:
            connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            connection.request("GET", "/api/config")
            response = connection.getresponse()
            if response.status == 200:
                response.close()
                return
        except Exception as error:
            last_error = error
            time.sleep(0.1)
        finally:
            if connection:
                connection.close()
    raise TimeoutError(f"Launcher server did not become ready: {last_error}")


def stop_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def install_profile(profile, browser):
    subprocess.run(
        [
            "bash",
            str(INSTALL_SCRIPT),
            "--user",
            getpass.getuser(),
            "--home",
            str(profile),
            "--lang",
            "en",
            "--browser",
            browser,
            "--launch-mode",
            "window",
            "--force",
        ],
        cwd=REPOSITORY_ROOT,
        check=True,
        stdout=subprocess.DEVNULL,
    )


def write_config(profile, theme):
    config = {
        "configVersion": 2,
        "language": "en",
        "parentLabel": "Parents",
        "exitLabel": "Exit kids mode",
        "shutdownLabel": "Shut down",
        "pinHash": "",
        "autoScanDone": True,
        "setupCompleted": True,
        "activeProfileId": "default",
        "profiles": [{
            "id": "default",
            "name": "Kiddo",
            "avatar": "🌈",
            "title": "Ready for adventure! 🌈",
            "theme": theme,
            "layoutMode": "gross",
            "currentPage": 0,
            "timerMinutes": 30,
            "timerWarningMinutes": 5,
            "favorites": [],
            "appLimits": {},
            "tiles": [
                {
                    "id": "paint",
                    "label": "Paint",
                    "emoji": "🎨",
                    "cmd": ["tuxpaint"],
                    "visible": True,
                },
                {
                    "id": "games",
                    "label": "Learning games",
                    "emoji": "🧩",
                    "cmd": ["gcompris-qt"],
                    "visible": True,
                },
                {
                    "id": "media",
                    "label": "Movies & music",
                    "emoji": "🎵",
                    "cmd": ["special:filme-musik"],
                    "visible": True,
                },
                {
                    "id": "kika",
                    "label": "KiKA",
                    "emoji": "🚀",
                    "cmd": ["special:external-browser:https://www.kika.de/"],
                    "visible": True,
                },
            ],
        }],
    }
    path = profile / ".config" / "cozy-kids-launcher" / "config.json"
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def capture(browser, url, output, profile, prepare_expression=""):
    command = [
        sys.executable,
        str(CAPTURE_SCRIPT),
        "--browser",
        browser,
        "--url",
        url,
        "--output",
        str(output),
        "--profile",
        str(profile),
        "--width",
        "1440",
        "--height",
        "900",
        "--ready-expression",
        "typeof cfg === 'object' && cfg !== null",
    ]
    if prepare_expression:
        command.extend(["--prepare-expression", prepare_expression])
    subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", help="Chromium-family browser command")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    if os.name != "posix":
        raise SystemExit("Run this command on Linux or through WSL.")

    browser = find_browser(args.browser)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="cozy-kids-screenshots-") as temporary:
        root = Path(temporary)
        launcher_home = root / "home"
        launcher_home.mkdir()
        install_profile(launcher_home, browser)
        write_config(launcher_home, "rosa")

        port = free_port()
        url = f"http://127.0.0.1:{port}"
        environment = dict(os.environ)
        environment["HOME"] = str(launcher_home)
        environment["COZY_KIDS_PORT"] = str(port)
        server_script = (
            launcher_home
            / ".local"
            / "share"
            / "cozy-kids-launcher"
            / "server.py"
        )
        server_log_path = root / "server.log"
        with server_log_path.open("w", encoding="utf-8") as server_log:
            server = subprocess.Popen(
                [sys.executable, str(server_script)],
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )
            try:
                wait_for_server(port, server)
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-home-default.png",
                    root / "chrome-home-default",
                )
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-admin-general.png",
                    root / "chrome-admin",
                    "(async () => { enterAdmin(); await checkUpdate(); await loadBackups(); return true; })()",
                )
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-theme-picker.png",
                    root / "chrome-theme-picker",
                    "(async () => { enterAdmin(); await checkUpdate(); await loadBackups(); openThemePicker(); return true; })()",
                )
                write_config(launcher_home, "ocean")
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-home-world.png",
                    root / "chrome-home-world",
                )
            except Exception:
                stop_process(server)
                server_log.flush()
                details = server_log_path.read_text(encoding="utf-8").strip()
                if details:
                    print(details, file=sys.stderr)
                raise
            finally:
                stop_process(server)

    print(f"README screenshots written to {output_dir}")


if __name__ == "__main__":
    main()
