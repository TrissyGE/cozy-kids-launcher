#!/usr/bin/env python3
"""Exercise core launcher journeys in a real Chromium browser."""

import argparse
import getpass
import http.server
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from browser_driver import BrowserSession, find_browser, stop_process


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIN = "2468"


class ReleaseFixtureHandler(http.server.BaseHTTPRequestHandler):
    latest_version = "0.0.0"
    mode = "ok"

    def do_GET(self):
        if self.mode != "ok":
            self.send_error(503, "synthetic update service failure")
            return
        if self.path == "/releases/latest":
            payload = json.dumps({
                "tag_name": f"v{self.latest_version}",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {"name": f"cozy-kids-launcher-{self.latest_version}.tar.gz"},
                    {"name": "SHA256SUMS"},
                ],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/VERSION":
            payload = f"{self.latest_version}\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        else:
            self.send_error(404)
            return
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string, *args):
        pass


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_server(url, process, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Launcher server exited before becoming ready ({process.returncode})"
            )
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.load(response)
                if response.status == 200 and isinstance(payload, dict):
                    return
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError("Launcher server did not become ready")


def write_demo_config(config_path, browser_name):
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    config.update({
        "language": "en",
        "title": "E2E Home",
        "theme": "rosa",
        "layoutMode": "gross",
        "parentLabel": "Parent",
        "exitLabel": "Exit kids mode",
        "pinHash": "",
        "currentPage": 0,
        "autoScanDone": True,
        "timerMinutes": 0,
        "timerWarningMinutes": 5,
        "browser": browser_name,
        "tiles": [
            {
                "id": "paint",
                "label": "Paint",
                "emoji": "🎨",
                "cmd": ["true"],
                "visible": True,
            },
            {
                "id": "music",
                "label": "Music",
                "emoji": "🎵",
                "cmd": ["true"],
                "visible": True,
            },
        ],
    })
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def assert_js(browser, expression, message):
    value = browser.evaluate(expression)
    if value is not True:
        raise AssertionError(f"{message} (expression returned {value!r})")


def log_scenario(name):
    print(f"  ✓ {name}", flush=True)


def enter_parent_settings(browser):
    browser.click("#parentBtn")
    browser.wait_for(
        "!document.getElementById('pin').classList.contains('hidden')",
        message="PIN dialog did not open",
    )
    browser.set_value("#pinInput", PIN)
    browser.click("#pin .save")
    browser.wait_for(
        "!document.getElementById('admin').classList.contains('hidden')",
        message="Correct PIN did not open Parent settings",
    )


def run_scenarios(browser, release_fixture, installed_version):
    browser.wait_for(
        "typeof cfg !== 'undefined' && cfg !== null && "
        "document.querySelectorAll('#grid .tile:not(.placeholder)').length === 2",
        message="Home screen did not finish rendering",
    )
    assert_js(
        browser,
        "document.getElementById('title').textContent === 'E2E Home' && "
        "document.getElementById('kids').classList.contains('hidden') === false && "
        "Array.from(document.querySelectorAll('#grid .tile:not(.placeholder)'))"
        ".map(tile => tile.textContent.trim()).join('|').includes('Paint')",
        "Home title or tiles are incorrect",
    )
    log_scenario("home renders title and app tiles")

    browser.click("#parentBtn")
    browser.wait_for("!document.getElementById('admin').classList.contains('hidden')")
    browser.set_value("#cfgPin", PIN)
    browser.set_value("#cfgPinConfirm", PIN)
    browser.click("#setPinBtn")
    browser.wait_for("cfg.pinConfigured === true")
    browser.click("#backBtn")

    browser.click("#parentBtn")
    browser.wait_for("!document.getElementById('pin').classList.contains('hidden')")
    browser.set_value("#pinInput", "0000")
    browser.click("#pin .save")
    browser.wait_for("document.getElementById('pinErr').textContent.length > 0")
    assert_js(
        browser,
        "document.getElementById('admin').classList.contains('hidden')",
        "Wrong PIN unexpectedly opened Parent settings",
    )
    browser.set_value("#pinInput", PIN)
    browser.click("#pin .save")
    browser.wait_for("!document.getElementById('admin').classList.contains('hidden')")
    log_scenario("PIN setup rejects a wrong PIN and accepts the correct PIN")

    browser.click("#openThemeBtn")
    browser.wait_for("!document.getElementById('themeOverlay').classList.contains('hidden')")
    chosen = browser.evaluate(
        "(() => { const index=ALL_THEMES.findIndex(theme => theme.id==='weltraum');"
        " const tiles=document.querySelectorAll('#themeChooser .theme-thumb');"
        " if(index < 0 || !tiles[index]) return false; tiles[index].click(); return true; })()"
    )
    if chosen is not True:
        raise AssertionError("Space theme could not be selected")
    browser.set_value("#cfgTitle", "Polished E2E Home")
    browser.set_value("#cfgLayoutMode", "klein")
    browser.set_value("#cfgParentLabel", "Family controls")
    browser.click("#saveBtn")
    browser.wait_for(
        "document.getElementById('admin').classList.contains('hidden') && "
        "document.body.classList.contains('theme-weltraum')",
        message="Saved settings were not applied to the home screen",
    )
    assert_js(
        browser,
        "document.getElementById('title').textContent === 'Polished E2E Home' && "
        "document.getElementById('grid').classList.contains('klein') && "
        "document.getElementById('parentBtn').textContent === 'Family controls'",
        "Title, layout, or parent label did not update",
    )
    saved_config = browser.evaluate(
        "fetch('/api/config',{cache:'no-store'}).then(response => response.json())",
        await_promise=True,
    )
    expected = {
        "title": "Polished E2E Home",
        "layoutMode": "klein",
        "theme": "weltraum",
        "parentLabel": "Family controls",
    }
    if any(saved_config.get(key) != value for key, value in expected.items()):
        raise AssertionError(f"Saved config does not match the UI: {saved_config!r}")
    log_scenario("settings and theme selection persist and re-render")

    enter_parent_settings(browser)
    browser.set_value("#cfgTimerMinutes", "15")
    browser.click("#timerToggleBtn")
    browser.wait_for(
        "lastTimerStatus.active === true && lastTimerStatus.expired === false && "
        "document.getElementById('timerBadge').style.display === 'block'",
        message="Timer did not become active",
    )
    assert_js(
        browser,
        "document.getElementById('timerBadge').textContent.includes('15') || "
        "document.getElementById('timerBadge').textContent.includes('14')",
        "Timer badge does not show the remaining time",
    )
    browser.click("#timerToggleBtn")
    browser.wait_for(
        "lastTimerStatus.active === false && "
        "document.getElementById('timerBadge').style.display === 'none'",
        message="Timer did not stop cleanly",
    )
    log_scenario("screen timer starts, renders its badge, and stops")

    release_fixture.latest_version = installed_version
    release_fixture.mode = "ok"
    browser.click("#checkUpdateBtn")
    browser.wait_for(
        "document.getElementById('checkUpdateBtn').disabled === false && "
        "document.getElementById('updateMsg').textContent === uiText.updateUpToDate",
        message="Up-to-date check did not finish",
    )
    assert_js(
        browser,
        "document.getElementById('updateMsg').textContent === uiText.updateUpToDate && "
        "document.getElementById('updateRow').style.display === 'none'",
        "Up-to-date state was not rendered",
    )

    installed_major = int(installed_version.split(".", maxsplit=1)[0])
    available_version = f"{installed_major + 1}.0.0"
    release_fixture.latest_version = available_version
    browser.click("#checkUpdateBtn")
    encoded_available = json.dumps(available_version)
    browser.wait_for(
        "document.getElementById('checkUpdateBtn').disabled === false && "
        f"document.getElementById('updateMsg').textContent.includes({encoded_available})",
        message="Available-update check did not finish",
    )
    update_message = browser.evaluate("document.getElementById('updateMsg').textContent")
    update_visible = browser.evaluate(
        "document.getElementById('updateRow').style.display === 'grid'"
    )
    if available_version not in update_message or update_visible is not True:
        raise AssertionError("Available-update state was not rendered")

    release_fixture.mode = "error"
    browser.click("#checkUpdateBtn")
    browser.wait_for(
        "document.getElementById('checkUpdateBtn').disabled === false && "
        "document.getElementById('updateMsg').textContent === uiText.updateError",
        message="Failed update check did not finish",
    )
    assert_js(
        browser,
        "document.getElementById('updateMsg').textContent === uiText.updateError && "
        "document.getElementById('updateRow').style.display === 'none' && "
        "document.getElementById('checkUpdateBtn').disabled === false",
        "Update error state was not rendered or did not recover",
    )
    log_scenario("update check renders current, available, and error states")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", help="Chromium-family executable name")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=REPOSITORY_ROOT / ".test-artifacts" / "browser-e2e",
    )
    parser.add_argument("--timeout", type=float, default=25)
    args = parser.parse_args()

    browser_path = find_browser(args.browser)
    browser_name = Path(browser_path).name
    args.artifacts.mkdir(parents=True, exist_ok=True)
    print(f"Browser E2E: {browser_path}", flush=True)

    release_server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        ReleaseFixtureHandler,
    )
    release_thread = threading.Thread(target=release_server.serve_forever, daemon=True)
    release_thread.start()
    release_port = release_server.server_address[1]

    server_process = None
    server_log = None
    try:
        with tempfile.TemporaryDirectory(prefix="cozy-kids-browser-e2e-") as temp_dir:
            test_home = Path(temp_dir)
            install_log_path = args.artifacts / "install.log"
            with install_log_path.open("w", encoding="utf-8") as install_log:
                subprocess.run(
                    [
                        "bash",
                        "scripts/install.sh",
                        "--user",
                        getpass.getuser(),
                        "--home",
                        str(test_home),
                        "--lang",
                        "en",
                        "--browser",
                        browser_name,
                        "--launch-mode",
                        "window",
                        "--skip-browser-check",
                        "--force",
                    ],
                    cwd=REPOSITORY_ROOT,
                    stdout=install_log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )

            app_root = test_home / ".local" / "share" / "cozy-kids-launcher"
            config_path = test_home / ".config" / "cozy-kids-launcher" / "config.json"
            write_demo_config(config_path, browser_name)
            installed_version = (app_root / "version").read_text(encoding="utf-8").strip()
            ReleaseFixtureHandler.latest_version = installed_version

            app_port = available_port()
            environment = dict(os.environ)
            environment.update({
                "HOME": str(test_home),
                "COZY_KIDS_PORT": str(app_port),
                "COZY_KIDS_RELEASE_API_URL": (
                    f"http://127.0.0.1:{release_port}/releases/latest"
                ),
                "COZY_KIDS_RAW_URL": f"http://127.0.0.1:{release_port}",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            })
            server_log = (args.artifacts / "server.log").open("w", encoding="utf-8")
            server_process = subprocess.Popen(
                ["python3", str(app_root / "server.py")],
                cwd=app_root,
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )
            base_url = f"http://127.0.0.1:{app_port}"
            wait_for_server(f"{base_url}/api/config", server_process)

            with BrowserSession(
                browser_name,
                f"{base_url}/index.html",
                test_home / "browser-profile",
                args.artifacts / "browser.log",
                timeout=args.timeout,
                width=1440,
                height=900,
            ) as browser:
                try:
                    run_scenarios(browser, ReleaseFixtureHandler, installed_version)
                    browser.screenshot(args.artifacts / "final-state.png")
                except Exception:
                    browser.screenshot(args.artifacts / "failure.png")
                    raise
    finally:
        if server_process:
            stop_process(server_process)
        if server_log:
            server_log.close()
        release_server.shutdown()
        release_server.server_close()
        release_thread.join(timeout=5)

    print("Browser E2E passed: 6 core journeys, 10 UI states", flush=True)
    print(f"Artifacts: {args.artifacts}", flush=True)


if __name__ == "__main__":
    main()
