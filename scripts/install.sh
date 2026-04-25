#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="$REPO_DIR/src"
DEFAULT_LANG="en"
APP_ID="cozy-kids-launcher"
APP_DIR_NAME="$APP_ID"
APP_BIN_NAME="cozy-kids-launcher"
DESKTOP_FILE_ID="cozy-kids-launcher.desktop"
AUTOSTART_FILE_ID="cozy-kids-launcher-autostart.desktop"
DESKTOP_SHORTCUT_ID="Cozy Kids Launcher.desktop"
DEFAULT_PORT="38431"
DEFAULT_BROWSER="auto"
DEFAULT_TITLE=""
DEFAULT_THEME="rosa"
DEFAULT_LAYOUT="gross"
DEFAULT_PARENT_LABEL=""
DEFAULT_EXIT_LABEL=""
DEFAULT_LAUNCH_MODE="kiosk"
TARGET_USER="${SUDO_USER:-${USER:-$(id -un 2>/dev/null || true)}}"
TARGET_HOME=""
INSTALL_SHUTDOWN_HELPER="0"
LANG_MODE="auto"
FORCE="0"
SKIP_BROWSER_CHECK="0"
RECOMMENDED="0"

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [options]

Options:
  --user <name>              Install for this Linux user
  --home <path>              Override user home directory
  --lang <auto|de|en>        Installer and default UI language
  --browser <auto|firefox|chromium|chromium-browser|google-chrome>
                             Preferred kiosk browser
  --title <text>             Default launcher title
  --theme <rosa|lila|blau|gruen|regenbogen>
  --layout <gross|klein>
  --launch-mode <window|fullscreen|kiosk>
                             Browser launch mode
  --parent-label <text>      Default parent/settings button label
  --exit-label <text>        Default exit button label
  --install-shutdown-helper  Install optional local shutdown helper
  --recommended              Add tiles for installed recommended apps
  --skip-browser-check       Generate files without requiring a local browser
  --force                    Overwrite existing generated files
  -h, --help                 Show this help
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

trim() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  printf '%s' "$value"
}

lang_base() {
  local raw="$1"
  raw="${raw%%.*}"
  raw="${raw%%@*}"
  raw="${raw%%_*}"
  printf '%s' "${raw,,}"
}

auto_detect_lang() {
  local candidate="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
  candidate="$(lang_base "$candidate")"
  case "$candidate" in
    de) printf 'de' ;;
    en) printf 'en' ;;
    *) printf '%s' "$DEFAULT_LANG" ;;
  esac
}

text() {
  local key="$1"
  case "$ACTIVE_LANG:$key" in
    de:app_name) echo "Cozy Kids Launcher" ;;
    de:shortcut_name) echo "Kinder-Modus" ;;
    de:autostart_name) echo "Cozy Kids Launcher beim Login" ;;
    de:config_title) echo "Hallo Kiddo 🌈" ;;
    de:parent_label) echo "Papa" ;;
    de:exit_label) echo "Kindermodus beenden" ;;
    de:shutdown_label) echo "Ausschalten" ;;
    de:no_media_title) echo "Keine Medien gefunden" ;;
    de:no_media_body) echo "Hier wurden noch keine Musik- oder Videodateien gefunden." ;;
    de:no_media_back) echo "Zurück zur Startseite" ;;
    de:admin_title) echo "Eltern-Einstellungen" ;;
    de:placeholder_title) echo "Überschrift" ;;
    de:placeholder_parent_label) echo "Eltern-Button" ;;
    de:placeholder_exit_label) echo "Beenden-Button" ;;
    de:add_tile) echo "Kachel hinzufügen" ;;
    de:back) echo "Zurück" ;;
    de:save) echo "Speichern" ;;
    de:layout_large) echo "Groß (4)" ;;
    de:layout_small) echo "Klein (9)" ;;
    de:visible) echo "sichtbar" ;;
    de:special_media) echo "Spezial: Filme und Musik" ;;
    de:no_app) echo "Kein Programm" ;;
    de:custom_cmd) echo "Benutzerdefiniert" ;;
    de:move_up) echo "Hoch" ;;
    de:move_down) echo "Runter" ;;
    de:delete) echo "Löschen" ;;
    de:new_tile) echo "Neue Kachel" ;;
    de:tile_paint) echo "Malen" ;;
    de:tile_games) echo "Lernspiele" ;;
    de:tile_music) echo "Filme und Musik" ;;
    de:tile_browser) echo "Kinder-Internet" ;;
    de:browser_url) echo "https://www.fragfinn.de/" ;;
    de:pin_title) echo "PIN eingeben" ;;
    de:pin_placeholder) echo "4-6 Zahlen" ;;
    de:pin_wrong) echo "Falscher PIN" ;;
    de:pin_set) echo "PIN setzen" ;;
    de:pin_change) echo "PIN ändern" ;;
    de:pin_remove) echo "PIN entfernen" ;;
    de:pin_confirm) echo "Wiederholen" ;;
    de:pin_mismatch) echo "PINs stimmen nicht überein" ;;
    de:pin_saved) echo "PIN gespeichert" ;;
    de:pin_removed) echo "PIN entfernt" ;;
    de:admin_page_prev) echo "← Vorherige Seite" ;;
    de:admin_page_next) echo "Nächste Seite →" ;;
    de:update_check) echo "Auf Updates prüfen" ;;
    de:update_available) echo "Update verfügbar" ;;
    de:update_up_to_date) echo "Aktuell" ;;
    de:update_error) echo "Update-Prüfung fehlgeschlagen" ;;
    de:version_label) echo "Version" ;;
    de:install_done) echo "Installation abgeschlossen." ;;
    de:next_steps) echo "Du kannst Cozy Kids Launcher jetzt über den Desktop-Shortcut oder nach dem nächsten Login starten." ;;
    de:recommended_title) echo "Empfohlene Apps" ;;
    de:recommended_installed) echo "installiert" ;;
    de:recommended_not_installed) echo "nicht installiert" ;;
    de:recommended_prompt) echo "Tiles für empfohlene Apps erstellen, falls installiert? [j/N]" ;;
    en:app_name) echo "Cozy Kids Launcher" ;;
    en:shortcut_name) echo "Kids Mode" ;;
    en:autostart_name) echo "Cozy Kids Launcher on Login" ;;
    en:config_title) echo "Hello Kiddo 🌈" ;;
    en:parent_label) echo "Parent" ;;
    en:exit_label) echo "Exit kids mode" ;;
    en:shutdown_label) echo "Shut down" ;;
    en:no_media_title) echo "No media found" ;;
    en:no_media_body) echo "No music or video files were found here yet." ;;
    en:no_media_back) echo "Back to home screen" ;;
    en:admin_title) echo "Parent settings" ;;
    en:placeholder_title) echo "Title" ;;
    en:placeholder_parent_label) echo "Parent button" ;;
    en:placeholder_exit_label) echo "Exit button" ;;
    en:add_tile) echo "Add tile" ;;
    en:back) echo "Back" ;;
    en:save) echo "Save" ;;
    en:layout_large) echo "Large (4)" ;;
    en:layout_small) echo "Small (9)" ;;
    en:visible) echo "visible" ;;
    en:special_media) echo "Special: Movies and music" ;;
    en:no_app) echo "No app" ;;
    en:custom_cmd) echo "Custom" ;;
    en:move_up) echo "Up" ;;
    en:move_down) echo "Down" ;;
    en:delete) echo "Delete" ;;
    en:new_tile) echo "New tile" ;;
    en:tile_paint) echo "Paint" ;;
    en:tile_games) echo "Learning games" ;;
    en:tile_music) echo "Movies and music" ;;
    en:tile_browser) echo "Kids browser" ;;
    en:browser_url) echo "https://www.pbskids.org/" ;;
    en:pin_title) echo "Enter PIN" ;;
    en:pin_placeholder) echo "4-6 digits" ;;
    en:pin_wrong) echo "Wrong PIN" ;;
    en:pin_set) echo "Set PIN" ;;
    en:pin_change) echo "Change PIN" ;;
    en:pin_remove) echo "Remove PIN" ;;
    en:pin_confirm) echo "Repeat" ;;
    en:pin_mismatch) echo "PINs do not match" ;;
    en:pin_saved) echo "PIN saved" ;;
    en:pin_removed) echo "PIN removed" ;;
    en:admin_page_prev) echo "← Previous page" ;;
    en:admin_page_next) echo "Next page →" ;;
    en:update_check) echo "Check for updates" ;;
    en:update_available) echo "Update available" ;;
    en:update_up_to_date) echo "Up to date" ;;
    en:update_error) echo "Update check failed" ;;
    en:version_label) echo "Version" ;;
    en:install_done) echo "Installation complete." ;;
    en:next_steps) echo "You can now launch Cozy Kids Launcher from the desktop shortcut or after the next login." ;;
    en:recommended_title) echo "Recommended apps" ;;
    en:recommended_installed) echo "installed" ;;
    en:recommended_not_installed) echo "not installed" ;;
    en:recommended_prompt) echo "Create tiles for recommended apps if installed? [y/N]" ;;
    *) die "Missing translation for $ACTIVE_LANG:$key" ;;
  esac
}

json_text() {
  python3 - "$1" <<'PY'
import json, sys
print(json.dumps(sys.argv[1], ensure_ascii=False))
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      TARGET_USER="${2:-}"
      shift 2
      ;;
    --home)
      TARGET_HOME="${2:-}"
      shift 2
      ;;
    --lang)
      LANG_MODE="${2:-}"
      shift 2
      ;;
    --browser)
      DEFAULT_BROWSER="${2:-}"
      shift 2
      ;;
    --title)
      DEFAULT_TITLE="${2:-}"
      shift 2
      ;;
    --theme)
      DEFAULT_THEME="${2:-}"
      shift 2
      ;;
    --layout)
      DEFAULT_LAYOUT="${2:-}"
      shift 2
      ;;
    --launch-mode)
      DEFAULT_LAUNCH_MODE="${2:-}"
      shift 2
      ;;
    --parent-label)
      DEFAULT_PARENT_LABEL="${2:-}"
      shift 2
      ;;
    --exit-label)
      DEFAULT_EXIT_LABEL="${2:-}"
      shift 2
      ;;
    --install-shutdown-helper)
      INSTALL_SHUTDOWN_HELPER="1"
      shift
      ;;
    --recommended)
      RECOMMENDED="1"
      shift
      ;;
    --skip-browser-check)
      SKIP_BROWSER_CHECK="1"
      shift
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

[[ -n "$TARGET_USER" ]] || die "No target user resolved. Use --user <name>."

if [[ -z "$TARGET_HOME" ]]; then
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
fi
[[ -n "$TARGET_HOME" ]] || die "Could not resolve home directory for user '$TARGET_USER'."
[[ -d "$TARGET_HOME" ]] || die "Home directory does not exist: $TARGET_HOME"

case "$LANG_MODE" in
  auto) ACTIVE_LANG="$(auto_detect_lang)" ;;
  de|en) ACTIVE_LANG="$LANG_MODE" ;;
  *) die "Unsupported language: $LANG_MODE" ;;
esac

case "$DEFAULT_THEME" in
  rosa|lila|blau|gruen|regenbogen) ;;
  *) die "Unsupported theme: $DEFAULT_THEME" ;;
esac

case "$DEFAULT_LAYOUT" in
  gross|klein) ;;
  *) die "Unsupported layout: $DEFAULT_LAYOUT" ;;
esac

case "$DEFAULT_LAUNCH_MODE" in
  window|fullscreen|kiosk) ;;
  *) die "Unsupported launch mode: $DEFAULT_LAUNCH_MODE" ;;
esac

find_browser() {
  if [[ "$DEFAULT_BROWSER" != "auto" ]]; then
    command -v "$DEFAULT_BROWSER" >/dev/null 2>&1 || die "Browser not found: $DEFAULT_BROWSER"
    printf '%s' "$DEFAULT_BROWSER"
    return
  fi

  local candidates=(firefox chromium chromium-browser google-chrome)
  local browser
  for browser in "${candidates[@]}"; do
    if command -v "$browser" >/dev/null 2>&1; then
      printf '%s' "$browser"
      return
    fi
  done

  if [[ "$SKIP_BROWSER_CHECK" == "1" ]]; then
    printf '%s' "firefox"
    return
  fi

  die "No supported browser found. Install Firefox or Chromium, or pass --browser."
}

BROWSER_CMD="$(find_browser)"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
command -v install >/dev/null 2>&1 || die "install is required"

APP_ROOT="$TARGET_HOME/.local/share/$APP_DIR_NAME"
BIN_DIR="$TARGET_HOME/.local/bin"
CFG_DIR="$TARGET_HOME/.config/$APP_DIR_NAME"
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
DESKTOP_DIR="$TARGET_HOME/Desktop"
if [[ ! -d "$DESKTOP_DIR" && -d "$TARGET_HOME/Schreibtisch" ]]; then
  DESKTOP_DIR="$TARGET_HOME/Schreibtisch"
fi
CACHE_DIR="$TARGET_HOME/.cache/$APP_DIR_NAME"
RUNTIME_BIN="$BIN_DIR/$APP_BIN_NAME"
CONFIG_FILE="$CFG_DIR/config.json"
SERVER_FILE="$APP_ROOT/server.py"
INDEX_FILE="$APP_ROOT/index.html"
MEDIA_FILE="$APP_ROOT/no-media.html"
AUTOSTART_FILE="$AUTOSTART_DIR/$AUTOSTART_FILE_ID"
DESKTOP_FILE="$DESKTOP_DIR/$DESKTOP_SHORTCUT_ID"
APP_DESKTOP_FILE="$TARGET_HOME/.local/share/applications/$DESKTOP_FILE_ID"
UNINSTALL_FILE="$APP_ROOT/uninstall.txt"
BACKUP_DIR="$TARGET_HOME/.local/share/$APP_DIR_NAME-backups/$(date +%Y%m%d-%H%M%S)"

mkdir -p "$APP_ROOT" "$BIN_DIR" "$CFG_DIR" "$AUTOSTART_DIR" "$DESKTOP_DIR" "$CACHE_DIR" "$(dirname "$APP_DESKTOP_FILE")" "$BACKUP_DIR"

backup_if_exists() {
  local path="$1"
  [[ -e "$path" ]] || return 0
  cp -a "$path" "$BACKUP_DIR/$(basename "$path")"
}

write_file() {
  local path="$1"
  local mode="$2"
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if [[ -e "$path" && "$FORCE" != "1" ]]; then
    backup_if_exists "$path"
  fi
  install -m "$mode" "$tmp" "$path"
  rm -f "$tmp"
}

render_template() {
  local src="$1"
  local dest="$2"
  local mode="$3"

  if [[ ! -f "$src" ]]; then
    die "Template not found: $src"
  fi

  local tmp
  tmp="$(mktemp)"

  # Export all template variables so Python can see them
  export APP_ID DEFAULT_PORT BROWSER_CMD DEFAULT_THEME DEFAULT_LAYOUT
  export DEFAULT_LAUNCH_MODE INSTALL_SHUTDOWN_HELPER ACTIVE_LANG
  export DEFAULT_TITLE DEFAULT_PARENT_LABEL DEFAULT_EXIT_LABEL SHUTDOWN_LABEL
  export ADMIN_TITLE PLACEHOLDER_TITLE PLACEHOLDER_PARENT_LABEL PLACEHOLDER_EXIT_LABEL
  export LABEL_LAYOUT_LARGE LABEL_LAYOUT_SMALL LABEL_ADD_TILE LABEL_BACK LABEL_SAVE
  export LABEL_VISIBLE LABEL_SPECIAL_MEDIA LABEL_NO_APP LABEL_CUSTOM_CMD
  export LABEL_MOVE_UP LABEL_MOVE_DOWN LABEL_DELETE DEFAULT_NEW_TILE_LABEL
  export NO_MEDIA_TITLE NO_MEDIA_BODY NO_MEDIA_BACK
  export PIN_TITLE PIN_PLACEHOLDER PIN_WRONG PIN_SET PIN_CHANGE PIN_REMOVE PIN_CONFIRM PIN_MISMATCH PIN_SAVED PIN_REMOVED ADMIN_PAGE_PREV ADMIN_PAGE_NEXT
  export DEFAULT_TILE_PAINT DEFAULT_TILE_GAMES DEFAULT_TILE_MUSIC DEFAULT_TILE_BROWSER DEFAULT_BROWSER_URL
  export JSON_ADMIN_TITLE JSON_PLACEHOLDER_TITLE JSON_PLACEHOLDER_PARENT_LABEL JSON_PLACEHOLDER_EXIT_LABEL
  export JSON_ADD_TILE JSON_BACK JSON_SAVE JSON_VISIBLE JSON_SPECIAL_MEDIA
  export JSON_NO_APP JSON_CUSTOM_CMD JSON_MOVE_UP JSON_MOVE_DOWN JSON_DELETE JSON_NEW_TILE
  export JSON_PIN_TITLE JSON_PIN_PLACEHOLDER JSON_PIN_WRONG JSON_PIN_SET JSON_PIN_CHANGE JSON_PIN_REMOVE JSON_PIN_CONFIRM JSON_PIN_MISMATCH JSON_PIN_SAVED JSON_PIN_REMOVED JSON_ADMIN_PAGE_PREV JSON_ADMIN_PAGE_NEXT
  export JSON_UPDATE_CHECK JSON_UPDATE_AVAILABLE JSON_UPDATE_UP_TO_DATE JSON_UPDATE_ERROR JSON_VERSION_LABEL
  export RECOMMENDED_TITLE RECOMMENDED_INSTALLED RECOMMENDED_NOT_INSTALLED RECOMMENDED_PROMPT
  export JSON_RECOMMENDED_TITLE JSON_RECOMMENDED_INSTALLED JSON_RECOMMENDED_NOT_INSTALLED JSON_RECOMMENDED_PROMPT
  export APP_NAME

  python3 - "$src" "$tmp" <<'PY'
import sys, os, re
src, dst = sys.argv[1], sys.argv[2]
with open(src, 'r', encoding='utf-8') as f:
    content = f.read()

def replacer(m):
    key = m.group(1)
    return os.environ.get(key, m.group(0))

content = re.sub(r'\{\{(\w+)\}\}', replacer, content)
with open(dst, 'w', encoding='utf-8') as f:
    f.write(content)
PY

  if [[ -e "$dest" && "$FORCE" != "1" ]]; then
    backup_if_exists "$dest"
  fi
  install -m "$mode" "$tmp" "$dest"
  rm -f "$tmp"
}

DEFAULT_TITLE="$(trim "${DEFAULT_TITLE:-$(text config_title)}")"
DEFAULT_PARENT_LABEL="$(trim "${DEFAULT_PARENT_LABEL:-$(text parent_label)}")"
DEFAULT_EXIT_LABEL="$(trim "${DEFAULT_EXIT_LABEL:-$(text exit_label)}")"
SHUTDOWN_LABEL="$(text shutdown_label)"
SHORTCUT_NAME="$(text shortcut_name)"
AUTOSTART_NAME="$(text autostart_name)"
APP_NAME="$(text app_name)"
NO_MEDIA_TITLE="$(text no_media_title)"
NO_MEDIA_BODY="$(text no_media_body)"
NO_MEDIA_BACK="$(text no_media_back)"
ADMIN_TITLE="$(text admin_title)"
PLACEHOLDER_TITLE="$(text placeholder_title)"
PLACEHOLDER_PARENT_LABEL="$(text placeholder_parent_label)"
PLACEHOLDER_EXIT_LABEL="$(text placeholder_exit_label)"
LABEL_ADD_TILE="$(text add_tile)"
LABEL_BACK="$(text back)"
LABEL_SAVE="$(text save)"
LABEL_LAYOUT_LARGE="$(text layout_large)"
LABEL_LAYOUT_SMALL="$(text layout_small)"
LABEL_VISIBLE="$(text visible)"
LABEL_SPECIAL_MEDIA="$(text special_media)"
LABEL_NO_APP="$(text no_app)"
LABEL_CUSTOM_CMD="$(text custom_cmd)"
LABEL_MOVE_UP="$(text move_up)"
LABEL_MOVE_DOWN="$(text move_down)"
LABEL_DELETE="$(text delete)"
DEFAULT_NEW_TILE_LABEL="$(text new_tile)"
PIN_TITLE="$(text pin_title)"
PIN_PLACEHOLDER="$(text pin_placeholder)"
PIN_WRONG="$(text pin_wrong)"
PIN_SET="$(text pin_set)"
PIN_CHANGE="$(text pin_change)"
PIN_REMOVE="$(text pin_remove)"
PIN_CONFIRM="$(text pin_confirm)"
PIN_MISMATCH="$(text pin_mismatch)"
PIN_SAVED="$(text pin_saved)"
PIN_REMOVED="$(text pin_removed)"
ADMIN_PAGE_PREV="$(text admin_page_prev)"
ADMIN_PAGE_NEXT="$(text admin_page_next)"
UPDATE_CHECK="$(text update_check)"
UPDATE_AVAILABLE="$(text update_available)"
UPDATE_UP_TO_DATE="$(text update_up_to_date)"
UPDATE_ERROR="$(text update_error)"
VERSION_LABEL="$(text version_label)"
DEFAULT_TILE_PAINT="$(text tile_paint)"
DEFAULT_TILE_GAMES="$(text tile_games)"
DEFAULT_TILE_MUSIC="$(text tile_music)"
DEFAULT_TILE_BROWSER="$(text tile_browser)"
DEFAULT_BROWSER_URL="$(text browser_url)"
RECOMMENDED_TITLE="$(text recommended_title)"
RECOMMENDED_INSTALLED="$(text recommended_installed)"
RECOMMENDED_NOT_INSTALLED="$(text recommended_not_installed)"
RECOMMENDED_PROMPT="$(text recommended_prompt)"

JSON_ADMIN_TITLE="$(json_text "$ADMIN_TITLE")"
JSON_PLACEHOLDER_TITLE="$(json_text "$PLACEHOLDER_TITLE")"
JSON_PLACEHOLDER_PARENT_LABEL="$(json_text "$PLACEHOLDER_PARENT_LABEL")"
JSON_PLACEHOLDER_EXIT_LABEL="$(json_text "$PLACEHOLDER_EXIT_LABEL")"
JSON_ADD_TILE="$(json_text "$LABEL_ADD_TILE")"
JSON_BACK="$(json_text "$LABEL_BACK")"
JSON_SAVE="$(json_text "$LABEL_SAVE")"
JSON_VISIBLE="$(json_text "$LABEL_VISIBLE")"
JSON_SPECIAL_MEDIA="$(json_text "$LABEL_SPECIAL_MEDIA")"
JSON_NO_APP="$(json_text "$LABEL_NO_APP")"
JSON_CUSTOM_CMD="$(json_text "$LABEL_CUSTOM_CMD")"
JSON_MOVE_UP="$(json_text "$LABEL_MOVE_UP")"
JSON_MOVE_DOWN="$(json_text "$LABEL_MOVE_DOWN")"
JSON_DELETE="$(json_text "$LABEL_DELETE")"
JSON_NEW_TILE="$(json_text "$DEFAULT_NEW_TILE_LABEL")"
JSON_PIN_TITLE="$(json_text "$PIN_TITLE")"
JSON_PIN_PLACEHOLDER="$(json_text "$PIN_PLACEHOLDER")"
JSON_PIN_WRONG="$(json_text "$PIN_WRONG")"
JSON_PIN_SET="$(json_text "$PIN_SET")"
JSON_PIN_CHANGE="$(json_text "$PIN_CHANGE")"
JSON_PIN_REMOVE="$(json_text "$PIN_REMOVE")"
JSON_PIN_CONFIRM="$(json_text "$PIN_CONFIRM")"
JSON_PIN_MISMATCH="$(json_text "$PIN_MISMATCH")"
JSON_PIN_SAVED="$(json_text "$PIN_SAVED")"
JSON_PIN_REMOVED="$(json_text "$PIN_REMOVED")"
JSON_ADMIN_PAGE_PREV="$(json_text "$ADMIN_PAGE_PREV")"
JSON_ADMIN_PAGE_NEXT="$(json_text "$ADMIN_PAGE_NEXT")"
JSON_UPDATE_CHECK="$(json_text "$UPDATE_CHECK")"
JSON_UPDATE_AVAILABLE="$(json_text "$UPDATE_AVAILABLE")"
JSON_UPDATE_UP_TO_DATE="$(json_text "$UPDATE_UP_TO_DATE")"
JSON_UPDATE_ERROR="$(json_text "$UPDATE_ERROR")"
JSON_VERSION_LABEL="$(json_text "$VERSION_LABEL")"
JSON_RECOMMENDED_TITLE="$(json_text "$RECOMMENDED_TITLE")"
JSON_RECOMMENDED_INSTALLED="$(json_text "$RECOMMENDED_INSTALLED")"
JSON_RECOMMENDED_NOT_INSTALLED="$(json_text "$RECOMMENDED_NOT_INSTALLED")"
JSON_RECOMMENDED_PROMPT="$(json_text "$RECOMMENDED_PROMPT")"

backup_if_exists "$RUNTIME_BIN"
backup_if_exists "$SERVER_FILE"
backup_if_exists "$INDEX_FILE"
backup_if_exists "$MEDIA_FILE"
backup_if_exists "$CONFIG_FILE"
backup_if_exists "$AUTOSTART_FILE"
backup_if_exists "$DESKTOP_FILE"
backup_if_exists "$APP_DESKTOP_FILE"

# Interactive recommended-apps prompt
if [[ "$RECOMMENDED" != "1" && -t 0 ]]; then
  echo ""
  echo "$RECOMMENDED_PROMPT"
  read -r answer
  case "$answer" in
    [jJyY]*) RECOMMENDED="1" ;;
    *) RECOMMENDED="0" ;;
  esac
fi

# Render templates from src/
render_template "$SRC_DIR/server.py" "$SERVER_FILE" 0644
render_template "$SRC_DIR/index.html" "$INDEX_FILE" 0644
render_template "$SRC_DIR/no-media.html" "$MEDIA_FILE" 0644
render_template "$SRC_DIR/launcher.sh" "$RUNTIME_BIN" 0755

# Generate config JSON with proper escaping
python3 - "$CONFIG_FILE" "$ACTIVE_LANG" "$DEFAULT_TITLE" "$DEFAULT_THEME" "$DEFAULT_LAYOUT" "$DEFAULT_PARENT_LABEL" "$DEFAULT_EXIT_LABEL" "$SHUTDOWN_LABEL" "$DEFAULT_TILE_PAINT" "$DEFAULT_TILE_GAMES" "$DEFAULT_TILE_MUSIC" "$DEFAULT_TILE_BROWSER" "$DEFAULT_BROWSER_URL" "$SRC_DIR/recommendations.json" "$RECOMMENDED" <<'PY'
import json, sys, shutil, os
path, lang, title, theme, layout, parent_label, exit_label, shutdown_label, tile_paint, tile_games, tile_music, tile_browser, browser_url, rec_path, recommended = sys.argv[1:16]
config = {
    "language": lang,
    "title": title,
    "theme": theme,
    "layoutMode": layout,
    "parentLabel": parent_label,
    "exitLabel": exit_label,
    "shutdownLabel": shutdown_label,
    "pinHash": "",
    "currentPage": 0,
    "tiles": [
        {"id": "paint", "label": tile_paint, "emoji": "🎨", "cmd": ["tuxpaint"], "visible": True},
        {"id": "games", "label": tile_games, "emoji": "🧩", "cmd": ["gcompris"], "visible": True},
        {"id": "music", "label": tile_music, "emoji": "🎵", "cmd": ["special:filme-musik"], "visible": True},
        {"id": "browser", "label": tile_browser, "emoji": "🌐", "cmd": ["xdg-open", browser_url], "visible": False}
    ]
}
existing_ids = {"paint", "games", "music", "browser"}
if recommended == "1" and os.path.isfile(rec_path):
    with open(rec_path, 'r', encoding='utf-8') as f:
        recs = json.load(f)
    for rec in recs:
        if rec["id"] in existing_ids:
            continue
        cmds = rec.get("cmd", [])
        alt_cmds = rec.get("alt_cmds", [])
        found_cmd = None
        for cmd in cmds:
            if shutil.which(cmd):
                found_cmd = cmd
                break
        if not found_cmd:
            for cmd in alt_cmds:
                if shutil.which(cmd):
                    found_cmd = cmd
                    break
        if found_cmd:
            label = rec.get("label_de" if lang == "de" else "label_en", rec["id"])
            tile_cmd = cmds if (cmds and found_cmd == cmds[0]) else [found_cmd]
            config["tiles"].append({
                "id": rec["id"],
                "label": label,
                "emoji": rec.get("emoji", "✨"),
                "cmd": tile_cmd,
                "visible": True
            })
            existing_ids.add(rec["id"])
with open(path, 'w', encoding='utf-8') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
    f.write('\n')
PY

# Copy recommendations data for runtime use
if [[ -f "$SRC_DIR/recommendations.json" ]]; then
  install -m 0644 "$SRC_DIR/recommendations.json" "$APP_ROOT/recommendations.json"
fi

write_file "$AUTOSTART_FILE" 0644 <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$AUTOSTART_NAME
Exec=$RUNTIME_BIN
Terminal=false
NoDisplay=true
X-KDE-autostart-phase=2
EOF

write_file "$DESKTOP_FILE" 0755 <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$SHORTCUT_NAME
Exec=$RUNTIME_BIN
Icon=preferences-desktop-theme
Terminal=false
Categories=Utility;
EOF

write_file "$APP_DESKTOP_FILE" 0644 <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
Exec=$RUNTIME_BIN
Icon=preferences-desktop-theme
Terminal=false
Categories=Utility;
EOF

write_file "$UNINSTALL_FILE" 0644 <<EOF
Remove these paths to uninstall:
- $APP_ROOT
- $CFG_DIR
- $RUNTIME_BIN
- $AUTOSTART_FILE
- $DESKTOP_FILE
- $APP_DESKTOP_FILE

Backups from this run are in:
- $BACKUP_DIR
EOF

# Write version marker
if [[ -f "$REPO_DIR/VERSION" ]]; then
  install -m 0644 "$REPO_DIR/VERSION" "$APP_ROOT/version"
fi

chown -R "$TARGET_USER":"$TARGET_USER" "$APP_ROOT" "$CFG_DIR" "$CACHE_DIR"
chown "$TARGET_USER":"$TARGET_USER" "$RUNTIME_BIN" "$AUTOSTART_FILE" "$DESKTOP_FILE" "$APP_DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then
    update-desktop-database "$TARGET_HOME/.local/share/applications" >/dev/null 2>&1 || true
  elif command -v runuser >/dev/null 2>&1 && [[ "$(id -u)" == "0" ]]; then
    runuser -u "$TARGET_USER" -- sh -lc 'update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true'
  fi
fi

echo "$(text install_done)"
echo "$APP_NAME"
echo "  user: $TARGET_USER"
echo "  home: $TARGET_HOME"
echo "  language: $ACTIVE_LANG"
echo "  browser: $BROWSER_CMD"
echo "  shutdown helper enabled: $INSTALL_SHUTDOWN_HELPER"
echo "  backup dir: $BACKUP_DIR"
echo "$(text next_steps)"
