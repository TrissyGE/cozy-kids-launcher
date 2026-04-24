#!/usr/bin/env python3
import glob
import hashlib
import http.server
import json
import os
import re
import subprocess
from urllib.parse import unquote

HOME = os.path.expanduser("~")
APP_ROOT = os.path.join(HOME, ".local", "share", "{{APP_ID}}")
CFG = os.path.join(HOME, ".config", "{{APP_ID}}", "config.json")
PORT = int(os.environ.get("COZY_KIDS_PORT", "{{DEFAULT_PORT}}"))
PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "server.pid")
BROWSER_PIDFILE = os.path.join(HOME, ".cache", "{{APP_ID}}", "browser.pid")
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


def verify_pin(pin_hash, pin):
    if not pin_hash or not pin:
        return False
    computed = hashlib.sha256(pin.encode("utf-8")).hexdigest()[:16]
    return computed == pin_hash


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=APP_ROOT, **kwargs)

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
