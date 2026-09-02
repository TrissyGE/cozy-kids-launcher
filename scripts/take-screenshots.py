#!/usr/bin/env python3
"""Create the real UI screenshots used by the GitHub README and website.

The command installs the current checkout into a temporary home directory,
starts its local server, captures deterministic 1440x900 views through a
Chromium-family browser, and removes the temporary profile afterwards.
It never reads or changes the developer's installed launcher configuration.
"""

import argparse
import getpass
import hashlib
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


def demo_tiles():
    return [
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
    ]


def demo_profile(profile_id, name, avatar, title, theme="rosa"):
    return {
        "id": profile_id,
        "name": name,
        "avatar": avatar,
        "title": title,
        "theme": theme,
        "layoutMode": "gross",
        "currentPage": 0,
        "timerMinutes": 30,
        "timerWarningMinutes": 5,
        "favorites": [],
        "appLimits": {},
        "weeklySchedule": {"enabled": False, "days": {}},
        "appAvailability": {},
        "tiles": demo_tiles(),
    }


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
        "activityTrackingEnabled": True,
        "activeProfileId": "default",
        "profiles": [
            demo_profile("default", "Alex", "🌈", "Ready for adventure! 🌈", theme),
            demo_profile("sam", "Sam", "🚀", "Let's explore space! 🚀", "ocean"),
            demo_profile("mika", "Mika", "🎨", "Time to create! 🎨", "wald"),
        ],
    }
    path = profile / ".config" / "cozy-kids-launcher" / "config.json"
    path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def write_demo_state(profile):
    media_files = [
        profile / "Videos" / "Moon Mission.mp4",
        profile / "Videos" / "Dinosaur Detectives.mkv",
        profile / "Videos" / "Ocean Adventure.webm",
        profile / "Music" / "Rainbow Songs.flac",
        profile / "Music" / "Dance Party.mp3",
        profile / "Music" / "Bedtime Stories.ogg",
    ]
    for media_file in media_files:
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"Cozy Kids screenshot demo\n")

    media_ids = [
        hashlib.sha256(os.fsencode(media_file.resolve())).hexdigest()[:24]
        for media_file in media_files
    ]
    state_root = profile / ".local" / "state" / "cozy-kids-launcher"
    state_root.mkdir(parents=True, exist_ok=True)
    (state_root / "media.json").write_text(
        json.dumps({
            "mediaStateVersion": 1,
            "profiles": {
                "default": {
                    "favorites": [media_ids[0], media_ids[3]],
                    "recents": [media_ids[3], media_ids[1], media_ids[0]],
                }
            },
        }, indent=2) + "\n",
        encoding="utf-8",
    )

    now = int(time.time())
    (state_root / "activity.json").write_text(
        json.dumps({
            "activityVersion": 1,
            "discardBefore": 0,
            "records": [
                {"profileId": "sam", "tileId": "kika", "startedAt": now - 7400, "durationSeconds": 780},
                {"profileId": "mika", "tileId": "paint", "startedAt": now - 5100, "durationSeconds": 1320},
                {"profileId": "default", "tileId": "games", "startedAt": now - 2800, "durationSeconds": 1560},
                {"profileId": "default", "tileId": "media", "startedAt": now - 900, "durationSeconds": 540},
            ],
        }, indent=2) + "\n",
        encoding="utf-8",
    )


def capture(
    browser,
    url,
    output,
    profile,
    prepare_expression="",
    ready_expression="typeof cfg === 'object' && cfg !== null",
):
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
        ready_expression,
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
        write_demo_state(launcher_home)

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
                    "(async () => { enterAdmin(); await loadBackups(); await loadActivityDashboard(); return true; })()",
                )
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-theme-picker.png",
                    root / "chrome-theme-picker",
                    "(async () => { enterAdmin(); await loadBackups(); openThemePicker(); return true; })()",
                )
                write_config(launcher_home, "ocean")
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-profile-picker.png",
                    root / "chrome-profile-picker",
                    "(() => { openProfilePicker(); return true; })()",
                )
                write_config(launcher_home, "wald")
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-admin-children.png",
                    root / "chrome-admin-children",
                    "(async () => { enterAdmin(); await loadBackups(); activateAdminSection('children'); return true; })()",
                )
                write_config(launcher_home, "weltraum")
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-admin-screen-time.png",
                    root / "chrome-admin-screen-time",
                    """(() => {
                      enterAdmin();
                      cfg.weeklySchedule={enabled:true,days:{
                        monday:[{start:'07:30',end:'19:30'}],
                        tuesday:[{start:'07:30',end:'19:30'}],
                        wednesday:[{start:'07:30',end:'19:30'}],
                        thursday:[{start:'07:30',end:'19:30'}],
                        friday:[{start:'07:30',end:'20:00'}],
                        saturday:[{start:'08:00',end:'20:30'}],
                        sunday:[{start:'08:00',end:'19:30'}]
                      }};
                      cfg.appAvailability={games:{enabled:true,days:{
                        monday:[{start:'15:00',end:'18:00'}],
                        wednesday:[{start:'15:00',end:'18:00'}],
                        friday:[{start:'15:00',end:'18:30'}]
                      }}};
                      renderAdmin();
                      selectAppSchedule('games');
                      activateAdminSection('screen-time');
                      return true;
                    })()""",
                )
                write_config(launcher_home, "blau")
                capture(
                    browser,
                    url,
                    output_dir / "screenshot-admin-appearance.png",
                    root / "chrome-admin-appearance",
                    """(() => {
                      enterAdmin();
                      cfg.theme='ocean';
                      cfg.themeMotionEnabled=true;
                      cfg.themeTimeOfDayEnabled=true;
                      cfg.soundFeedbackEnabled=true;
                      cfg.speechFeedbackEnabled=true;
                      cfg.celebrationEnabled=true;
                      cfg.accessibilityLargeText=true;
                      cfg.accessibilityHighContrast=true;
                      cfg.accessibilityKeyboardFocus=true;
                      renderAdmin();
                      activateAdminSection('appearance');
                      return true;
                    })()""",
                )
                write_config(launcher_home, "regenbogen")
                capture(
                    browser,
                    url + "/media.html?tile=media",
                    output_dir / "screenshot-media-library.png",
                    root / "chrome-media-library",
                    ready_expression=(
                        "typeof mediaConfig === 'object' && mediaConfig !== null "
                        "&& Array.isArray(mediaItems) && mediaItems.length >= 6"
                    ),
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
