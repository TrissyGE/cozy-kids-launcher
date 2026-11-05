#!/usr/bin/env python3
"""Exercise an installed system package in an isolated graphical user home."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import traceback
import urllib.error
import urllib.request

import desktop_smoke as smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", choices=("gnome", "kde", "xfce"), required=True)
    parser.add_argument("--session", choices=("wayland", "x11"), required=True)
    parser.add_argument("--browser", required=True)
    parser.add_argument("--launch-mode", choices=("kiosk", "fullscreen"), required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    errors = smoke.environment_errors(args.desktop, args.session)
    if errors:
        raise RuntimeError(errors)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    report = {"desktop": args.desktop, "session": args.session, "browser": args.browser,
              "mode": args.launch_mode, "version": subprocess.check_output(["dpkg-query", "-W", "cozy-kids-launcher"], text=True).strip(),
              "checks": [], "manualPending": ["Physical gameplay input", "Native Wayland focus and visual stacking"]}
    root = Path("/usr/share/cozy-kids-launcher")
    sys.path.insert(0, str(root))
    assert (root / "package-managed").is_file()
    assert not os.access(root, os.W_OK), "System runtime must be read-only to the family user"
    entry = next(item for item in json.loads((root / "recommendations.json").read_text()) if item["id"] == "kturtle")
    with tempfile.TemporaryDirectory(prefix="cozy-system-package-", dir=smoke.temporary_home_parent(args.browser)) as directory:
        home = Path(directory)
        port = smoke.available_port()
        environment = {**os.environ, "HOME": directory, "COZY_KIDS_PORT": str(port), "NO_PROXY": "127.0.0.1,localhost"}
        command = ["/usr/bin/cozy-kids-launcher", "--browser", args.browser, "--launch-mode", args.launch_mode]
        subprocess.run([*command, "--initialize-only"], env=environment, check=True)
        config = home / ".config/cozy-kids-launcher/config.json"
        smoke.write_smoke_config(config, args.browser, entry)
        base = f"http://127.0.0.1:{port}"
        cache = home / ".cache/cozy-kids-launcher"
        launcher = None
        try:
            with (args.artifacts / "launcher.log").open("w") as log:
                launcher = subprocess.Popen(command, env=environment, stdout=log, stderr=log)
            smoke.wait_until(lambda: smoke._server_ready(base, launcher), timeout=45)
            record = smoke.wait_until(lambda: smoke.live_process_record(cache / "browser.pid", "browser"))
            browser_command = smoke.wait_until(lambda: value if smoke.browser_command_ready(value := smoke.process_command(record["pid"]), args.browser) else None)
            smoke.verify_browser_mode(browser_command, args.browser, args.launch_mode)
            report["checks"].append("system runtime server and requested browser mode")
            with urllib.request.urlopen(base + "/index.html", timeout=10) as response:
                assert b"Cozy" in response.read()
            with urllib.request.urlopen(base + "/api/update/status", timeout=10) as response:
                assert json.load(response)["source"] == "package-manager"
            request = urllib.request.Request(base + "/api/update", data=b"{}", headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(request, timeout=10)
                raise AssertionError("Package release updater was available")
            except urllib.error.HTTPError as error:
                assert error.code == 409
            report["checks"].append("package update owner and release updater refusal")
            assert smoke.request(base + "/launch/desktop-smoke", method="POST", timeout=45)[0] == 204
            tile = smoke.wait_until(lambda: smoke.live_process_record(cache / "tile-process.pid", "tile-process"), timeout=15)
            smoke.wait_until(lambda: smoke.owned_fullscreen_window(tile["pid"]), timeout=15)
            smoke.wait_until(lambda: smoke.live_process_record(cache / "overlay.pid", "overlay"), timeout=15)
            overlay = smoke.wait_until(lambda: smoke.x11_window_ids("App Overlay"), timeout=15)
            # A Tk title can become observable before the first map/raise and
            # widget layout finish. Click after that initial placement settles.
            time.sleep(1)
            smoke.x11_click_overlay_close(overlay[-1])
            smoke.wait_until(lambda: not smoke.live_process_record(cache / "tile-process.pid", "tile-process"), timeout=20)
            report["checks"].append("owned KTurtle fullscreen and overlay close from system code")
            assert smoke.request(base + "/exit-kids", method="POST")[0] == 204
            launcher.wait(timeout=25)
            assert launcher.returncode == 0
            for name, role in (("server", "server"), ("browser", "browser"), ("tile-process", "tile-process"), ("overlay", "overlay"), ("watchdog", "watchdog")):
                assert not smoke.live_process_record(cache / (name + ".pid"), role)
            report["checks"].append("Parent exit and owned-process cleanup")
            report["outcome"] = "automation-passed-manual-pending"
        except Exception:
            report["outcome"] = "failed"
            raise
        finally:
            if launcher and launcher.poll() is None:
                launcher.terminate()
                launcher.wait(timeout=30)
            smoke.copy_runtime_artifacts(home, args.artifacts)
            (args.artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
