#!/usr/bin/env python3
import json
import os
import subprocess
import time
import tempfile
import shutil

HOME = os.path.expanduser("~")
REPO = os.path.join(HOME, "cozy-kids-launcher")
SHOTS = os.path.join(REPO, "screenshots")

ENGLISH_UI_TEXT = '''const uiText = {
  adminTitle: "Parent Settings",
  placeholderTitle: "Title",
  placeholderParentLabel: "Parent button",
  placeholderExitLabel: "Exit button",
  addTile: "Add tile",
  back: "Back",
  save: "Save",
  visible: "visible",
  specialMedia: "Special: Movies & Music",
  noApp: "No app",
  customCmd: "Custom",
  moveUp: "Up",
  moveDown: "Down",
  delete: "Delete",
  newTile: "New tile",
  pinTitle: "Enter PIN",
  pinPlaceholder: "4-6 digits",
  pinWrong: "Wrong PIN",
  pinSet: "Set PIN",
  pinChange: "Change PIN",
  pinRemove: "Remove PIN",
  pinConfirm: "Repeat",
  pinMismatch: "PINs do not match",
  pinSaved: "PIN saved",
  pinRemoved: "PIN removed",
  adminPagePrev: "← Previous",
  adminPageNext: "Next →",
  updateCheck: "Check for updates",
  updateAvailable: "Update available",
  updateUpToDate: "Up to date",
  updateError: "Update check failed",
  versionLabel: "Version",
  updateNow: "Update now",
  updateProgress: "Installing update... please wait",
  updateConfirm: "Browser will close and update will be installed. Continue?",
  recommendedTitle: "Recommended apps",
  appBrowserTitle: "App Browser",
  install: "Install",
  added: "Added",
  installed: "installed",
  notInstalled: "not installed",
  copyCommand: "Copy",
  commandCopied: "Copied!",
  installStarted: "Installation started. Watch for a password dialog, or run the command below:",
  installManual: "Please run this command in a terminal:",
  close: "Close"
};'''

def kill_firefox():
    subprocess.run(["pkill", "-9", "-f", "firefox"], capture_output=True)
    time.sleep(1)

def screenshot(url, path, window_size="1280,800"):
    profile_dir = tempfile.mkdtemp(prefix="fx-screenshot-")
    kill_firefox()
    cmd = [
        "firefox", "--headless", "--profile", profile_dir,
        "--window-size", window_size,
        "--screenshot", path, url
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(25):
        time.sleep(1)
        if os.path.exists(path) and os.path.getsize(path) > 5000:
            break
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.terminate()
    time.sleep(1)
    shutil.rmtree(profile_dir, ignore_errors=True)

def make_html(path, theme="rosa", admin_mode=False):
    # Fetch current HTML from running server
    result = subprocess.run(
        ["curl", "-s", "http://localhost:38431/"],
        capture_output=True, text=True
    )
    html = result.stdout

    if not html or "<!doctype html>" not in html.lower():
        raise RuntimeError("Failed to fetch launcher HTML from server")

    # Replace German uiText with English
    start = html.find("const uiText = {")
    end = html.find("function pageSize()")
    if start != -1 and end != -1:
        html = html[:start] + ENGLISH_UI_TEXT + "\n" + html[end:]

    # Replace fallback strings
    html = html.replace("'Hallo Kiddo 🌈'", "'Hello Kiddo 🌈'")
    html = html.replace("'Papa'", "'Parent'")
    html = html.replace("'Zurück'", "'Back'")
    html = html.replace("'Kindermodus beenden'", "'Exit Kids Mode'")
    html = html.replace("'Ausschalten'", "'Shut down'")
    html = html.replace("textContent=uiText.back||'Zurück'", "textContent=uiText.back||'Back'")

    # Build embedded config
    config = {
        "language": "en",
        "title": "Hello Kiddo 🌈",
        "theme": theme,
        "layoutMode": "gross",
        "parentLabel": "Parent",
        "exitLabel": "Exit Kids Mode",
        "shutdownLabel": "Shut down",
        "pinHash": "",
        "currentPage": 0,
        "tiles": [
            {"id": "paint", "label": "Paint", "emoji": "🎨", "cmd": ["tuxpaint"], "visible": True},
            {"id": "games", "label": "Learning games", "emoji": "🧩", "cmd": ["gcompris-qt"], "visible": True},
            {"id": "music", "label": "Movies & Music", "emoji": "🎵", "cmd": ["special:filme-musik"], "visible": True},
            {"id": "math", "label": "Math", "emoji": "🧮", "cmd": ["tuxmath"], "visible": True},
            {"id": "typing", "label": "Typing", "emoji": "⌨️", "cmd": ["tuxtype"], "visible": False},
            {"id": "browser", "label": "Kids Web", "emoji": "🌐", "cmd": ["xdg-open", "https://www.fragfinn.de/"], "visible": False}
        ]
    }
    config_json = json.dumps(config, ensure_ascii=False)

    # Replace loadConfig to use embedded config instead of fetch
    old_load = "async function loadConfig(){ cfg=await fetch('/api/config').then(r=>r.json());"
    new_load = f"async function loadConfig(){{ cfg={config_json};"
    html = html.replace(old_load, new_load)

    # Also replace loadApps to avoid fetch errors for file:// URLs
    old_apps = "async function loadApps(){ appOptions=await fetch('/api/apps').then(r=>r.json()); }"
    new_apps = "async function loadApps(){ appOptions=[{name:'Tux Paint',exec:'tuxpaint'},{name:'GCompris',exec:'gcompris-qt'},{name:'TuxMath',exec:'tuxmath'},{name:'TuxType',exec:'tuxtype'}]; }"
    html = html.replace(old_apps, new_apps)

    # Replace loadRecommendations
    old_rec = "async function loadRecommendations(){ try{ const r=await fetch('/api/recommendations'); recommendations=await r.json(); }catch(e){ recommendations=[]; } }"
    new_rec = "async function loadRecommendations(){ recommendations=[]; }"
    html = html.replace(old_rec, new_rec)

    if admin_mode:
        # Swap visibility: hide kids, show admin by default
        html = html.replace('id="kids" class="screen"', 'id="kids" class="screen hidden"')
        html = html.replace('id="admin" class="screen hidden"', 'id="admin" class="screen"')

    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

def main():
    os.makedirs(SHOTS, exist_ok=True)
    tmpdir = tempfile.mkdtemp(prefix="ckl-screenshots-")
    try:
        print("Creating home screen HTML...")
        home_html = os.path.join(tmpdir, "home.html")
        make_html(home_html, theme="rosa", admin_mode=False)

        print("Taking screenshot: home screen...")
        screenshot(
            "file://" + home_html,
            os.path.join(SHOTS, "screenshot-home.png")
        )

        print("Creating admin settings HTML...")
        admin_html = os.path.join(tmpdir, "admin.html")
        make_html(admin_html, theme="rosa", admin_mode=True)

        print("Taking screenshot: admin settings...")
        screenshot(
            "file://" + admin_html,
            os.path.join(SHOTS, "screenshot-parent-settings.png")
        )

        print("Creating blue theme HTML...")
        blue_html = os.path.join(tmpdir, "blue.html")
        make_html(blue_html, theme="blau", admin_mode=False)

        print("Taking screenshot: blue theme...")
        screenshot(
            "file://" + blue_html,
            os.path.join(SHOTS, "screenshot-theme-blue.png")
        )

        print("Done! Screenshots saved to", SHOTS)
    finally:
        kill_firefox()
        shutil.rmtree(tmpdir, ignore_errors=True)

if __name__ == "__main__":
    main()
