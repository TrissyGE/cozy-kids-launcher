#!/usr/bin/env python3
import glob
import hashlib
import http.server
import json
import os
import re
import shutil
import subprocess
from urllib.parse import unquote

HOME = os.path.expanduser("~")
APP_ROOT = os.path.join(HOME, ".local", "share", "{{APP_ID}}")
VERSION_FILE = os.path.join(APP_ROOT, "version")
CFG = os.path.join(HOME, ".config", "{{APP_ID}}", "config.json")
PORT = int(os.environ.get("COZY_KIDS_PORT", "{{DEFAULT_PORT}}"))
PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "server.pid")
BROWSER_PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "browser.pid")
RECOMMENDATIONS_FILE = os.path.join(APP_ROOT, "recommendations.json")
VIDEOS = os.path.join(HOME, "Videos")
MUSIC = os.path.join(HOME, "Music")
ALT_MUSIC = os.path.join(HOME, "Musik")
EXTS = ("*.mp4", "*.mkv", "*.webm", "*.avi", "*.mov", "*.mp3", "*.ogg", "*.wav", "*.flac", "*.m4a")


def has_media(path):
    if not os.path.isdir(path):
        return False
    for ext in EXTS:
        if glob.glob(os.path.join(path, "**", ext), recursive=True):
            return True
    return False


def load_cfg():
    with open(CFG, "r", encoding="utf-8") as fh:
        return json.load(fh)


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
        if rec.get("cmd"):
            all_cmds.append(rec["cmd"][0])
        for alt in rec.get("alt_cmds", []):
            all_cmds.append(alt)
        installed = any(shutil.which(c) for c in all_cmds if c)
        result.append({**rec, "installed": installed})
    return result


def verify_pin(pin_hash, pin):
    if not pin_hash or not pin:
        return False
    computed = hashlib.sha256(pin.encode("utf-8")).hexdigest()[:16]
    return computed == pin_hash


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
            save_cfg(json.loads(raw.decode("utf-8")))
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
            if os.environ.get("COZY_KIDS_ENABLE_SHUTDOWN") == "1":
                subprocess.Popen(["systemctl", "poweroff"], env=dict(os.environ))
            self.send_response(204)
            self.end_headers()
            return
        if action == "exit-kids":
            if os.path.isfile(BROWSER_PIDFILE):
                try:
                    with open(BROWSER_PIDFILE, "r", encoding="utf-8") as f:
                        pid = int(f.read().strip())
                    os.kill(pid, 15)
                except (ValueError, ProcessLookupError, PermissionError):
                    pass
            self.send_response(204)
            self.end_headers()
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
            clean = [part for part in cmd if part]
            if not clean:
                self.send_response(204)
                self.end_headers()
                return
            # Avoid shell=True whenever possible
            if len(clean) == 1:
                parts = clean[0].split()
                if len(parts) == 1 and not any(c in parts[0] for c in ";&|<>$`\n"):
                    subprocess.Popen(parts, env=dict(os.environ))
                else:
                    subprocess.Popen(clean[0], env=dict(os.environ), shell=True)
            else:
                subprocess.Popen(clean, env=dict(os.environ))
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
