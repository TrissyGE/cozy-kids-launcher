#!/usr/bin/env python3
"""
Screenshot generator for Cozy Kids Launcher GitHub page.

This script temporarily modifies the installed launcher files to English,
takes screenshots via Firefox headless, then restores the originals.

Requirements: Firefox installed and the launcher server running on localhost:38431.
"""
import json
import os
import shutil
import subprocess
import time
import tempfile

HOME = os.path.expanduser("~")
APP_ROOT = os.path.join(HOME, ".local", "share", "cozy-kids-launcher")
INDEX = os.path.join(APP_ROOT, "index.html")
CFG = os.path.join(HOME, ".config", "cozy-kids-launcher", "config.json")
REPO = os.path.join(HOME, "cozy-kids-launcher")
SHOTS = os.path.join(REPO, "screenshots")

INDEX_BAK = INDEX + ".bak-screenshot"
CFG_BAK = CFG + ".bak-screenshot"

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
  adminPagePrev: "<- Previous",
  adminPageNext: "Next ->",
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


def backup():
    shutil.copy2(INDEX, INDEX_BAK)
    shutil.copy2(CFG, CFG_BAK)


def restore():
    shutil.copy2(INDEX_BAK, INDEX)
    shutil.copy2(CFG_BAK, CFG)


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


def translate_installed_html():
    with open(INDEX, "r", encoding="utf-8") as f:
        html = f.read()

    # Replace German uiText block with English
    start = html.find("const uiText = {")
    end = html.find("function pageSize()")
    if start != -1 and end != -1:
        html = html[:start] + ENGLISH_UI_TEXT + "\n" + html[end:]

    # Translate fallback strings
    html = html.replace("'Hallo Kiddo 🌈'", "'Hello Kiddo 🌈'")
    html = html.replace("'Papa'", "'Parent'")
    html = html.replace("'Zurück'", "'Back'")
    html = html.replace("'Kindermodus beenden'", "'Exit Kids Mode'")
    html = html.replace("'Ausschalten'", "'Shut down'")
    html = html.replace("textContent=uiText.back||'Zurück'", "textContent=uiText.back||'Back'")

    # Translate hardcoded select options
    html = html.replace('<option value="rosa">Rosa</option>', '<option value="rosa">Pink</option>')
    html = html.replace('<option value="lila">Lila</option>', '<option value="lila">Purple</option>')
    html = html.replace('<option value="blau">Blau</option>', '<option value="blau">Blue</option>')
    html = html.replace('<option value="gruen">Grün</option>', '<option value="gruen">Green</option>')
    html = html.replace('<option value="regenbogen">Regenbogen</option>', '<option value="regenbogen">Rainbow</option>')

    # Translate layout option labels
    html = html.replace(">{{LABEL_LAYOUT_LARGE}}</option>", ">Large tiles</option>")
    html = html.replace(">{{LABEL_LAYOUT_SMALL}}</option>", ">Small tiles</option>")

    # Translate PIN input placeholders
    html = html.replace('placeholder="{{PIN_SET}}"', 'placeholder="Set PIN"')
    html = html.replace('placeholder="{{PIN_CONFIRM}}"', 'placeholder="Repeat"')

    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)


def write_english_config(theme="rosa"):
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
    with open(CFG, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def swap_to_admin_mode():
    with open(INDEX, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace('id="kids" class="screen"', 'id="kids" class="screen hidden"')
    html = html.replace('id="admin" class="screen hidden"', 'id="admin" class="screen"')
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)


def swap_to_kids_mode():
    with open(INDEX, "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace('id="kids" class="screen hidden"', 'id="kids" class="screen"')
    html = html.replace('id="admin" class="screen"', 'id="admin" class="screen hidden"')
    with open(INDEX, "w", encoding="utf-8") as f:
        f.write(html)


def main():
    os.makedirs(SHOTS, exist_ok=True)
    backup()
    try:
        print("Translating installed HTML...")
        translate_installed_html()

        print("Taking screenshot: home screen (rosa)...")
        write_english_config("rosa")
        screenshot("http://localhost:38431", os.path.join(SHOTS, "screenshot-home.png"))

        print("Taking screenshot: admin settings...")
        swap_to_admin_mode()
        screenshot("http://localhost:38431", os.path.join(SHOTS, "screenshot-parent-settings.png"))
        swap_to_kids_mode()

        print("Taking screenshot: blue theme...")
        write_english_config("blau")
        screenshot("http://localhost:38431", os.path.join(SHOTS, "screenshot-theme-blue.png"))

        print("Done! Screenshots saved to", SHOTS)
    finally:
        print("Restoring original files...")
        restore()
        kill_firefox()
        for bak in (INDEX_BAK, CFG_BAK):
            if os.path.exists(bak):
                os.remove(bak)


if __name__ == "__main__":
    main()
