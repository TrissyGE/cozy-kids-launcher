#!/usr/bin/env python3
"""Run an isolated launcher smoke test inside a real Linux desktop session."""

import argparse
import getpass
import json
import os
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
DESKTOP_ALIASES = {
    "gnome": ("gnome", "ubuntu:gnome", "ubuntu"),
    "kde": ("kde", "plasma", "kde:plasma"),
    "xfce": ("xfce", "xfce4"),
}
BROWSER_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
    "firefox",
    "firefox-esr",
)
MANUAL_CHECKS = (
    "Autostart opens exactly one launcher after a fresh login",
    "The selected browser mode fits the display without a black screen",
    "The app overlay stays reachable above a launched child app",
    "Closing a child app returns focus to the launcher",
    "The desktop shortcut reopens the launcher without a duplicate instance",
    "The optional shutdown helper powers off the disposable VM cleanly",
)


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00",
        "Z",
    )


def command_version(candidates):
    for command in candidates:
        executable = shutil.which(command)
        if not executable:
            continue
        try:
            result = subprocess.run(
                [executable, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=5,
            )
            output = (result.stdout or result.stderr).strip().splitlines()
            if output:
                return output[0][:200]
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "unknown"


def distribution_identity(path="/etc/os-release"):
    values = {}
    try:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.startswith("#"):
                continue
            key, value = line.split("=", maxsplit=1)
            values[key] = value.strip().strip('"')
    except OSError:
        pass
    return {
        "id": values.get("ID", "unknown")[:80],
        "version": values.get("VERSION_ID", "unknown")[:80],
    }


def repository_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return "unknown"


def is_wsl(proc_version=None, environment=None):
    environment = os.environ if environment is None else environment
    if environment.get("WSL_DISTRO_NAME"):
        return True
    if proc_version is None:
        try:
            proc_version = Path("/proc/version").read_text(encoding="utf-8")
        except OSError:
            proc_version = ""
    return "microsoft" in proc_version.lower()


def canonical_desktop(value):
    normalized = (value or "").strip().lower()
    parts = {part for part in normalized.replace(";", ":").split(":") if part}
    for desktop, aliases in DESKTOP_ALIASES.items():
        for alias in aliases:
            if normalized == alias or alias in parts:
                return desktop
    return "unknown"


def detected_session(environment=None):
    environment = os.environ if environment is None else environment
    declared = environment.get("XDG_SESSION_TYPE", "").strip().lower()
    if declared in ("x11", "wayland"):
        return declared
    if environment.get("WAYLAND_DISPLAY"):
        return "wayland"
    if environment.get("DISPLAY"):
        return "x11"
    return "unknown"


def environment_errors(expected_desktop, expected_session, environment=None, wsl=None):
    environment = os.environ if environment is None else environment
    wsl = is_wsl(environment=environment) if wsl is None else wsl
    errors = []
    actual_desktop = canonical_desktop(environment.get("XDG_CURRENT_DESKTOP", ""))
    actual_session = detected_session(environment)
    if wsl:
        errors.append("WSL/WSLg is not a full desktop session")
    if actual_desktop != expected_desktop:
        errors.append(
            f"expected {expected_desktop}, detected {actual_desktop} "
            f"from XDG_CURRENT_DESKTOP"
        )
    if actual_session != expected_session:
        errors.append(f"expected {expected_session}, detected {actual_session}")
    if not environment.get("DBUS_SESSION_BUS_ADDRESS"):
        errors.append("DBUS_SESSION_BUS_ADDRESS is missing")
    if expected_session == "x11" and not environment.get("DISPLAY"):
        errors.append("DISPLAY is missing for the X11 session")
    if expected_session == "wayland" and not environment.get("WAYLAND_DISPLAY"):
        errors.append("WAYLAND_DISPLAY is missing for the Wayland session")
    return errors


def find_browser(preferred=None):
    candidates = (preferred,) if preferred else BROWSER_CANDIDATES
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    requested = preferred or ", ".join(BROWSER_CANDIDATES)
    raise RuntimeError(f"supported browser not found: {requested}")


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def process_start_time(pid):
    try:
        stat_line = Path(f"/proc/{int(pid)}/stat").read_text(encoding="utf-8")
        closing_parenthesis = stat_line.rfind(")")
        fields = stat_line[closing_parenthesis + 2:].split()
        if closing_parenthesis < 0 or fields[0] == "Z":
            return None
        return int(fields[19])
    except (IndexError, OSError, TypeError, ValueError):
        return None


def live_process_record(path, role):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict) or data.get("role") != role:
        return None
    pid = data.get("pid")
    start_time = data.get("startTime")
    if isinstance(pid, bool) or not isinstance(pid, int):
        return None
    if process_start_time(pid) != start_time:
        return None
    return data


def process_command(pid):
    """Return the exact argv for a live Linux process."""
    try:
        raw = Path(f"/proc/{int(pid)}/cmdline").read_bytes()
    except (OSError, TypeError, ValueError):
        return []
    return [
        part.decode("utf-8", errors="replace")
        for part in raw.split(b"\0")
        if part
    ]


def expected_browser_mode_flag(browser_name, launch_mode):
    """Return the browser switch that proves the requested launch mode."""
    if launch_mode == "window":
        return None
    if launch_mode == "kiosk":
        return "--kiosk"
    if launch_mode == "fullscreen":
        if Path(browser_name).name in ("firefox", "firefox-esr"):
            return "--fullscreen"
        return "--start-fullscreen"
    raise ValueError(f"unsupported launch mode: {launch_mode}")


def browser_command_ready(command, browser_name):
    """Return whether the owned PID has completed exec into its browser."""
    if not command:
        return False
    tokens = browser_command_tokens(command)
    if not tokens:
        return False
    executable = Path(tokens[0]).name.lower()
    configured = Path(browser_name).name.lower()
    if configured in ("firefox", "firefox-esr"):
        return "firefox" in executable
    return "chrome" in executable or "chromium" in executable


def browser_command_tokens(command):
    """Normalize browser argv after Chromium rewrites it as one process title."""
    return [token for argument in command for token in argument.split()]


def verify_browser_mode(command, browser_name, launch_mode):
    """Fail if the owned browser argv does not match the selected mode."""
    command = browser_command_tokens(command)
    expected = expected_browser_mode_flag(browser_name, launch_mode)
    mode_flags = {"--kiosk", "--fullscreen", "--start-fullscreen"}
    present = mode_flags.intersection(command)
    if expected is None:
        if present:
            raise RuntimeError(
                f"window mode unexpectedly uses browser flags: {sorted(present)!r}"
            )
        return "window (no fullscreen or kiosk switch)"
    if expected not in command:
        raise RuntimeError(
            f"{launch_mode} mode is missing browser switch {expected}"
        )
    unexpected = present - {expected}
    if unexpected:
        raise RuntimeError(
            f"{launch_mode} mode has conflicting browser flags: "
            f"{sorted(unexpected)!r}"
        )
    return f"{launch_mode} ({expected})"


def wait_until(predicate, timeout=30, interval=0.2, message="condition timed out"):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(interval)
    raise TimeoutError(message)


def request(url, method="GET", timeout=10):
    request_object = urllib.request.Request(url, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request_object, timeout=timeout) as response:
        body = response.read()
        return response.status, body


def write_smoke_config(config_path, browser_name):
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    config.update({
        "language": "en",
        "title": "Cozy Kids Desktop Smoke",
        "browser": browser_name,
        "pinHash": "",
        "autoScanDone": True,
        "currentPage": 0,
        "tiles": [
            {
                "id": "desktop-smoke",
                "label": "Desktop smoke app",
                "emoji": "🧪",
                "cmd": ["sleep", "20"],
                "visible": True,
            }
        ],
    })
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def validate_desktop_files(test_home):
    validator = shutil.which("desktop-file-validate")
    if not validator:
        raise RuntimeError("desktop-file-validate is required (desktop-file-utils)")
    files = (
        test_home / ".config" / "autostart" / "cozy-kids-launcher-autostart.desktop",
        test_home / ".local" / "share" / "applications" / "cozy-kids-launcher.desktop",
        test_home / "Desktop" / "Cozy Kids Launcher.desktop",
    )
    for path in files:
        if not path.is_file():
            raise RuntimeError(f"desktop integration file is missing: {path.name}")
        subprocess.run(
            [validator, str(path)],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    return [path.name for path in files]


def x11_window_titles():
    result = subprocess.run(
        ["wmctrl", "-l"],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return result.stdout


def x11_window_present(title):
    try:
        if title in x11_window_titles():
            return True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", title],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0 and bool(result.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def x11_window_ids(title):
    """Return X11 window IDs matched by title through xdotool."""
    try:
        result = subprocess.run(
            ["xdotool", "search", "--name", title],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    window_ids = []
    for value in result.stdout.splitlines():
        try:
            window_ids.append(int(value.strip(), 0))
        except ValueError:
            continue
    return window_ids


def x11_active_window_id():
    """Return the currently active X11 window ID, or None."""
    try:
        result = subprocess.run(
            ["xdotool", "getactivewindow"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return int(result.stdout.strip(), 0)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return None


def x11_window_is_active(title):
    """Return whether the active window currently matches the expected title."""
    active_window = x11_active_window_id()
    return active_window is not None and active_window in x11_window_ids(title)


def x11_click_overlay_close(window_id):
    """Click the fixed close control in the test overlay."""
    subprocess.run(
        [
            "xdotool",
            "mousemove",
            "--window",
            str(int(window_id)),
            "28",
            "32",
            "click",
            "1",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )


class SmokeReport:
    def __init__(self, desktop, session, artifacts, launch_mode="window"):
        self.path = Path(artifacts) / "report.json"
        self.data = {
            "schemaVersion": 1,
            "createdAt": utc_timestamp(),
            "expectedDesktop": desktop,
            "detectedDesktop": canonical_desktop(
                os.environ.get("XDG_CURRENT_DESKTOP", "")
            ),
            "expectedSession": session,
            "detectedSession": detected_session(),
            "launchMode": launch_mode,
            "repositoryCommit": repository_commit(),
            "distribution": distribution_identity(),
            "desktopVersion": command_version({
                "gnome": ("gnome-shell",),
                "kde": ("plasmashell",),
                "xfce": ("xfce4-session",),
            }[desktop]),
            "automatedChecks": [],
            "manualChecks": [
                {"name": name, "status": "pending"} for name in MANUAL_CHECKS
            ],
            "outcome": "running",
        }

    def pass_check(self, name, details=""):
        self.data["automatedChecks"].append({
            "name": name,
            "status": "passed",
            **({"details": details} if details else {}),
        })

    def manual_check(self, name, details=""):
        self.data["automatedChecks"].append({
            "name": name,
            "status": "manual-required",
            **({"details": details} if details else {}),
        })

    def fail(self, message):
        self.data["outcome"] = "failed"
        self.data["failure"] = str(message)[:500]
        self.write()

    def collect_manual_checks(self, input_fn=input):
        print("Record the manual checks from this disposable VM session:")
        for check in self.data["manualChecks"]:
            while True:
                answer = input_fn(f"  {check['name']} [y/n/s]: ").strip().lower()
                if answer in ("y", "yes"):
                    check["status"] = "passed"
                    break
                if answer in ("n", "no"):
                    check["status"] = "failed"
                    break
                if answer in ("s", "skip"):
                    check["status"] = "pending"
                    break
                print("Please answer y (pass), n (fail), or s (pending).")

    def complete(self):
        statuses = {check["status"] for check in self.data["manualChecks"]}
        if "failed" in statuses:
            self.data["outcome"] = "failed"
        elif statuses == {"passed"}:
            self.data["outcome"] = "passed"
        else:
            self.data["outcome"] = "automation-passed-manual-pending"
        self.write()

    def write(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )


def copy_runtime_artifacts(test_home, artifacts):
    targets = {
        test_home / ".local" / "state" / "cozy-kids-launcher" / "runtime.jsonl":
            Path(artifacts) / "runtime.jsonl",
        test_home / ".cache" / "cozy-kids-launcher" / "lifecycle.json":
            Path(artifacts) / "lifecycle.json",
    }
    for source, destination in targets.items():
        if source.is_file():
            shutil.copy2(source, destination)


def run_smoke(args, browser_path, report):
    artifacts = args.artifacts
    artifacts.mkdir(parents=True, exist_ok=True)
    browser_name = Path(browser_path).name
    launcher = None
    launcher_log = None
    with tempfile.TemporaryDirectory(prefix="cozy-kids-desktop-smoke-") as temp_dir:
        test_home = Path(temp_dir)
        environment = dict(os.environ)
        environment.update({
            "HOME": str(test_home),
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        })
        try:
            with (artifacts / "install.log").open("w", encoding="utf-8") as install_log:
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
                        args.launch_mode,
                        "--force",
                    ],
                    cwd=REPOSITORY_ROOT,
                    env=environment,
                    check=True,
                    stdout=install_log,
                    stderr=subprocess.STDOUT,
                )
            report.pass_check("isolated installer")

            desktop_files = validate_desktop_files(test_home)
            report.pass_check("desktop and autostart files", ", ".join(desktop_files))

            config_path = test_home / ".config" / "cozy-kids-launcher" / "config.json"
            write_smoke_config(config_path, browser_name)
            app_root = test_home / ".local" / "share" / "cozy-kids-launcher"
            runtime = test_home / ".local" / "bin" / "cozy-kids-launcher"
            cache = test_home / ".cache" / "cozy-kids-launcher"
            version = (app_root / "version").read_text(encoding="utf-8").strip()
            report.data["appVersion"] = version
            report.data["browser"] = browser_name
            report.data["browserVersion"] = command_version((browser_name,))
            port = available_port()
            environment["COZY_KIDS_PORT"] = str(port)

            launcher_log = (artifacts / "launcher.log").open("w", encoding="utf-8")
            launcher = subprocess.Popen(
                [str(runtime)],
                env=environment,
                stdout=launcher_log,
                stderr=subprocess.STDOUT,
            )
            base_url = f"http://127.0.0.1:{port}"
            wait_until(
                lambda: _server_ready(base_url, launcher),
                timeout=45,
                message="launcher server did not become ready",
            )
            browser_record = wait_until(
                lambda: live_process_record(cache / "browser.pid", "browser"),
                timeout=30,
                message="owned launcher browser did not start",
            )
            report.pass_check(
                "launcher server and owned browser",
                f"browser pid {browser_record['pid']}",
            )
            browser_command = wait_until(
                lambda: (
                    command
                    if browser_command_ready(command, browser_name)
                    else None
                )
                if (command := process_command(browser_record["pid"]))
                else None,
                timeout=30,
                message="owned PID did not exec into the configured browser",
            )
            mode_details = verify_browser_mode(
                browser_command,
                browser_name,
                args.launch_mode,
            )
            report.pass_check("browser launch mode", mode_details)

            second = subprocess.run(
                [str(runtime)],
                env=environment,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            if second.returncode != 0:
                raise RuntimeError("second launcher invocation did not exit cleanly")
            current_record = live_process_record(cache / "browser.pid", "browser")
            if not current_record or current_record["pid"] != browser_record["pid"]:
                raise RuntimeError("second launcher invocation replaced the active browser")
            report.pass_check("single-instance lock")

            if args.session == "x11":
                for command in ("wmctrl", "xdotool"):
                    if not shutil.which(command):
                        raise RuntimeError(f"{command} is required for X11 window checks")
                wait_until(
                    lambda: x11_window_present("Cozy Kids Launcher"),
                    timeout=20,
                    message="launcher window is not visible to the X11 window manager",
                )
                report.pass_check("X11 launcher window visibility")
            else:
                report.manual_check(
                    "Wayland launcher window visibility",
                    "compositor-wide window enumeration is intentionally unavailable",
                )

            status, _ = request(f"{base_url}/launch/desktop-smoke", method="POST")
            if status != 204:
                raise RuntimeError(f"tile launch returned HTTP {status}")
            wait_until(
                lambda: live_process_record(
                    cache / "tile-process.pid",
                    "tile-process",
                ),
                timeout=15,
                message="owned tile supervisor did not start",
            )
            wait_until(
                lambda: live_process_record(cache / "overlay.pid", "overlay"),
                timeout=15,
                message="app overlay did not start",
            )
            report.pass_check("owned child process and overlay")
            if args.session == "x11":
                wait_until(
                    lambda: x11_window_present("App Overlay"),
                    timeout=15,
                    message="app overlay is not visible to the X11 window manager",
                )
                report.pass_check("X11 overlay window visibility")
                wait_until(
                    lambda: x11_window_ids("Cozy Kids Launcher"),
                    timeout=15,
                    message="launcher window ID is unavailable",
                )
                overlay_windows = wait_until(
                    lambda: x11_window_ids("App Overlay"),
                    timeout=15,
                    message="overlay window ID is unavailable",
                )
                x11_click_overlay_close(overlay_windows[-1])
                wait_until(
                    lambda: not live_process_record(
                        cache / "tile-process.pid",
                        "tile-process",
                    ),
                    timeout=15,
                    message="overlay close did not stop the owned tile",
                )
                wait_until(
                    lambda: x11_window_is_active("Cozy Kids Launcher"),
                    timeout=15,
                    message="overlay close did not restore launcher focus",
                )
                report.pass_check("X11 overlay close and launcher focus recovery")
            else:
                report.manual_check(
                    "Wayland overlay stacking and focus",
                    "verify visually in the compositor",
                )

            status, _ = request(f"{base_url}/exit-kids", method="POST")
            if status != 204:
                raise RuntimeError(f"parent exit returned HTTP {status}")
            launcher.wait(timeout=20)
            if launcher.returncode != 0:
                raise RuntimeError(f"launcher exited with {launcher.returncode}")
            launcher = None
            for filename, role in (
                ("server.pid", "server"),
                ("browser.pid", "browser"),
                ("tile-process.pid", "tile-process"),
                ("overlay.pid", "overlay"),
                ("watchdog.pid", "watchdog"),
            ):
                if live_process_record(cache / filename, role):
                    raise RuntimeError(f"owned {role} process survived launcher exit")
            lifecycle = json.loads(
                (cache / "lifecycle.json").read_text(encoding="utf-8")
            )
            if lifecycle.get("state") != "stopped" or lifecycle.get("reason") != "parent-exit":
                raise RuntimeError(f"unexpected final lifecycle state: {lifecycle!r}")
            report.pass_check("clean parent exit and process cleanup")
            copy_runtime_artifacts(test_home, artifacts)
        finally:
            if launcher and launcher.poll() is None:
                try:
                    request(f"http://127.0.0.1:{environment['COZY_KIDS_PORT']}/exit-kids", method="POST")
                    launcher.wait(timeout=10)
                except Exception:
                    launcher.terminate()
                    try:
                        launcher.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        launcher.kill()
                        launcher.wait(timeout=5)
            if launcher_log:
                launcher_log.close()
            copy_runtime_artifacts(test_home, artifacts)


def _server_ready(base_url, process):
    if process.poll() is not None:
        raise RuntimeError(f"launcher exited before server readiness ({process.returncode})")
    try:
        status, body = request(f"{base_url}/api/config", timeout=3)
        return status == 200 and isinstance(json.loads(body), dict)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--desktop", choices=tuple(DESKTOP_ALIASES), required=True)
    parser.add_argument("--session", choices=("x11", "wayland"), required=True)
    parser.add_argument("--browser", help="Browser executable name")
    parser.add_argument(
        "--launch-mode",
        choices=("window", "fullscreen", "kiosk"),
        default="window",
        help="Installed browser launch mode to verify (default: window)",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Record the six manual VM observations in the JSON report",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        help=(
            "Output directory (default: .test-artifacts/desktop-matrix/"
            "<desktop>-<session>-<launch-mode>)"
        ),
    )
    args = parser.parse_args()
    args.artifacts = args.artifacts or (
        REPOSITORY_ROOT
        / ".test-artifacts"
        / "desktop-matrix"
        / f"{args.desktop}-{args.session}-{args.launch_mode}"
    )

    errors = environment_errors(args.desktop, args.session)
    if errors:
        raise SystemExit("Desktop smoke refused:\n- " + "\n- ".join(errors))
    if not shutil.which("bash") or not shutil.which("python3"):
        raise SystemExit("Desktop smoke requires bash and python3")
    tkinter = subprocess.run(
        ["python3", "-c", "import tkinter"],
        capture_output=True,
        check=False,
    )
    if tkinter.returncode != 0:
        raise SystemExit("Desktop smoke requires Python Tk support (python3-tk)")
    try:
        browser_path = find_browser(args.browser)
    except RuntimeError as exc:
        raise SystemExit(str(exc)) from exc

    report = SmokeReport(
        args.desktop,
        args.session,
        args.artifacts,
        launch_mode=args.launch_mode,
    )
    print(
        f"Desktop smoke: {args.desktop}/{args.session} with {browser_path}",
        flush=True,
    )
    try:
        run_smoke(args, browser_path, report)
    except Exception as exc:
        report.fail(exc)
        print(f"Desktop smoke failed: {exc}", flush=True)
        print(f"Report: {report.path}", flush=True)
        raise SystemExit(1) from exc
    if args.interactive:
        report.collect_manual_checks()
    report.complete()
    if report.data["outcome"] == "failed":
        print("Desktop automation passed, but a manual check failed.", flush=True)
        print(f"Report: {report.path}", flush=True)
        raise SystemExit(1)
    if report.data["outcome"] == "passed":
        print("Desktop smoke passed, including all manual VM checks.", flush=True)
    else:
        print("Desktop automation passed; complete the six manual VM checks.", flush=True)
    print(f"Report: {report.path}", flush=True)


if __name__ == "__main__":
    main()
