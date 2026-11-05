#!/usr/bin/env python3
"""Exercise an installed system package in an isolated graphical user home."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import traceback
import urllib.error
import urllib.request

import desktop_smoke as smoke


def check_user_service():
    """This optional probe requires an unused account in the disposable VM."""
    home = Path.home()
    config = home / ".config/cozy-kids-launcher/config.json"
    unit = home / ".config/systemd/user/cozy-kids-launcher.service"
    if config.exists() or unit.exists():
        raise RuntimeError("The service probe requires an unused disposable desktop account")
    command = ["/usr/bin/cozy-kids-launcher", "--service"]
    enabled = False
    try:
        subprocess.run([*command, "enable"], check=True)
        enabled = True
        subprocess.run([*command, "start"], check=True)
        def ready():
            try:
                with urllib.request.urlopen("http://127.0.0.1:38431/api/update/status", timeout=2) as response:
                    return json.load(response).get("source") == "package-manager"
            except OSError:
                return False
        smoke.wait_until(ready, timeout=45)
        cache = home / ".cache/cozy-kids-launcher"
        browser = smoke.wait_until(lambda: smoke.live_process_record(cache / "browser.pid", "browser"), timeout=45)
        smoke.wait_until(lambda: "--kiosk" in smoke.browser_command_tokens(smoke.process_command(browser["pid"]) or []), timeout=30)
        status = json.loads(subprocess.check_output([*command, "status"], text=True))
        assert status["mode"] == "systemd" and status["unitState"] == "active"
        subprocess.run([*command, "stop"], check=True)
        status = json.loads(subprocess.check_output([*command, "status"], text=True))
        assert status["unitState"] == "inactive"
        assert status["lastLifecycle"]["reason"] == "manual-stop"
        for name, role in (("server", "server"), ("browser", "browser"), ("watchdog", "watchdog")):
            assert not smoke.live_process_record(cache / (name + ".pid"), role)
    finally:
        if enabled:
            subprocess.run([*command, "disable"], check=True)
    assert not unit.exists()
    return "system package user-service enable, graphical start, status, stop, cleanup and disable"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--desktop", choices=("gnome", "kde", "xfce"), required=True)
    parser.add_argument("--session", choices=("wayland", "x11"), required=True)
    parser.add_argument("--browser", required=True)
    parser.add_argument("--launch-mode", choices=("kiosk", "fullscreen"), required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--user-service", action="store_true", help="Also test the service in this unused disposable account's actual home")
    parser.add_argument("--recovery", action="store_true", help="Inject fullscreen loss and stalled overlay status in a disposable VM")
    parser.add_argument("--resize-x11", action="store_true", help="Also displace the control and resize the only output in a disposable XFCE X11 VM")
    args = parser.parse_args()
    if args.resize_x11 and (not args.recovery or args.desktop != "xfce" or args.session != "x11"):
        parser.error("--resize-x11 requires --recovery and a disposable XFCE X11 session")
    errors = smoke.environment_errors(args.desktop, args.session)
    if errors:
        raise RuntimeError(errors)
    args.artifacts.mkdir(parents=True, exist_ok=True)
    report = {"desktop": args.desktop, "session": args.session, "browser": args.browser,
              "mode": args.launch_mode, "version": subprocess.check_output(["dpkg-query", "-W", "cozy-kids-launcher"], text=True).strip(),
              "checks": [], "manualPending": ["Physical gameplay input", "Native Wayland focus and visual stacking"]}
    root = Path("/usr/share/cozy-kids-launcher")
    smoke.RUNTIME_SOURCE_ROOT = root
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
            app_window = smoke.wait_until(lambda: smoke.owned_fullscreen_window(tile["pid"]), timeout=15)
            smoke.wait_until(lambda: value if (value := smoke.live_process_record(cache / "overlay.pid", "overlay")) and value.get("ready") is True else None, timeout=15)
            overlay = smoke.wait_until(lambda: smoke.x11_window_ids("App Overlay"), timeout=15)
            if args.session == "x11":
                smoke.wait_until(lambda: smoke.x11_active_window_id() == app_window, timeout=8,
                                 message="Overlay took focus from the launched app")
                report["checks"].append("mapped overlay leaves keyboard focus on the owned app (X11)")
            if args.recovery:
                import desktop_recovery
                report["checks"].append(desktop_recovery.recover_fullscreen(tile["pid"]))
                if args.resize_x11:
                    report["checks"].append(desktop_recovery.resize_x11(overlay[-1], args.artifacts))
                report["stalledStatus"] = desktop_recovery.close_with_stalled_status(cache, root, args.artifacts)
                report["checks"].append(report["stalledStatus"]["check"])
            else:
                smoke.x11_click_overlay_close(overlay[-1])
            smoke.wait_until(lambda: not smoke.live_process_record(cache / "tile-process.pid", "tile-process"), timeout=20)
            report["checks"].append("owned KTurtle fullscreen and overlay close from system code")
            if args.session == "x11":
                smoke.wait_until(lambda: smoke.x11_window_is_active("Cozy Kids Launcher"), timeout=8,
                                 message="Overlay close did not restore launcher focus")
                report["checks"].append("overlay close restores the owned launcher browser focus (X11)")
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
    if args.user_service:
        try:
            report["checks"].append(check_user_service())
        except Exception:
            report["outcome"] = "failed"
            raise
        finally:
            (args.artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
