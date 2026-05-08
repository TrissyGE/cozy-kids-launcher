#!/usr/bin/env python3
import glob
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from urllib.parse import unquote

HOME = os.path.expanduser("~")
APP_ROOT = os.path.join(HOME, ".local", "share", "{{APP_ID}}")
VERSION_FILE = os.path.join(APP_ROOT, "version")
CFG = os.path.join(HOME, ".config", "{{APP_ID}}", "config.json")
PORT = int(os.environ.get("COZY_KIDS_PORT", "{{DEFAULT_PORT}}"))
PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "server.pid")
BROWSER_PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "browser.pid")
EXTERNAL_BROWSER_PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "external-browser.pid")
EXIT_FLAGFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "exit-requested")
RECOMMENDATIONS_FILE = os.path.join(APP_ROOT, "recommendations.json")
VIDEOS = os.path.join(HOME, "Videos")
MUSIC = os.path.join(HOME, "Music")
ALT_MUSIC = os.path.join(HOME, "Musik")
EXTS = ("*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.mp3", "*.ogg", "*.wav", "*.flac", "*.m4a")
TIMER_FILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "timer.json")


def has_media(path):
    if not os.path.isdir(path):
        return False
    for ext in EXTS:
        if glob.glob(os.path.join(path, "**", ext), recursive=True):
            return True
    return False


def load_cfg():
    with open(CFG, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    migrated = False
    recs = load_recommendations()
    rec_by_first_cmd = {}
    for rec in recs:
        if rec.get("cmd"):
            rec_by_first_cmd[rec["cmd"][0]] = rec["cmd"]
        for alt in rec.get("alt_cmds", []):
            rec_by_first_cmd[alt] = rec["cmd"]
    for tile in data.get("tiles", []):
        cmd = tile.get("cmd", [])
        if cmd and len(cmd) >= 1 and cmd[0] in rec_by_first_cmd and cmd != rec_by_first_cmd[cmd[0]]:
            tile["cmd"] = rec_by_first_cmd[cmd[0]]
            migrated = True
    if "autoScanDone" not in data:
        data["autoScanDone"] = True
        migrated = True
    if migrated:
        save_cfg(data)
    return data


def save_cfg(data):
    with open(CFG, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def parse_desktop_file(path):
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            txt = fh.read()
    except Exception:
        return None
    if "NoDisplay=true" in txt:
        return None
    if "TryExec=" in txt:
        for line in txt.splitlines():
            if line.startswith("TryExec="):
                try_cmd = line[8:].strip().split()[0]
                if not any(os.path.exists(os.path.join(p, try_cmd)) for p in os.environ.get("PATH", "/usr/bin").split(":")):
                    if not os.path.isabs(try_cmd) or not os.path.exists(try_cmd):
                        return None
                break

    app_name = None
    exec_cmd = None
    for line in txt.splitlines():
        if line.startswith("Name=") and app_name is None:
            app_name = line[5:].strip()
        elif line.startswith("Exec=") and exec_cmd is None:
            exec_cmd = line[5:].strip()
    if not app_name or not exec_cmd:
        return None
    # Strip field codes like %U %F %u %f %c %i %m %k %v %d %D %n %N %t %T %r %R
    clean_exec = re.sub(r'%[UuFfCcIiMmKkVvDdNnTtRr]', '', exec_cmd).strip()
    if not clean_exec:
        return None
    return {"name": app_name, "exec": clean_exec}


def scan_apps():
    apps = []
    seen = set()
    bases = [
        os.path.join(HOME, ".local/share/applications"),
        "/usr/share/applications",
        "/var/lib/snapd/desktop/applications",
    ]
    for base in bases:
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if not name.endswith(".desktop"):
                continue
            path = os.path.join(base, name)
            app = parse_desktop_file(path)
            if not app:
                continue
            if app["exec"] in seen:
                continue
            seen.add(app["exec"])
            apps.append(app)
    return apps[:300]


def media_location():
    if has_media(VIDEOS):
        return VIDEOS
    if has_media(MUSIC):
        return MUSIC
    if has_media(ALT_MUSIC):
        return ALT_MUSIC
    return None


def get_version():
    try:
        with open(VERSION_FILE, "r", encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return "0.0.0"


def load_recommendations():
    if not os.path.isfile(RECOMMENDATIONS_FILE):
        return []
    try:
        with open(RECOMMENDATIONS_FILE, "r", encoding="utf-8") as fh:
            recs = json.load(fh)
    except Exception:
        return []
    result = []
    for rec in recs:
        all_cmds = []
        cmd = rec.get("cmd", [])
        # KDE wrapper detection: kstart/kstart5 are wrappers, not the app itself
        is_wrapper = cmd and cmd[0] in ("kstart", "kstart5")
        if is_wrapper:
            # Only check alt_cmds or the actual app name (skip wrapper and --fullscreen)
            for alt in rec.get("alt_cmds", []):
                all_cmds.append(alt)
            for part in cmd[2:]:
                if part and not part.startswith("-"):
                    all_cmds.append(part)
        else:
            if cmd:
                all_cmds.append(cmd[0])
            for alt in rec.get("alt_cmds", []):
                all_cmds.append(alt)
        installed = any(shutil.which(c) for c in all_cmds if c)
        if not installed and rec.get("category") == "browser":
            installed = True
        result.append({**rec, "installed": installed})
    return result


def verify_pin(pin_hash, pin):
    if not pin_hash or not pin:
        return False
    computed = hashlib.sha256(pin.encode("utf-8")).hexdigest()[:16]
    return computed == pin_hash


def load_timer():
    if not os.path.isfile(TIMER_FILE):
        return None
    try:
        with open(TIMER_FILE, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def save_timer(data):
    os.makedirs(os.path.dirname(TIMER_FILE), exist_ok=True)
    with open(TIMER_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def clear_timer():
    try:
        if os.path.isfile(TIMER_FILE):
            os.remove(TIMER_FILE)
    except Exception:
        pass


def timer_status(cfg):
    data = load_timer()
    if not data or not isinstance(data, dict):
        return {"active": False, "expired": False, "warning": False, "remainingSeconds": 0, "totalMinutes": 0}
    end_time = data.get("end_time", 0)
    total_minutes = data.get("totalMinutes", 0)
    warning_minutes = cfg.get("timerWarningMinutes", 5)
    now = time.time()
    remaining = int(end_time - now)
    if remaining <= 0:
        return {"active": True, "expired": True, "warning": False, "remainingSeconds": 0, "totalMinutes": total_minutes}
    warning_seconds = warning_minutes * 60
    return {
        "active": True,
        "expired": False,
        "warning": remaining <= warning_seconds,
        "remainingSeconds": remaining,
        "totalMinutes": total_minutes,
    }


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_ROOT, **kwargs)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def json_response(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/api/config":
            return self.json_response(load_cfg())
        if self.path == "/api/apps":
            return self.json_response(scan_apps())
        if self.path == "/api/recommendations":
            return self.json_response(load_recommendations())
        if self.path == "/api/version":
            return self.json_response({"version": get_version()})
        if self.path == "/api/features":
            shutdown_ok = bool(
                shutil.which("systemctl") or shutil.which("loginctl")
            )
            return self.json_response({"shutdownAvailable": shutdown_ok})
        if self.path == "/api/browsers":
            candidates = [
                "firefox", "firefox-esr", "librewolf",
                "chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
                "brave", "brave-browser", "opera", "opera-stable",
                "vivaldi", "vivaldi-stable", "microsoft-edge", "microsoft-edge-stable",
                "edge", "cachy-browser"
            ]
            return self.json_response([
                {"name": b, "installed": bool(shutil.which(b))} for b in candidates
            ])
        if self.path == "/api/timer/status":
            return self.json_response(timer_status(load_cfg()))
        if self.path == "/api/export-config":
            data = load_cfg()
            payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="cozy-kids-config.json"')
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        return super().do_GET()

    def do_POST(self):
        action = self.path.strip("/")
        if action == "api/save-config":
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            data = json.loads(raw.decode("utf-8"))
            save_cfg(data)
            browser = data.get("browser", "")
            if browser:
                try:
                    browser_file = os.path.join(os.path.dirname(CFG), "browser")
                    with open(browser_file, "w", encoding="utf-8") as f:
                        f.write(browser)
                except Exception:
                    pass
            self.send_response(204)
            self.end_headers()
            return
        if action == "api/verify-pin":
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            data = json.loads(raw.decode("utf-8"))
            cfg = load_cfg()
            pin_hash = cfg.get("pinHash", "")
            if not pin_hash:
                self.json_response({"valid": True})
                return
            pin = data.get("pin", "")
            self.json_response({"valid": verify_pin(pin_hash, pin)})
            return
        if action == "api/import-config":
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            data = json.loads(raw.decode("utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("tiles"), list):
                self.json_response({"status": "error", "message": "Invalid config format"}, 400)
                return
            save_cfg(data)
            self.json_response({"status": "ok"})
            return
        if action == "shutdown":
            shutdown_ok = False
            for cmd in (["systemctl", "poweroff"], ["loginctl", "poweroff"]):
                if shutil.which(cmd[0]):
                    try:
                        subprocess.Popen(cmd, env=dict(os.environ))
                        shutdown_ok = True
                        break
                    except Exception:
                        pass
            self.json_response({"status": "ok" if shutdown_ok else "error"})
            return
        if action == "exit-kids":
            # Signal launcher.sh to exit its while-true loop
            try:
                with open(EXIT_FLAGFILE, "w", encoding="utf-8") as f:
                    f.write("1")
            except Exception:
                pass
            if os.path.isfile(BROWSER_PIDFILE):
                try:
                    with open(BROWSER_PIDFILE, "r", encoding="utf-8") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, 15)
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
            self.send_response(204)
            self.end_headers()
            # Shutdown the HTTP server so launcher.sh exits cleanly
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if action == "api/timer/start":
            cfg = load_cfg()
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw.decode("utf-8")) if raw else {}
            pin_hash = cfg.get("pinHash", "")
            if pin_hash and not verify_pin(pin_hash, body.get("pin", "")):
                self.json_response({"valid": False, "message": "Invalid PIN"}, 403)
                return
            minutes = body.get("minutes", cfg.get("timerMinutes", 0))
            if minutes <= 0:
                self.json_response({"valid": False, "message": "Invalid duration"}, 400)
                return
            end_time = int(time.time()) + minutes * 60
            save_timer({"end_time": end_time, "totalMinutes": minutes})
            self.json_response({"valid": True, "endTime": end_time, "minutes": minutes})
            return
        if action == "api/timer/stop":
            cfg = load_cfg()
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw.decode("utf-8")) if raw else {}
            pin_hash = cfg.get("pinHash", "")
            if pin_hash and not verify_pin(pin_hash, body.get("pin", "")):
                self.json_response({"valid": False, "message": "Invalid PIN"}, 403)
                return
            clear_timer()
            self.json_response({"valid": True})
            return
        if action == "api/timer/extend":
            cfg = load_cfg()
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            body = json.loads(raw.decode("utf-8")) if raw else {}
            pin_hash = cfg.get("pinHash", "")
            if pin_hash and not verify_pin(pin_hash, body.get("pin", "")):
                self.json_response({"valid": False, "message": "Invalid PIN"}, 403)
                return
            minutes = body.get("minutes", 15)
            if minutes <= 0:
                self.json_response({"valid": False, "message": "Invalid duration"}, 400)
                return
            end_time = int(time.time()) + minutes * 60
            save_timer({"end_time": end_time, "totalMinutes": minutes})
            self.json_response({"valid": True, "endTime": end_time, "minutes": minutes})
            return
        if action == "api/update":
            trigger_path = os.path.join(APP_ROOT, "update-trigger.sh")
            trigger_script = """#!/usr/bin/env bash
set -euo pipefail
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT
REPO="TrissyGE/cozy-kids-launcher"
APP_ID="cozy-kids-launcher"
if command -v curl >/dev/null 2>&1; then
  curl -fsSL -o "$TMP_DIR/cozy.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP_DIR/cozy.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
else
  exit 1
fi
unzip -q "$TMP_DIR/cozy.zip" -d "$TMP_DIR/"
REPO_DIR="$TMP_DIR/cozy-kids-launcher-main"
if [[ -f "$HOME/.config/$APP_ID/config.json" ]]; then
  cp "$HOME/.config/$APP_ID/config.json" "$TMP_DIR/config-backup.json"
fi
cd "$REPO_DIR"
bash scripts/install.sh --user "$(id -un)" --force
if [[ -f "$TMP_DIR/config-backup.json" ]]; then
  cp "$TMP_DIR/config-backup.json" "$HOME/.config/$APP_ID/config.json"
fi
"""
            try:
                with open(trigger_path, "w", encoding="utf-8") as fh:
                    fh.write(trigger_script)
                os.chmod(trigger_path, 0o755)
                # Execute after a short delay so the browser can exit first
                subprocess.Popen(
                    ["bash", "-c", "sleep 3 && bash '" + trigger_path + "'"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                self.json_response({"status": "triggered"})
            except Exception as e:
                self.json_response({"status": "error", "message": str(e)}, 500)
            return
        if action == "api/install-package":
            raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
            data = json.loads(raw.decode("utf-8"))
            package = data.get("package", "")
            recs = load_recommendations()
            valid_packages = {r["package"] for r in recs if r.get("package")}
            if not package or package not in valid_packages:
                self.json_response({"status": "error", "message": "Invalid package"}, 400)
                return
            command = f"sudo apt install -y {package}"
            self.json_response({"status": "manual", "command": command})
            return
        if action.startswith("launch/"):
            tile_id = unquote(action.split("/", 1)[1])
            if not tile_id or not re.match(r"^[A-Za-z0-9_-]+$", tile_id):
                self.send_response(400)
                self.end_headers()
                return
            cfg = load_cfg()
            tile = next((t for t in cfg.get("tiles", []) if t.get("id") == tile_id and t.get("visible", True)), None)
            if not tile:
                self.send_response(404)
                self.end_headers()
                return
            cmd = tile.get("cmd", [])
            # Kill any existing overlay so only one runs at a time
            try:
                result = subprocess.run(["pgrep", "-f", "overlay.py"], capture_output=True, text=True)
                for pid_str in result.stdout.strip().split("\n"):
                    if pid_str:
                        try:
                            os.kill(int(pid_str), 15)
                        except Exception:
                            pass
            except Exception:
                pass
            if cmd == ["special:filme-musik"]:
                location = media_location()
                if location:
                    subprocess.Popen(["xdg-open", location], env=dict(os.environ))
                    self.send_response(204)
                else:
                    self.send_response(302)
                    self.send_header("Location", "/no-media.html")
                self.end_headers()
                return
            if cmd and len(cmd) == 1 and cmd[0].startswith("special:browser:"):
                url = cmd[0][len("special:browser:"):]
                self.send_response(302)
                self.send_header("Location", f"/browser.html?url={url}")
                self.end_headers()
                return
            if cmd and len(cmd) == 1 and cmd[0].startswith("special:external-browser:"):
                url = cmd[0][len("special:external-browser:"):]
                external_browser = None
                for candidate in ["chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "brave", "brave-browser", "microsoft-edge", "microsoft-edge-stable", "vivaldi", "vivaldi-stable", "opera", "opera-stable"]:
                    if shutil.which(candidate):
                        external_browser = candidate
                        break
                if external_browser:
                    proc = subprocess.Popen([external_browser, f"--app={url}", "--kiosk", "--no-first-run", "--disable-session-crashed-bubble"], env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    try:
                        with open(EXTERNAL_BROWSER_PIDFILE, "w", encoding="utf-8") as f:
                            f.write(str(proc.pid))
                    except Exception:
                        pass
                    overlay_script = os.path.join(APP_ROOT, "overlay.py")
                    if os.path.isfile(overlay_script):
                        subprocess.Popen([sys.executable, overlay_script, "--mode", "external", "--url", url, "--label", "Home", "--browser-pid", str(proc.pid)], env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    subprocess.Popen(["xdg-open", url], env=dict(os.environ))
                self.send_response(204)
                self.end_headers()
                return
            clean = [part for part in cmd if part]
            if not clean:
                self.send_response(204)
                self.end_headers()
                return
            # KDE wrapper fallback: if kstart5/kstart is missing, drop it and launch directly
            if len(clean) >= 3 and clean[0] in ("kstart5", "kstart") and clean[1] == "--fullscreen":
                if not shutil.which(clean[0]):
                    clean = clean[2:]
            # Determine primary app command for overlay tracking
            app_cmd = ""
            if len(clean) == 1:
                parts = clean[0].split()
                app_cmd = parts[0] if parts else ""
            elif len(clean) >= 3 and clean[0] in ("kstart5", "kstart") and clean[1] == "--fullscreen":
                app_cmd = clean[2] if len(clean) > 2 else ""
            else:
                app_cmd = clean[0] if clean else ""

            # Avoid shell=True to prevent command injection from user-editable configs
            if len(clean) == 1:
                parts = clean[0].split()
                subprocess.Popen(parts, env=dict(os.environ))
            else:
                subprocess.Popen(clean, env=dict(os.environ))

            # Start overlay for local apps so the child can close them and see the timer
            overlay_script = os.path.join(APP_ROOT, "overlay.py")
            if os.path.isfile(overlay_script) and app_cmd:
                subprocess.Popen([sys.executable, overlay_script, "--mode", "local", "--app-cmd", app_cmd, "--label", "Home"], env=dict(os.environ), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            self.send_response(204)
            self.end_headers()
            return
        self.send_response(404)
        self.end_headers()


with http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Handler) as httpd:
    os.makedirs(os.path.dirname(PIDFILE), exist_ok=True)
    with open(PIDFILE, "w", encoding="utf-8") as fh:
        fh.write(str(os.getpid()))
    httpd.serve_forever()
