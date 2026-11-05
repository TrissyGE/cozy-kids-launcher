#!/usr/bin/env bash
set -euo pipefail
if [[ -d /snap/bin ]] && [[ ":$PATH:" != *":/snap/bin:"* ]]; then
  export PATH="$PATH:/snap/bin"
fi

# Self-bootstrap: if run standalone (e.g. curl | bash) and src/ is missing,
# download the repo and re-execute from the extracted copy.
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
  REPO_DIR="."
fi
SRC_DIR="$REPO_DIR/src"

if [[ ! -d "$SRC_DIR" ]] || [[ ! -f "$SRC_DIR/server.py" ]]; then
  REPO="TrissyGE/cozy-kids-launcher"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT

  echo "Downloading Cozy Kids Launcher..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$TMP_DIR/repo.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_DIR/repo.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
  else
    echo "Error: curl or wget is required."
    exit 1
  fi

  echo "Extracting..."
  if command -v unzip >/dev/null 2>&1; then
    unzip -q "$TMP_DIR/repo.zip" -d "$TMP_DIR/"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m zipfile -e "$TMP_DIR/repo.zip" "$TMP_DIR/"
  else
    echo "Error: unzip or Python 3 is required to extract the download."
    exit 1
  fi

  # Re-execute with all original arguments
  exec bash "$TMP_DIR/cozy-kids-launcher-main/scripts/install.sh" "$@"
fi

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
EXPLICIT_LANG=0
EXPLICIT_BROWSER=0
EXPLICIT_TITLE=0
EXPLICIT_THEME=0
EXPLICIT_LAYOUT=0
EXPLICIT_LAUNCH_MODE=0
EXPLICIT_PARENT_LABEL=0
EXPLICIT_EXIT_LABEL=0
EXPLICIT_SHUTDOWN=0
EXPLICIT_RECOMMENDED=0

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [options]

Options:
  --user <name>              Install for this Linux user
  --home <path>              Override user home directory
  --lang <auto|code>         Installer and default UI language (see language registry)
  --browser <auto|firefox|chromium|chromium-browser|google-chrome|google-chrome-stable|brave|opera|opera-stable|vivaldi|vivaldi-stable|microsoft-edge|microsoft-edge-stable|cachy-browser|librewolf>
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

is_interactive() {
  [[ -t 0 ]]
}

prompt_read() {
  local prompt_text="$1"
  local var_name="$2"
  if [[ -t 0 ]]; then
    IFS= read -r -p "$prompt_text" "$var_name"
  elif [[ -r /dev/tty ]] && command -v tty >/dev/null 2>&1 && tty >/dev/null 2>&1; then
    IFS= read -r -p "$prompt_text" "$var_name" < /dev/tty
  fi
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
  raw="${raw%%-*}"
  printf '%s' "${raw,,}"
}

language_supported() {
  local code
  for code in "${LANGUAGE_CODES[@]}"; do
    [[ "$code" != "$1" ]] || return 0
  done
  return 1
}

resolve_language() {
  if [[ "$LANG_MODE" == "auto" ]]; then
    local candidate
    candidate="$(lang_base "${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}")"
    ACTIVE_LANG="$DEFAULT_LANG"
    if language_supported "$candidate"; then
      ACTIVE_LANG="$candidate"
    fi
  else
    language_supported "$LANG_MODE" || die "Unsupported language: $LANG_MODE"
    ACTIVE_LANG="$LANG_MODE"
  fi
  load_translation_table
}

load_translation_table() {
  local rows row
  rows="$(PYTHONIOENCODING=utf-8 python3 "$SRC_DIR/translation_data.py" "$ACTIVE_LANG")" ||
    die "Could not load translations for $ACTIVE_LANG"
  TRANSLATIONS=()
  while IFS= read -r row; do
    TRANSLATIONS["${row%%$'\t'*}"]="${row#*$'\t'}"
  done <<< "$rows"
}

text() {
  local key="$1"
  [[ -n "${TRANSLATIONS[$key]+present}" ]] || die "Missing translation: $key"
  printf '%s\n' "${TRANSLATIONS[$key]}"
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
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      TARGET_USER="$2"
      shift 2
      ;;
    --home)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      TARGET_HOME="$2"
      shift 2
      ;;
    --lang)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      LANG_MODE="$2"
      EXPLICIT_LANG=1
      shift 2
      ;;
    --browser)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_BROWSER="$2"
      EXPLICIT_BROWSER=1
      shift 2
      ;;
    --title)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_TITLE="$2"
      EXPLICIT_TITLE=1
      shift 2
      ;;
    --theme)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_THEME="$2"
      EXPLICIT_THEME=1
      shift 2
      ;;
    --layout)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_LAYOUT="$2"
      EXPLICIT_LAYOUT=1
      shift 2
      ;;
    --launch-mode)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_LAUNCH_MODE="$2"
      EXPLICIT_LAUNCH_MODE=1
      shift 2
      ;;
    --parent-label)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_PARENT_LABEL="$2"
      EXPLICIT_PARENT_LABEL=1
      shift 2
      ;;
    --exit-label)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_EXIT_LABEL="$2"
      EXPLICIT_EXIT_LABEL=1
      shift 2
      ;;
    --install-shutdown-helper)
      INSTALL_SHUTDOWN_HELPER="1"
      EXPLICIT_SHUTDOWN=1
      shift
      ;;
    --recommended)
      RECOMMENDED="1"
      EXPLICIT_RECOMMENDED=1
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

command -v python3 >/dev/null 2>&1 || die "python3 is required"
registry_rows="$(PYTHONIOENCODING=utf-8 python3 "$SRC_DIR/language_registry.py")" || die "Could not load language registry"
LANGUAGE_CODES=()
LANGUAGE_NAMES=()
{
  read -r DEFAULT_LANG
  while IFS=$'\t' read -r code name; do
    LANGUAGE_CODES+=("$code")
    LANGUAGE_NAMES+=("$name")
  done
} <<< "$registry_rows"
JSON_LANGUAGE_REGISTRY="$(cat "$SRC_DIR/language_registry.json")"
declare -A TRANSLATIONS=()
resolve_language

case "$DEFAULT_THEME" in
  rosa|lila|blau|gruen|regenbogen|wald|weltraum|ocean|dinosaurier|baustelle|prinzessin|bauernhof|katzen|hunde) ;;
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

guided_setup() {
  local input index auto_choice
  echo ""
  echo "========================================="
  echo "$(text cli_guided)"
  echo "========================================="
  echo ""

  if [[ "$EXPLICIT_LANG" == "0" ]]; then
    echo "$(text cli_choose_language)"
    for index in "${!LANGUAGE_CODES[@]}"; do
      printf '  %s) %s\n' "$((index + 1))" "${LANGUAGE_NAMES[index]}"
    done
    auto_choice="$((${#LANGUAGE_CODES[@]} + 1))"
    echo "  $auto_choice) $(text cli_auto)"
    prompt_read "$(text cli_choice) [$auto_choice]: " input
    for index in "${!LANGUAGE_CODES[@]}"; do
      if [[ "$input" == "$((index + 1))" ]]; then
        LANG_MODE="${LANGUAGE_CODES[index]}"
        EXPLICIT_LANG=1
        break
      fi
    done
    resolve_language
  fi

  if [[ "$EXPLICIT_BROWSER" == "0" ]]; then
    echo ""
    echo "$(text cli_choose_browser)"
    echo "  1) $(text cli_auto)"
    echo "  2) Firefox"
    echo "  3) Chromium"
    echo "  4) Google Chrome"
    echo "  5) $(text cli_browser_other)"
    prompt_read "$(text cli_choice) [1]: " input
    case "$input" in
      2) DEFAULT_BROWSER="firefox"; EXPLICIT_BROWSER=1 ;;
      3) DEFAULT_BROWSER="chromium"; EXPLICIT_BROWSER=1 ;;
      4)
        if command -v google-chrome >/dev/null 2>&1; then
          DEFAULT_BROWSER="google-chrome"; EXPLICIT_BROWSER=1
        elif command -v google-chrome-stable >/dev/null 2>&1; then
          DEFAULT_BROWSER="google-chrome-stable"; EXPLICIT_BROWSER=1
        else
          DEFAULT_BROWSER="google-chrome"; EXPLICIT_BROWSER=1
        fi
        ;;
      5)
        prompt_read "$(text cli_browser_command) " input
        if [[ -n "$input" ]]; then
          DEFAULT_BROWSER="$input"; EXPLICIT_BROWSER=1
        fi
        ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_THEME" == "0" ]]; then
    echo ""
    echo "$(text cli_choose_theme)"
    local themes=(rosa lila blau gruen regenbogen wald weltraum ocean dinosaurier baustelle prinzessin bauernhof katzen hunde)
    for index in "${!themes[@]}"; do
      printf '  %2d) %s' "$((index + 1))" "$(text "theme_name_${themes[index]}")"
      if [[ "$index" == 0 ]]; then printf ' (%s)' "$(text cli_default)"; fi
      printf '\n'
    done
    prompt_read "$(text cli_choice) [1]: " input
    case "$input" in
      2) DEFAULT_THEME="lila"; EXPLICIT_THEME=1 ;;
      3) DEFAULT_THEME="blau"; EXPLICIT_THEME=1 ;;
      4) DEFAULT_THEME="gruen"; EXPLICIT_THEME=1 ;;
      5) DEFAULT_THEME="regenbogen"; EXPLICIT_THEME=1 ;;
      6) DEFAULT_THEME="wald"; EXPLICIT_THEME=1 ;;
      7) DEFAULT_THEME="weltraum"; EXPLICIT_THEME=1 ;;
      8) DEFAULT_THEME="ocean"; EXPLICIT_THEME=1 ;;
      9) DEFAULT_THEME="dinosaurier"; EXPLICIT_THEME=1 ;;
      10) DEFAULT_THEME="baustelle"; EXPLICIT_THEME=1 ;;
      11) DEFAULT_THEME="prinzessin"; EXPLICIT_THEME=1 ;;
      12) DEFAULT_THEME="bauernhof"; EXPLICIT_THEME=1 ;;
      13) DEFAULT_THEME="katzen"; EXPLICIT_THEME=1 ;;
      14) DEFAULT_THEME="hunde"; EXPLICIT_THEME=1 ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_LAYOUT" == "0" ]]; then
    echo ""
    echo "$(text cli_choose_layout)"
    echo "  1) $(text layout_large) ($(text cli_default))"
    echo "  2) $(text layout_small)"
    prompt_read "$(text cli_choice) [1]: " input
    case "$input" in
      2) DEFAULT_LAYOUT="klein"; EXPLICIT_LAYOUT=1 ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_LAUNCH_MODE" == "0" ]]; then
    echo ""
    echo "$(text cli_choose_mode)"
    echo "  1) $(text cli_mode_kiosk) ($(text cli_default))"
    echo "  2) $(text cli_mode_fullscreen)"
    echo "  3) $(text cli_mode_window)"
    prompt_read "$(text cli_choice) [1]: " input
    case "$input" in
      2) DEFAULT_LAUNCH_MODE="fullscreen"; EXPLICIT_LAUNCH_MODE=1 ;;
      3) DEFAULT_LAUNCH_MODE="window"; EXPLICIT_LAUNCH_MODE=1 ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_TITLE" == "0" ]]; then
    echo ""
    prompt_read "$(text cli_title) [$(text config_title)]: " input
    if [[ -n "$input" ]]; then
      DEFAULT_TITLE="$input"
      EXPLICIT_TITLE=1
    fi
  fi

  if [[ "$EXPLICIT_PARENT_LABEL" == "0" ]]; then
    echo ""
    prompt_read "$(text cli_parent) [$(text parent_label)]: " input
    if [[ -n "$input" ]]; then
      DEFAULT_PARENT_LABEL="$input"
      EXPLICIT_PARENT_LABEL=1
    fi
  fi

  if [[ "$EXPLICIT_EXIT_LABEL" == "0" ]]; then
    echo ""
    prompt_read "$(text cli_exit) [$(text exit_label)]: " input
    if [[ -n "$input" ]]; then
      DEFAULT_EXIT_LABEL="$input"
      EXPLICIT_EXIT_LABEL=1
    fi
  fi

  if [[ "$EXPLICIT_SHUTDOWN" == "0" ]]; then
    echo ""
    prompt_read "$(text cli_shutdown): " input
    case "$input" in
      [jJyY]*) INSTALL_SHUTDOWN_HELPER="1"; EXPLICIT_SHUTDOWN=1 ;;
    esac
  fi

  if [[ "$EXPLICIT_RECOMMENDED" == "0" ]]; then
    echo ""
    prompt_read "$(text recommended_prompt): " input
    case "$input" in
      [jJyY]*) RECOMMENDED="1"; EXPLICIT_RECOMMENDED=1 ;;
    esac
  fi
}

# Offer guided mode when running interactively without explicit customizations
if is_interactive; then
  echo ""
  prompt_read "$(text cli_quick_or_guided) " input
  case "$input" in
    [wW]*) guided_setup ;;
    *) echo "$(text cli_using_defaults)" ;;
  esac

fi

find_browser() {
  if [[ "$DEFAULT_BROWSER" != "auto" ]]; then
    command -v "$DEFAULT_BROWSER" >/dev/null 2>&1 || die "Browser not found: $DEFAULT_BROWSER"
    printf '%s' "$DEFAULT_BROWSER"
    return
  fi

  local candidates=(firefox chromium chromium-browser google-chrome google-chrome-stable brave brave-browser opera opera-stable vivaldi vivaldi-stable microsoft-edge microsoft-edge-stable cachy-browser librewolf)
  local browser
  for browser in "${candidates[@]}"; do
    if command -v "$browser" >/dev/null 2>&1; then
      printf '%s' "$browser"
      return
    fi
  done

  # Snap-installed browsers (Ubuntu / Zorin)
  if [[ -d /snap/bin ]]; then
    for browser in "${candidates[@]}"; do
      if [[ -x "/snap/bin/$browser" ]]; then
        printf '%s' "/snap/bin/$browser"
        return
      fi
    done
  fi

  if [[ "$SKIP_BROWSER_CHECK" == "1" ]]; then
    printf '%s' "firefox"
    return
  fi

  die "No supported browser found. Install Firefox, Chromium, or another supported browser, or pass --browser."
}

BROWSER_CMD="$(find_browser)"
command -v install >/dev/null 2>&1 || die "install is required"
command -v flock >/dev/null 2>&1 || die "flock is required (provided by util-linux)"

# Summary
echo ""
echo "========================================="
echo "$(text cli_summary)"
echo "========================================="
echo "  $(text cli_user): $TARGET_USER"
echo "  $(text cli_home): $TARGET_HOME"
echo "  $(text cli_language): $ACTIVE_LANG"
echo "  $(text cli_browser): $BROWSER_CMD"
echo "  $(text cli_theme): $DEFAULT_THEME"
echo "  $(text cli_layout): $DEFAULT_LAYOUT"
echo "  $(text cli_mode): $DEFAULT_LAUNCH_MODE"
echo "  $(text cli_title): ${DEFAULT_TITLE:-$(text config_title)}"
echo "  $(text cli_parent): ${DEFAULT_PARENT_LABEL:-$(text parent_label)}"
echo "  $(text cli_exit): ${DEFAULT_EXIT_LABEL:-$(text exit_label)}"
echo "  $(text cli_shutdown_helper): $INSTALL_SHUTDOWN_HELPER"
echo "  $(text cli_recommended): $RECOMMENDED"
echo ""

if is_interactive; then
  prompt_read "$(text cli_proceed) " input
  case "$input" in
    [nN]*) echo "$(text cli_cancelled)"; exit 0 ;;
  esac
fi

APP_ROOT="$TARGET_HOME/.local/share/$APP_DIR_NAME"
if [[ -e "$APP_ROOT/package-managed" || -L "$APP_ROOT/package-managed" ]]; then
  die "This installation is managed by the system package manager"
fi
if [[ -e "/usr/share/$APP_ID/package-managed" || -L "/usr/share/$APP_ID/package-managed" ]]; then
  # The package builder uses a fresh disposable home. It must also work on a
  # build host with Cozy Kids installed, without permitting a family overwrite.
  if [[ "${COZY_KIDS_PACKAGE_STAGE:-0}" != "1" || -e "$APP_ROOT" ||
        -e "$TARGET_HOME/.config/$APP_ID/config.json" || -L "$TARGET_HOME/.config/$APP_ID/config.json" ]]; then
    die "This installation is managed by the system package manager"
  fi
fi
FRONTEND_DIR="$APP_ROOT/frontend"
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
FRONTEND_STYLES_FILE="$FRONTEND_DIR/styles.css"
FRONTEND_DESIGN_SYSTEM_FILE="$FRONTEND_DIR/design-system.css"
FRONTEND_STATE_FILE="$FRONTEND_DIR/state.js"
FRONTEND_LOCALIZATION_FILE="$FRONTEND_DIR/localization.js"
FRONTEND_LOCALES_DIR="$FRONTEND_DIR/locales"
FRONTEND_ICONS_FILE="$FRONTEND_DIR/icons.js"
FRONTEND_DIALOGS_FILE="$FRONTEND_DIR/dialogs.js"
FRONTEND_THEME_RUNTIME_FILE="$FRONTEND_DIR/theme-runtime.js"
FRONTEND_ACCESSIBILITY_RUNTIME_FILE="$FRONTEND_DIR/accessibility-runtime.js"
FRONTEND_FEEDBACK_RUNTIME_FILE="$FRONTEND_DIR/feedback-runtime.js"
FRONTEND_CELEBRATION_RUNTIME_FILE="$FRONTEND_DIR/celebration-runtime.js"
FRONTEND_TRANSITION_RUNTIME_FILE="$FRONTEND_DIR/transition-runtime.js"
FRONTEND_LAUNCHER_FILE="$FRONTEND_DIR/launcher-ui.js"
FRONTEND_PROFILES_FILE="$FRONTEND_DIR/profiles.js"
FRONTEND_SCHEDULE_FILE="$FRONTEND_DIR/schedule-controls.js"
FRONTEND_ACTIVITY_FILE="$FRONTEND_DIR/activity-dashboard.js"
FRONTEND_MEDIA_LIBRARY_STYLES_FILE="$FRONTEND_DIR/media-library.css"
FRONTEND_MEDIA_LIBRARY_FILE="$FRONTEND_DIR/media-library.js"
FRONTEND_SETTINGS_FILE="$FRONTEND_DIR/parent-settings.js"
FRONTEND_APP_CATALOG_FILE="$FRONTEND_DIR/app-catalog.js"
FRONTEND_FIRST_RUN_FILE="$FRONTEND_DIR/first-run.js"
FRONTEND_RUNTIME_FILE="$FRONTEND_DIR/runtime-controls.js"
MEDIA_FILE="$APP_ROOT/no-media.html"
MEDIA_LIBRARY_PAGE="$APP_ROOT/media.html"
UPDATE_SCRIPT="$APP_ROOT/update.sh"
AUTOSTART_FILE="$AUTOSTART_DIR/$AUTOSTART_FILE_ID"
DESKTOP_FILE="$DESKTOP_DIR/$DESKTOP_SHORTCUT_ID"
APP_DESKTOP_FILE="$TARGET_HOME/.local/share/applications/$DESKTOP_FILE_ID"
UNINSTALL_FILE="$APP_ROOT/uninstall.txt"
BACKUP_ROOT="$TARGET_HOME/.local/share/$APP_DIR_NAME-backups"
BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)"

mkdir -p "$APP_ROOT" "$FRONTEND_DIR" "$BIN_DIR" "$CFG_DIR" "$AUTOSTART_DIR" "$DESKTOP_DIR" "$CACHE_DIR" "$(dirname "$APP_DESKTOP_FILE")" "$BACKUP_ROOT"
[[ ! -L "$BACKUP_ROOT" ]] || die "Backup root must not be a symbolic link: $BACKUP_ROOT"
mkdir "$BACKUP_DIR" || die "Could not create a unique backup directory: $BACKUP_DIR"
chmod 0700 "$CFG_DIR" "$CACHE_DIR" "$BACKUP_ROOT" "$BACKUP_DIR"

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
  export DEFAULT_LAUNCH_MODE INSTALL_SHUTDOWN_HELPER ACTIVE_LANG ACTIVE_DIRECTION
  export DEFAULT_TITLE DEFAULT_PARENT_LABEL DEFAULT_EXIT_LABEL SHUTDOWN_LABEL
  export ADMIN_TITLE PLACEHOLDER_TITLE PLACEHOLDER_PARENT_LABEL PLACEHOLDER_EXIT_LABEL
  export LABEL_LAYOUT_LARGE LABEL_LAYOUT_SMALL LABEL_ADD_TILE LABEL_BACK LABEL_SAVE
  export LABEL_VISIBLE LABEL_SPECIAL_MEDIA LABEL_NO_APP LABEL_CUSTOM_CMD
  export LABEL_MOVE_UP LABEL_MOVE_DOWN LABEL_DELETE DEFAULT_NEW_TILE_LABEL
  export LABEL_COPY_COMMAND LABEL_CLOSE
  export LABEL_EXPORT_CONFIG LABEL_IMPORT_CONFIG LABEL_EXPORT_DIAGNOSTICS IMPORT_SUCCESS IMPORT_ERROR INVALID_CONFIG IMPORT_CONFIRM LABEL_PREVIEW_TITLE STARTING_APP STARTED_APP EMPTY_STATE_EMOJI EMPTY_STATE_TEXT FEEDBACK_OPTIONS SOUND_FEEDBACK SPEECH_FEEDBACK SPEECH_AVAILABLE SPEECH_UNAVAILABLE FEEDBACK_HINT CELEBRATION_OPTIONS CELEBRATION_ENABLED CELEBRATION_HINT ACCESSIBILITY_OPTIONS ACCESSIBILITY_LARGE_TEXT ACCESSIBILITY_HIGH_CONTRAST ACCESSIBILITY_REDUCED_MOTION ACCESSIBILITY_KEYBOARD_FOCUS ACCESSIBILITY_HINT
  export BACKUP_TITLE BACKUP_RESTORE BACKUP_EMPTY BACKUP_LOADING BACKUP_LOAD_ERROR BACKUP_RESTORING BACKUP_CONFIRM BACKUP_SUCCESS BACKUP_ERROR BACKUP_INSTALLER BACKUP_PRE_RESTORE BACKUP_PIN_PRESERVED
  export JSON_BROWSER_PAGE JSON_WEB_MODE_EMBEDDED JSON_WEB_MODE_EXTERNAL JSON_BROWSER_ALLOWLIST_LABEL JSON_BROWSER_BOUNDARY_EMBEDDED JSON_BROWSER_BOUNDARY_EXTERNAL JSON_BROWSER_ALLOWLIST_INVALID
  export BROWSER_BOUNDARY_TITLE BROWSER_BOUNDARY_BODY BROWSER_BOUNDARY_STAY
  export NO_MEDIA_TITLE NO_MEDIA_BODY NO_MEDIA_BACK
  export PIN_TITLE PIN_PLACEHOLDER PIN_WRONG PIN_SET PIN_CHANGE PIN_REMOVE PIN_CONFIRM PIN_MISMATCH PIN_SAVED PIN_REMOVED ADMIN_PAGE_PREV ADMIN_PAGE_NEXT
  export DEFAULT_TILE_PAINT DEFAULT_TILE_GAMES DEFAULT_TILE_MUSIC DEFAULT_TILE_BROWSER DEFAULT_BROWSER_URL
  export JSON_ADMIN_TITLE JSON_ADMIN_NAV_LABEL JSON_ADMIN_OVERVIEW JSON_ADMIN_CHILDREN JSON_ADMIN_APPS_MEDIA JSON_ADMIN_SCREEN_TIME JSON_ADMIN_APPEARANCE JSON_ADMIN_SYSTEM
  export JSON_APP_SEARCH_LABEL JSON_APP_FILTER_LABEL JSON_APP_FILTER_ALL JSON_APP_FILTER_VISIBLE JSON_APP_FILTER_HIDDEN JSON_APP_FILTER_EMPTY JSON_APP_FILTER_COUNT
  export JSON_APP_BULK_ACTIONS JSON_APP_BULK_SELECT_ALL JSON_APP_BULK_SELECTED JSON_APP_BULK_SHOW JSON_APP_BULK_HIDE JSON_APP_BULK_DELETE JSON_APP_BULK_DELETE_CONFIRM JSON_APP_SELECT_TILE
  export JSON_CONFIRM_TITLE JSON_CONFIRM_CANCEL JSON_CONFIRM_CONTINUE
  export STARTUP_LOADING
  export JSON_RETRY JSON_STARTUP_LOADING JSON_STARTUP_ERROR_TITLE JSON_STARTUP_ERROR JSON_SAVE_LOADING JSON_SAVE_ERROR
  export JSON_APP_CATALOG_LOADING JSON_APP_CATALOG_EMPTY JSON_APP_CATALOG_ERROR JSON_BROWSER_CATALOG_LOADING JSON_BROWSER_CATALOG_EMPTY JSON_BROWSER_CATALOG_ERROR
  export JSON_RECOMMENDATIONS_LOADING JSON_RECOMMENDATIONS_EMPTY JSON_RECOMMENDATIONS_ERROR
  export JSON_PLACEHOLDER_TITLE JSON_PLACEHOLDER_PARENT_LABEL JSON_PLACEHOLDER_EXIT_LABEL
  export JSON_ADD_TILE JSON_BACK JSON_SAVE JSON_VISIBLE JSON_SPECIAL_MEDIA
  export JSON_NO_APP JSON_CUSTOM_CMD JSON_MOVE_UP JSON_MOVE_DOWN JSON_DELETE JSON_NEW_TILE
  export JSON_PIN_TITLE JSON_PIN_PLACEHOLDER JSON_PIN_WRONG JSON_PIN_SET JSON_PIN_CHANGE JSON_PIN_REMOVE JSON_PIN_CONFIRM JSON_PIN_MISMATCH JSON_PIN_SAVED JSON_PIN_REMOVED JSON_ADMIN_PAGE_PREV JSON_ADMIN_PAGE_NEXT
  export JSON_UPDATE_CHECK JSON_UPDATE_AVAILABLE JSON_UPDATE_UP_TO_DATE JSON_UPDATE_LOADING JSON_UPDATE_ERROR JSON_VERSION_LABEL JSON_UPDATE_NOW JSON_UPDATE_PROGRESS JSON_UPDATE_CONFIRM
  export JSON_EXPORT_CONFIG JSON_IMPORT_CONFIG JSON_EXPORT_DIAGNOSTICS JSON_IMPORT_SUCCESS JSON_IMPORT_ERROR JSON_INVALID_CONFIG JSON_IMPORT_CONFIRM
  export JSON_BACKUP_TITLE JSON_BACKUP_RESTORE JSON_BACKUP_EMPTY JSON_BACKUP_LOADING JSON_BACKUP_LOAD_ERROR JSON_BACKUP_RESTORING JSON_BACKUP_CONFIRM JSON_BACKUP_SUCCESS JSON_BACKUP_ERROR JSON_BACKUP_INSTALLER JSON_BACKUP_PRE_RESTORE JSON_BACKUP_PIN_PRESERVED
  export JSON_ACTIVITY_TITLE JSON_ACTIVITY_HINT JSON_ACTIVITY_ENABLED JSON_ACTIVITY_ENABLED_STATUS JSON_ACTIVITY_DISABLED_STATUS JSON_ACTIVITY_TIME JSON_ACTIVITY_LAUNCHES JSON_ACTIVITY_RECENT JSON_ACTIVITY_EMPTY JSON_ACTIVITY_LOADING JSON_ACTIVITY_ERROR JSON_ACTIVITY_EXPORT JSON_ACTIVITY_CLEAR JSON_ACTIVITY_CLEAR_CONFIRM JSON_ACTIVITY_CLEAR_SUCCESS JSON_ACTIVITY_CLEAR_ERROR JSON_ACTIVITY_UNKNOWN_PROFILE JSON_ACTIVITY_UNKNOWN_APP JSON_ACTIVITY_LESS_MINUTE JSON_ACTIVITY_MINUTES JSON_ACTIVITY_HOURS_MINUTES
  export UPDATE_CHECK UPDATE_AVAILABLE UPDATE_UP_TO_DATE UPDATE_ERROR VERSION_LABEL UPDATE_NOW UPDATE_PROGRESS UPDATE_CONFIRM
  export RUNTIME_FAILURE_TITLE RUNTIME_FAILURE_BODY
  export RECOMMENDED_TITLE RECOMMENDED_INSTALLED RECOMMENDED_NOT_INSTALLED RECOMMENDED_PROMPT
  export JSON_RECOMMENDED_TITLE JSON_RECOMMENDED_INSTALLED JSON_RECOMMENDED_NOT_INSTALLED JSON_RECOMMENDED_PROMPT
  export JSON_APP_BROWSER_TITLE JSON_INSTALL JSON_ADDED JSON_INSTALLED JSON_NOT_INSTALLED JSON_COPY_COMMAND JSON_COMMAND_COPIED JSON_INSTALL_STARTED JSON_INSTALL_MANUAL JSON_CLOSE
  export JSON_INSTALL_LOADING JSON_INSTALL_ERROR JSON_INSTALL_UNSUPPORTED JSON_UPDATE_START_ERROR
  export JSON_PACKAGE_CHECK JSON_PACKAGE_REVIEW JSON_PACKAGE_DOWNLOAD JSON_PACKAGE_COUNT JSON_PACKAGE_UNKNOWN_SIZE JSON_PACKAGE_CONSENT JSON_PACKAGE_INSTALLING JSON_PACKAGE_WAITING JSON_PACKAGE_AUTH JSON_PACKAGE_DOWNLOADING JSON_PACKAGE_COMPLETE JSON_PACKAGE_ADD JSON_PACKAGE_KEEP_OPEN JSON_PACKAGE_STATUS JSON_PACKAGE_NETWORK JSON_PACKAGE_AUTHORIZATION JSON_PACKAGE_BUSY JSON_PACKAGE_NOT_FOUND JSON_PACKAGE_UNSUPPORTED JSON_PACKAGE_CHANGES JSON_PACKAGE_CHANGED JSON_PACKAGE_FAILED JSON_PACKAGE_INTERRUPTED JSON_PACKAGE_STORAGE JSON_PACKAGE_LIST JSON_PACKAGE_CONFIRM JSON_PACKAGE_ADD_ERROR
  export TIMER_LABEL TIMER_OFF TIMER_15 TIMER_30 TIMER_60 TIMER_CUSTOM TIMER_START TIMER_STOP TIMER_ACTIVE TIMER_EXPIRED TIMER_REMAINING TIMER_WARNING_TITLE TIMER_WARNING_TEXT TIMER_ENTER_PIN TIMER_EXTEND TIMER_EXIT TIMER_WRONG_PIN TIMER_EXTENDED TIMER_EXPIRED_TITLE TIMER_EXPIRED_BODY TIMER_MINUTES
  export JSON_TIMER_LABEL JSON_TIMER_OFF JSON_TIMER_15 JSON_TIMER_30 JSON_TIMER_60 JSON_TIMER_MINUTES JSON_TIMER_CUSTOM JSON_TIMER_START JSON_TIMER_STOP JSON_TIMER_ACTIVE JSON_TIMER_EXPIRED JSON_TIMER_REMAINING JSON_TIMER_WARNING_TITLE JSON_TIMER_WARNING_TEXT JSON_TIMER_ENTER_PIN JSON_TIMER_EXTEND JSON_TIMER_EXIT JSON_TIMER_WRONG_PIN JSON_TIMER_EXTENDED JSON_STARTING_APP JSON_STARTED_APP JSON_EMPTY_STATE_EMOJI JSON_EMPTY_STATE_TEXT JSON_PREVIEW_TITLE JSON_FEEDBACK_OPTIONS JSON_SOUND_FEEDBACK JSON_SPEECH_FEEDBACK JSON_SPEECH_AVAILABLE JSON_SPEECH_UNAVAILABLE JSON_FEEDBACK_HINT JSON_CELEBRATION_OPTIONS JSON_CELEBRATION_ENABLED JSON_CELEBRATION_HINT JSON_ACCESSIBILITY_OPTIONS JSON_ACCESSIBILITY_LARGE_TEXT JSON_ACCESSIBILITY_HIGH_CONTRAST JSON_ACCESSIBILITY_REDUCED_MOTION JSON_ACCESSIBILITY_KEYBOARD_FOCUS JSON_ACCESSIBILITY_HINT
  export JSON_SCHEDULE_WEEKLY_TITLE JSON_SCHEDULE_WEEKLY_HINT JSON_SCHEDULE_ENABLED JSON_SCHEDULE_APP_TITLE JSON_SCHEDULE_APP_HINT JSON_SCHEDULE_SELECT_APP JSON_SCHEDULE_ADD_WINDOW JSON_SCHEDULE_REMOVE_WINDOW JSON_SCHEDULE_START JSON_SCHEDULE_END JSON_SCHEDULE_CLEAR_APP JSON_SCHEDULE_NO_WINDOWS JSON_SCHEDULE_BLOCKED_TITLE JSON_SCHEDULE_PROFILE_BLOCKED JSON_SCHEDULE_APP_BLOCKED JSON_SCHEDULE_OPEN_PARENTS
  export JSON_WEEKDAY_MONDAY JSON_WEEKDAY_TUESDAY JSON_WEEKDAY_WEDNESDAY JSON_WEEKDAY_THURSDAY JSON_WEEKDAY_FRIDAY JSON_WEEKDAY_SATURDAY JSON_WEEKDAY_SUNDAY
  export JSON_CATALOG_ALL
  export JSON_CATALOG_CREATIVE
  export JSON_CATALOG_LEARNING
  export JSON_CATALOG_GAMES
  export JSON_CATALOG_WEB
  export JSON_CATALOG_REFRESH
  export JSON_CATALOG_SEARCH
  export JSON_CATALOG_CATEGORY
  export JSON_CATALOG_STATUS
  export JSON_CATALOG_COUNT
  export JSON_CATALOG_NO_MATCHES
  export JSON_CATALOG_HINT
  export JSON_CATALOG_DETAILS
  export JSON_CATALOG_UNKNOWN
  export JSON_CATALOG_AGE
  export JSON_CATALOG_OFFLINE
  export JSON_CATALOG_OFFLINE_YES
  export JSON_CATALOG_OFFLINE_PARTIAL
  export JSON_CATALOG_OFFLINE_NO
  export JSON_CATALOG_LICENSE
  export JSON_CATALOG_INPUT
  export JSON_CATALOG_MOUSE
  export JSON_CATALOG_KEYBOARD
  export JSON_CATALOG_TOUCH
  export JSON_CATALOG_NETWORK
  export JSON_CATALOG_WEB_PRIVACY
  export JSON_CATALOG_SOURCE
  export JSON_CATALOG_REVIEWED
  export JSON_LANGUAGE_REGISTRY
  export JSON_SETUP_LOCALE
  export JSON_MEDIA_LOCALE
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

ACTIVE_DIRECTION="$(python3 "$SRC_DIR/language_registry.py" --direction "$ACTIVE_LANG")" || die "Could not resolve language direction"
JSON_SETUP_LOCALE="$(python3 - "$SRC_DIR/frontend/locales/$ACTIVE_LANG.json" <<'PY'
import json
from pathlib import Path
import sys

locale = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
keys = (
    "firstRun", "profiles", "defaultTitle", "defaultParentLabel", "defaultExitLabel",
    "defaultShutdownLabel", "tilePaint", "tileGames", "tileMusic", "tileBrowser",
    "themes", "counts", "browserHint", "browserLabel", "languageLabel", "paletteBgStart", "paletteBgEnd",
    "paletteText", "paletteButton", "paletteCard", "packageMaintenance", "budget", "updateTrack",
)
print(json.dumps({key: value for key, value in locale.items() if key in keys or key.startswith(("folder", "flatpak", "package")) or key == "catalogUseSource"}, ensure_ascii=True))
PY
)" || die "Could not prepare setup and profile translations for $ACTIVE_LANG"
JSON_MEDIA_LOCALE="$(python3 - "$SRC_DIR/frontend/locales/$ACTIVE_LANG.json" <<'PY'
import json
from pathlib import Path
import sys

locale = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps({key: value for key, value in locale.items() if key.startswith(("mediaLibrary", "retro"))}))
PY
)" || die "Could not prepare media translations for $ACTIVE_LANG"

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
ADMIN_NAV_LABEL="$(text admin_nav_label)"
ADMIN_OVERVIEW="$(text admin_overview)"
ADMIN_CHILDREN="$(text admin_children)"
ADMIN_APPS_MEDIA="$(text admin_apps_media)"
ADMIN_SCREEN_TIME="$(text admin_screen_time)"
ADMIN_APPEARANCE="$(text admin_appearance)"
ADMIN_SYSTEM="$(text admin_system)"
APP_SEARCH_LABEL="$(text app_search_label)"
APP_FILTER_LABEL="$(text app_filter_label)"
APP_FILTER_ALL="$(text app_filter_all)"
APP_FILTER_VISIBLE="$(text app_filter_visible)"
APP_FILTER_HIDDEN="$(text app_filter_hidden)"
APP_FILTER_EMPTY="$(text app_filter_empty)"
APP_FILTER_COUNT="$(text app_filter_count)"
APP_BULK_ACTIONS="$(text app_bulk_actions)"
APP_BULK_SELECT_ALL="$(text app_bulk_select_all)"
APP_BULK_SELECTED="$(text app_bulk_selected)"
APP_BULK_SHOW="$(text app_bulk_show)"
APP_BULK_HIDE="$(text app_bulk_hide)"
APP_BULK_DELETE="$(text app_bulk_delete)"
APP_BULK_DELETE_CONFIRM="$(text app_bulk_delete_confirm)"
APP_SELECT_TILE="$(text app_select_tile)"
CONFIRM_TITLE="$(text confirm_title)"
CONFIRM_CANCEL="$(text confirm_cancel)"
CONFIRM_CONTINUE="$(text confirm_continue)"
RETRY="$(text retry)"
STARTUP_LOADING="$(text startup_loading)"
STARTUP_ERROR_TITLE="$(text startup_error_title)"
STARTUP_ERROR="$(text startup_error)"
SAVE_LOADING="$(text save_loading)"
SAVE_ERROR="$(text save_error)"
APP_CATALOG_LOADING="$(text app_catalog_loading)"
APP_CATALOG_EMPTY="$(text app_catalog_empty)"
APP_CATALOG_ERROR="$(text app_catalog_error)"
BROWSER_CATALOG_LOADING="$(text browser_catalog_loading)"
BROWSER_CATALOG_EMPTY="$(text browser_catalog_empty)"
BROWSER_CATALOG_ERROR="$(text browser_catalog_error)"
RECOMMENDATIONS_LOADING="$(text recommendations_loading)"
RECOMMENDATIONS_EMPTY="$(text recommendations_empty)"
RECOMMENDATIONS_ERROR="$(text recommendations_error)"
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
UPDATE_LOADING="$(text update_loading)"
UPDATE_ERROR="$(text update_error)"
VERSION_LABEL="$(text version_label)"
UPDATE_NOW="$(text update_now)"
UPDATE_PROGRESS="$(text update_progress)"
UPDATE_CONFIRM="$(text update_confirm)"
RUNTIME_FAILURE_TITLE="$(text runtime_failure_title)"
RUNTIME_FAILURE_BODY="$(text runtime_failure_body)"
DEFAULT_TILE_PAINT="$(text tile_paint)"
DEFAULT_TILE_GAMES="$(text tile_games)"
DEFAULT_TILE_MUSIC="$(text tile_music)"
DEFAULT_TILE_BROWSER="$(text tile_browser)"
DEFAULT_BROWSER_URL="$(text browser_url)"
RECOMMENDED_TITLE="$(text recommended_title)"
RECOMMENDED_INSTALLED="$(text recommended_installed)"
RECOMMENDED_NOT_INSTALLED="$(text recommended_not_installed)"
RECOMMENDED_PROMPT="$(text recommended_prompt)"
APP_BROWSER_TITLE="$(text app_browser_title)"
BROWSER_PAGE="$(text browser_page)"
WEB_MODE_EMBEDDED="$(text web_mode_embedded)"
WEB_MODE_EXTERNAL="$(text web_mode_external)"
BROWSER_ALLOWLIST_LABEL="$(text browser_allowlist_label)"
BROWSER_BOUNDARY_EMBEDDED="$(text browser_boundary_embedded)"
BROWSER_BOUNDARY_EXTERNAL="$(text browser_boundary_external)"
BROWSER_ALLOWLIST_INVALID="$(text browser_allowlist_invalid)"
BROWSER_BOUNDARY_TITLE="$(text browser_boundary_title)"
BROWSER_BOUNDARY_BODY="$(text browser_boundary_body)"
BROWSER_BOUNDARY_STAY="$(text browser_boundary_stay)"
LABEL_INSTALL="$(text install)"
LABEL_ADDED="$(text added)"
LABEL_INSTALLED="$(text installed)"
LABEL_NOT_INSTALLED="$(text not_installed)"
LABEL_COPY_COMMAND="$(text copy_command)"
LABEL_COMMAND_COPIED="$(text command_copied)"
LABEL_INSTALL_STARTED="$(text install_started)"
LABEL_INSTALL_MANUAL="$(text install_manual)"
INSTALL_LOADING="$(text install_loading)"
INSTALL_ERROR="$(text install_error)"
INSTALL_UNSUPPORTED="$(text install_unsupported)"
UPDATE_START_ERROR="$(text update_start_error)"
LABEL_CLOSE="$(text close)"
LABEL_EXPORT_CONFIG="$(text export_config)"
LABEL_IMPORT_CONFIG="$(text import_config)"
LABEL_EXPORT_DIAGNOSTICS="$(text export_diagnostics)"
IMPORT_SUCCESS="$(text import_success)"
IMPORT_ERROR="$(text import_error)"
INVALID_CONFIG="$(text invalid_config)"
IMPORT_CONFIRM="$(text import_confirm)"
BACKUP_TITLE="$(text backup_title)"
BACKUP_RESTORE="$(text backup_restore)"
BACKUP_EMPTY="$(text backup_empty)"
BACKUP_LOADING="$(text backup_loading)"
BACKUP_LOAD_ERROR="$(text backup_load_error)"
BACKUP_RESTORING="$(text backup_restoring)"
BACKUP_CONFIRM="$(text backup_confirm)"
BACKUP_SUCCESS="$(text backup_success)"
BACKUP_ERROR="$(text backup_error)"
BACKUP_INSTALLER="$(text backup_installer)"
BACKUP_PRE_RESTORE="$(text backup_pre_restore)"
BACKUP_PIN_PRESERVED="$(text backup_pin_preserved)"
ACTIVITY_TITLE="$(text activity_title)"
ACTIVITY_HINT="$(text activity_hint)"
ACTIVITY_ENABLED="$(text activity_enabled)"
ACTIVITY_ENABLED_STATUS="$(text activity_enabled_status)"
ACTIVITY_DISABLED_STATUS="$(text activity_disabled_status)"
ACTIVITY_TIME="$(text activity_time)"
ACTIVITY_LAUNCHES="$(text activity_launches)"
ACTIVITY_RECENT="$(text activity_recent)"
ACTIVITY_EMPTY="$(text activity_empty)"
ACTIVITY_LOADING="$(text activity_loading)"
ACTIVITY_ERROR="$(text activity_error)"
ACTIVITY_EXPORT="$(text activity_export)"
ACTIVITY_CLEAR="$(text activity_clear)"
ACTIVITY_CLEAR_CONFIRM="$(text activity_clear_confirm)"
ACTIVITY_CLEAR_SUCCESS="$(text activity_clear_success)"
ACTIVITY_CLEAR_ERROR="$(text activity_clear_error)"
ACTIVITY_UNKNOWN_PROFILE="$(text activity_unknown_profile)"
ACTIVITY_UNKNOWN_APP="$(text activity_unknown_app)"
ACTIVITY_LESS_MINUTE="$(text activity_less_minute)"
ACTIVITY_MINUTES="$(text activity_minutes)"
ACTIVITY_HOURS_MINUTES="$(text activity_hours_minutes)"
TIMER_LABEL="$(text timer_label)"
TIMER_OFF="$(text timer_off)"
TIMER_15="$(text timer_15)"
TIMER_30="$(text timer_30)"
TIMER_60="$(text timer_60)"
TIMER_CUSTOM="$(text timer_custom)"
TIMER_START="$(text timer_start)"
TIMER_STOP="$(text timer_stop)"
TIMER_ACTIVE="$(text timer_active)"
TIMER_EXPIRED="$(text timer_expired)"
TIMER_REMAINING="$(text timer_remaining)"
TIMER_WARNING_TITLE="$(text timer_warning_title)"
TIMER_WARNING_TEXT="$(text timer_warning_text)"
TIMER_ENTER_PIN="$(text timer_enter_pin)"
TIMER_EXTEND="$(text timer_extend)"
TIMER_EXIT="$(text timer_exit)"
TIMER_WRONG_PIN="$(text timer_wrong_pin)"
TIMER_EXTENDED="$(text timer_extended)"
TIMER_EXPIRED_TITLE="$(text timer_expired_title)"
TIMER_EXPIRED_BODY="$(text timer_expired_body)"
TIMER_MINUTES="$(text timer_minutes)"
SCHEDULE_WEEKLY_TITLE="$(text schedule_weekly_title)"
SCHEDULE_WEEKLY_HINT="$(text schedule_weekly_hint)"
SCHEDULE_ENABLED="$(text schedule_enabled)"
SCHEDULE_APP_TITLE="$(text schedule_app_title)"
SCHEDULE_APP_HINT="$(text schedule_app_hint)"
SCHEDULE_SELECT_APP="$(text schedule_select_app)"
SCHEDULE_ADD_WINDOW="$(text schedule_add_window)"
SCHEDULE_REMOVE_WINDOW="$(text schedule_remove_window)"
SCHEDULE_START="$(text schedule_start)"
SCHEDULE_END="$(text schedule_end)"
SCHEDULE_CLEAR_APP="$(text schedule_clear_app)"
SCHEDULE_NO_WINDOWS="$(text schedule_no_windows)"
SCHEDULE_BLOCKED_TITLE="$(text schedule_blocked_title)"
SCHEDULE_PROFILE_BLOCKED="$(text schedule_profile_blocked)"
SCHEDULE_APP_BLOCKED="$(text schedule_app_blocked)"
SCHEDULE_OPEN_PARENTS="$(text schedule_open_parents)"
WEEKDAY_MONDAY="$(text weekday_monday)"
WEEKDAY_TUESDAY="$(text weekday_tuesday)"
WEEKDAY_WEDNESDAY="$(text weekday_wednesday)"
WEEKDAY_THURSDAY="$(text weekday_thursday)"
WEEKDAY_FRIDAY="$(text weekday_friday)"
WEEKDAY_SATURDAY="$(text weekday_saturday)"
WEEKDAY_SUNDAY="$(text weekday_sunday)"
LABEL_PREVIEW_TITLE="$(text preview_title)"
STARTING_APP="$(text starting_app)"
STARTED_APP="$(text started_app)"
EMPTY_STATE_EMOJI="$(text empty_state_emoji)"
EMPTY_STATE_TEXT="$(text empty_state_text)"
PREVIEW_TITLE="$(text preview_title)"
FEEDBACK_OPTIONS="$(text feedback_options)"
SOUND_FEEDBACK="$(text sound_feedback)"
SPEECH_FEEDBACK="$(text speech_feedback)"
SPEECH_AVAILABLE="$(text speech_available)"
SPEECH_UNAVAILABLE="$(text speech_unavailable)"
FEEDBACK_HINT="$(text feedback_hint)"
CELEBRATION_OPTIONS="$(text celebration_options)"
CELEBRATION_ENABLED="$(text celebration_enabled)"
CELEBRATION_HINT="$(text celebration_hint)"
ACCESSIBILITY_OPTIONS="$(text accessibility_options)"
ACCESSIBILITY_LARGE_TEXT="$(text accessibility_large_text)"
ACCESSIBILITY_HIGH_CONTRAST="$(text accessibility_high_contrast)"
ACCESSIBILITY_REDUCED_MOTION="$(text accessibility_reduced_motion)"
ACCESSIBILITY_KEYBOARD_FOCUS="$(text accessibility_keyboard_focus)"
ACCESSIBILITY_HINT="$(text accessibility_hint)"

JSON_ADMIN_TITLE="$(json_text "$ADMIN_TITLE")"
JSON_ADMIN_NAV_LABEL="$(json_text "$ADMIN_NAV_LABEL")"
JSON_ADMIN_OVERVIEW="$(json_text "$ADMIN_OVERVIEW")"
JSON_ADMIN_CHILDREN="$(json_text "$ADMIN_CHILDREN")"
JSON_ADMIN_APPS_MEDIA="$(json_text "$ADMIN_APPS_MEDIA")"
JSON_ADMIN_SCREEN_TIME="$(json_text "$ADMIN_SCREEN_TIME")"
JSON_ADMIN_APPEARANCE="$(json_text "$ADMIN_APPEARANCE")"
JSON_ADMIN_SYSTEM="$(json_text "$ADMIN_SYSTEM")"
JSON_APP_SEARCH_LABEL="$(json_text "$APP_SEARCH_LABEL")"
JSON_APP_FILTER_LABEL="$(json_text "$APP_FILTER_LABEL")"
JSON_APP_FILTER_ALL="$(json_text "$APP_FILTER_ALL")"
JSON_APP_FILTER_VISIBLE="$(json_text "$APP_FILTER_VISIBLE")"
JSON_APP_FILTER_HIDDEN="$(json_text "$APP_FILTER_HIDDEN")"
JSON_APP_FILTER_EMPTY="$(json_text "$APP_FILTER_EMPTY")"
JSON_APP_FILTER_COUNT="$(json_text "$APP_FILTER_COUNT")"
JSON_APP_BULK_ACTIONS="$(json_text "$APP_BULK_ACTIONS")"
JSON_APP_BULK_SELECT_ALL="$(json_text "$APP_BULK_SELECT_ALL")"
JSON_APP_BULK_SELECTED="$(json_text "$APP_BULK_SELECTED")"
JSON_APP_BULK_SHOW="$(json_text "$APP_BULK_SHOW")"
JSON_APP_BULK_HIDE="$(json_text "$APP_BULK_HIDE")"
JSON_APP_BULK_DELETE="$(json_text "$APP_BULK_DELETE")"
JSON_APP_BULK_DELETE_CONFIRM="$(json_text "$APP_BULK_DELETE_CONFIRM")"
JSON_APP_SELECT_TILE="$(json_text "$APP_SELECT_TILE")"
JSON_CONFIRM_TITLE="$(json_text "$CONFIRM_TITLE")"
JSON_CONFIRM_CANCEL="$(json_text "$CONFIRM_CANCEL")"
JSON_CONFIRM_CONTINUE="$(json_text "$CONFIRM_CONTINUE")"
JSON_RETRY="$(json_text "$RETRY")"
JSON_STARTUP_LOADING="$(json_text "$STARTUP_LOADING")"
JSON_STARTUP_ERROR_TITLE="$(json_text "$STARTUP_ERROR_TITLE")"
JSON_STARTUP_ERROR="$(json_text "$STARTUP_ERROR")"
JSON_SAVE_LOADING="$(json_text "$SAVE_LOADING")"
JSON_SAVE_ERROR="$(json_text "$SAVE_ERROR")"
JSON_APP_CATALOG_LOADING="$(json_text "$APP_CATALOG_LOADING")"
JSON_APP_CATALOG_EMPTY="$(json_text "$APP_CATALOG_EMPTY")"
JSON_APP_CATALOG_ERROR="$(json_text "$APP_CATALOG_ERROR")"
JSON_BROWSER_CATALOG_LOADING="$(json_text "$BROWSER_CATALOG_LOADING")"
JSON_BROWSER_CATALOG_EMPTY="$(json_text "$BROWSER_CATALOG_EMPTY")"
JSON_BROWSER_CATALOG_ERROR="$(json_text "$BROWSER_CATALOG_ERROR")"
JSON_RECOMMENDATIONS_LOADING="$(json_text "$RECOMMENDATIONS_LOADING")"
JSON_RECOMMENDATIONS_EMPTY="$(json_text "$RECOMMENDATIONS_EMPTY")"
JSON_RECOMMENDATIONS_ERROR="$(json_text "$RECOMMENDATIONS_ERROR")"
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
JSON_UPDATE_LOADING="$(json_text "$UPDATE_LOADING")"
JSON_UPDATE_ERROR="$(json_text "$UPDATE_ERROR")"
JSON_VERSION_LABEL="$(json_text "$VERSION_LABEL")"
JSON_UPDATE_NOW="$(json_text "$UPDATE_NOW")"
JSON_UPDATE_PROGRESS="$(json_text "$UPDATE_PROGRESS")"
JSON_UPDATE_CONFIRM="$(json_text "$UPDATE_CONFIRM")"
JSON_RECOMMENDED_TITLE="$(json_text "$RECOMMENDED_TITLE")"
JSON_RECOMMENDED_INSTALLED="$(json_text "$RECOMMENDED_INSTALLED")"
JSON_RECOMMENDED_NOT_INSTALLED="$(json_text "$RECOMMENDED_NOT_INSTALLED")"
JSON_RECOMMENDED_PROMPT="$(json_text "$RECOMMENDED_PROMPT")"
JSON_APP_BROWSER_TITLE="$(json_text "$APP_BROWSER_TITLE")"
JSON_BROWSER_PAGE="$(json_text "$BROWSER_PAGE")"
JSON_WEB_MODE_EMBEDDED="$(json_text "$WEB_MODE_EMBEDDED")"
JSON_WEB_MODE_EXTERNAL="$(json_text "$WEB_MODE_EXTERNAL")"
JSON_BROWSER_ALLOWLIST_LABEL="$(json_text "$BROWSER_ALLOWLIST_LABEL")"
JSON_BROWSER_BOUNDARY_EMBEDDED="$(json_text "$BROWSER_BOUNDARY_EMBEDDED")"
JSON_BROWSER_BOUNDARY_EXTERNAL="$(json_text "$BROWSER_BOUNDARY_EXTERNAL")"
JSON_BROWSER_ALLOWLIST_INVALID="$(json_text "$BROWSER_ALLOWLIST_INVALID")"
JSON_INSTALL="$(json_text "$LABEL_INSTALL")"
JSON_ADDED="$(json_text "$LABEL_ADDED")"
JSON_INSTALLED="$(json_text "$LABEL_INSTALLED")"
JSON_NOT_INSTALLED="$(json_text "$LABEL_NOT_INSTALLED")"
JSON_COPY_COMMAND="$(json_text "$LABEL_COPY_COMMAND")"
JSON_COMMAND_COPIED="$(json_text "$LABEL_COMMAND_COPIED")"
JSON_INSTALL_STARTED="$(json_text "$LABEL_INSTALL_STARTED")"
JSON_INSTALL_MANUAL="$(json_text "$LABEL_INSTALL_MANUAL")"
JSON_INSTALL_LOADING="$(json_text "$INSTALL_LOADING")"
JSON_INSTALL_ERROR="$(json_text "$INSTALL_ERROR")"
JSON_INSTALL_UNSUPPORTED="$(json_text "$INSTALL_UNSUPPORTED")"
JSON_UPDATE_START_ERROR="$(json_text "$UPDATE_START_ERROR")"
PACKAGE_CHECK="$(text package_check)"
JSON_PACKAGE_CHECK="$(json_text "$PACKAGE_CHECK")"
PACKAGE_REVIEW="$(text package_review)"
JSON_PACKAGE_REVIEW="$(json_text "$PACKAGE_REVIEW")"
PACKAGE_DOWNLOAD="$(text package_download)"
JSON_PACKAGE_DOWNLOAD="$(json_text "$PACKAGE_DOWNLOAD")"
PACKAGE_COUNT="$(text package_count)"
JSON_PACKAGE_COUNT="$(json_text "$PACKAGE_COUNT")"
PACKAGE_UNKNOWN_SIZE="$(text package_unknown_size)"
JSON_PACKAGE_UNKNOWN_SIZE="$(json_text "$PACKAGE_UNKNOWN_SIZE")"
PACKAGE_CONSENT="$(text package_consent)"
JSON_PACKAGE_CONSENT="$(json_text "$PACKAGE_CONSENT")"
PACKAGE_INSTALLING="$(text package_installing)"
JSON_PACKAGE_INSTALLING="$(json_text "$PACKAGE_INSTALLING")"
PACKAGE_WAITING="$(text package_waiting)"
JSON_PACKAGE_WAITING="$(json_text "$PACKAGE_WAITING")"
PACKAGE_AUTH="$(text package_auth)"
JSON_PACKAGE_AUTH="$(json_text "$PACKAGE_AUTH")"
PACKAGE_DOWNLOADING="$(text package_downloading)"
JSON_PACKAGE_DOWNLOADING="$(json_text "$PACKAGE_DOWNLOADING")"
PACKAGE_COMPLETE="$(text package_complete)"
JSON_PACKAGE_COMPLETE="$(json_text "$PACKAGE_COMPLETE")"
PACKAGE_ADD="$(text package_add)"
JSON_PACKAGE_ADD="$(json_text "$PACKAGE_ADD")"
PACKAGE_KEEP_OPEN="$(text package_keep_open)"
JSON_PACKAGE_KEEP_OPEN="$(json_text "$PACKAGE_KEEP_OPEN")"
PACKAGE_STATUS="$(text package_status)"
JSON_PACKAGE_STATUS="$(json_text "$PACKAGE_STATUS")"
PACKAGE_NETWORK="$(text package_network)"
JSON_PACKAGE_NETWORK="$(json_text "$PACKAGE_NETWORK")"
PACKAGE_AUTHORIZATION="$(text package_authorization)"
JSON_PACKAGE_AUTHORIZATION="$(json_text "$PACKAGE_AUTHORIZATION")"
PACKAGE_BUSY="$(text package_busy)"
JSON_PACKAGE_BUSY="$(json_text "$PACKAGE_BUSY")"
PACKAGE_NOT_FOUND="$(text package_not_found)"
JSON_PACKAGE_NOT_FOUND="$(json_text "$PACKAGE_NOT_FOUND")"
PACKAGE_UNSUPPORTED="$(text package_unsupported)"
JSON_PACKAGE_UNSUPPORTED="$(json_text "$PACKAGE_UNSUPPORTED")"
PACKAGE_CHANGES="$(text package_changes)"
JSON_PACKAGE_CHANGES="$(json_text "$PACKAGE_CHANGES")"
PACKAGE_CHANGED="$(text package_changed)"
JSON_PACKAGE_CHANGED="$(json_text "$PACKAGE_CHANGED")"
PACKAGE_FAILED="$(text package_failed)"
JSON_PACKAGE_FAILED="$(json_text "$PACKAGE_FAILED")"
PACKAGE_INTERRUPTED="$(text package_interrupted)"
JSON_PACKAGE_INTERRUPTED="$(json_text "$PACKAGE_INTERRUPTED")"
PACKAGE_STORAGE="$(text package_storage)"
JSON_PACKAGE_STORAGE="$(json_text "$PACKAGE_STORAGE")"
PACKAGE_LIST="$(text package_list)"
JSON_PACKAGE_LIST="$(json_text "$PACKAGE_LIST")"
PACKAGE_CONFIRM="$(text package_confirm)"
JSON_PACKAGE_CONFIRM="$(json_text "$PACKAGE_CONFIRM")"
PACKAGE_ADD_ERROR="$(text package_add_error)"
JSON_PACKAGE_ADD_ERROR="$(json_text "$PACKAGE_ADD_ERROR")"
JSON_CLOSE="$(json_text "$LABEL_CLOSE")"
JSON_EXPORT_CONFIG="$(json_text "$LABEL_EXPORT_CONFIG")"
JSON_IMPORT_CONFIG="$(json_text "$LABEL_IMPORT_CONFIG")"
JSON_EXPORT_DIAGNOSTICS="$(json_text "$LABEL_EXPORT_DIAGNOSTICS")"
JSON_IMPORT_SUCCESS="$(json_text "$IMPORT_SUCCESS")"
JSON_IMPORT_ERROR="$(json_text "$IMPORT_ERROR")"
JSON_INVALID_CONFIG="$(json_text "$INVALID_CONFIG")"
JSON_IMPORT_CONFIRM="$(json_text "$IMPORT_CONFIRM")"
JSON_BACKUP_TITLE="$(json_text "$BACKUP_TITLE")"
JSON_BACKUP_RESTORE="$(json_text "$BACKUP_RESTORE")"
JSON_BACKUP_EMPTY="$(json_text "$BACKUP_EMPTY")"
JSON_BACKUP_LOADING="$(json_text "$BACKUP_LOADING")"
JSON_BACKUP_LOAD_ERROR="$(json_text "$BACKUP_LOAD_ERROR")"
JSON_BACKUP_RESTORING="$(json_text "$BACKUP_RESTORING")"
JSON_BACKUP_CONFIRM="$(json_text "$BACKUP_CONFIRM")"
JSON_BACKUP_SUCCESS="$(json_text "$BACKUP_SUCCESS")"
JSON_BACKUP_ERROR="$(json_text "$BACKUP_ERROR")"
JSON_BACKUP_INSTALLER="$(json_text "$BACKUP_INSTALLER")"
JSON_BACKUP_PRE_RESTORE="$(json_text "$BACKUP_PRE_RESTORE")"
JSON_BACKUP_PIN_PRESERVED="$(json_text "$BACKUP_PIN_PRESERVED")"
JSON_ACTIVITY_TITLE="$(json_text "$ACTIVITY_TITLE")"
JSON_ACTIVITY_HINT="$(json_text "$ACTIVITY_HINT")"
JSON_ACTIVITY_ENABLED="$(json_text "$ACTIVITY_ENABLED")"
JSON_ACTIVITY_ENABLED_STATUS="$(json_text "$ACTIVITY_ENABLED_STATUS")"
JSON_ACTIVITY_DISABLED_STATUS="$(json_text "$ACTIVITY_DISABLED_STATUS")"
JSON_ACTIVITY_TIME="$(json_text "$ACTIVITY_TIME")"
JSON_ACTIVITY_LAUNCHES="$(json_text "$ACTIVITY_LAUNCHES")"
JSON_ACTIVITY_RECENT="$(json_text "$ACTIVITY_RECENT")"
JSON_ACTIVITY_EMPTY="$(json_text "$ACTIVITY_EMPTY")"
JSON_ACTIVITY_LOADING="$(json_text "$ACTIVITY_LOADING")"
JSON_ACTIVITY_ERROR="$(json_text "$ACTIVITY_ERROR")"
JSON_ACTIVITY_EXPORT="$(json_text "$ACTIVITY_EXPORT")"
JSON_ACTIVITY_CLEAR="$(json_text "$ACTIVITY_CLEAR")"
JSON_ACTIVITY_CLEAR_CONFIRM="$(json_text "$ACTIVITY_CLEAR_CONFIRM")"
JSON_ACTIVITY_CLEAR_SUCCESS="$(json_text "$ACTIVITY_CLEAR_SUCCESS")"
JSON_ACTIVITY_CLEAR_ERROR="$(json_text "$ACTIVITY_CLEAR_ERROR")"
JSON_ACTIVITY_UNKNOWN_PROFILE="$(json_text "$ACTIVITY_UNKNOWN_PROFILE")"
JSON_ACTIVITY_UNKNOWN_APP="$(json_text "$ACTIVITY_UNKNOWN_APP")"
JSON_ACTIVITY_LESS_MINUTE="$(json_text "$ACTIVITY_LESS_MINUTE")"
JSON_ACTIVITY_MINUTES="$(json_text "$ACTIVITY_MINUTES")"
JSON_ACTIVITY_HOURS_MINUTES="$(json_text "$ACTIVITY_HOURS_MINUTES")"
JSON_TIMER_LABEL="$(json_text "$TIMER_LABEL")"
JSON_TIMER_OFF="$(json_text "$TIMER_OFF")"
JSON_TIMER_15="$(json_text "$TIMER_15")"
JSON_TIMER_30="$(json_text "$TIMER_30")"
JSON_TIMER_60="$(json_text "$TIMER_60")"
JSON_TIMER_MINUTES="$(json_text "$TIMER_MINUTES")"
JSON_TIMER_CUSTOM="$(json_text "$TIMER_CUSTOM")"
JSON_TIMER_START="$(json_text "$TIMER_START")"
JSON_TIMER_STOP="$(json_text "$TIMER_STOP")"
JSON_TIMER_ACTIVE="$(json_text "$TIMER_ACTIVE")"
JSON_TIMER_EXPIRED="$(json_text "$TIMER_EXPIRED")"
JSON_TIMER_REMAINING="$(json_text "$TIMER_REMAINING")"
JSON_TIMER_WARNING_TITLE="$(json_text "$TIMER_WARNING_TITLE")"
JSON_TIMER_WARNING_TEXT="$(json_text "$TIMER_WARNING_TEXT")"
JSON_TIMER_ENTER_PIN="$(json_text "$TIMER_ENTER_PIN")"
JSON_TIMER_EXTEND="$(json_text "$TIMER_EXTEND")"
JSON_TIMER_EXIT="$(json_text "$TIMER_EXIT")"
JSON_TIMER_WRONG_PIN="$(json_text "$TIMER_WRONG_PIN")"
JSON_TIMER_EXTENDED="$(json_text "$TIMER_EXTENDED")"
JSON_SCHEDULE_WEEKLY_TITLE="$(json_text "$SCHEDULE_WEEKLY_TITLE")"
JSON_SCHEDULE_WEEKLY_HINT="$(json_text "$SCHEDULE_WEEKLY_HINT")"
JSON_SCHEDULE_ENABLED="$(json_text "$SCHEDULE_ENABLED")"
JSON_SCHEDULE_APP_TITLE="$(json_text "$SCHEDULE_APP_TITLE")"
JSON_SCHEDULE_APP_HINT="$(json_text "$SCHEDULE_APP_HINT")"
JSON_SCHEDULE_SELECT_APP="$(json_text "$SCHEDULE_SELECT_APP")"
JSON_SCHEDULE_ADD_WINDOW="$(json_text "$SCHEDULE_ADD_WINDOW")"
JSON_SCHEDULE_REMOVE_WINDOW="$(json_text "$SCHEDULE_REMOVE_WINDOW")"
JSON_SCHEDULE_START="$(json_text "$SCHEDULE_START")"
JSON_SCHEDULE_END="$(json_text "$SCHEDULE_END")"
JSON_SCHEDULE_CLEAR_APP="$(json_text "$SCHEDULE_CLEAR_APP")"
JSON_SCHEDULE_NO_WINDOWS="$(json_text "$SCHEDULE_NO_WINDOWS")"
JSON_SCHEDULE_BLOCKED_TITLE="$(json_text "$SCHEDULE_BLOCKED_TITLE")"
JSON_SCHEDULE_PROFILE_BLOCKED="$(json_text "$SCHEDULE_PROFILE_BLOCKED")"
JSON_SCHEDULE_APP_BLOCKED="$(json_text "$SCHEDULE_APP_BLOCKED")"
JSON_SCHEDULE_OPEN_PARENTS="$(json_text "$SCHEDULE_OPEN_PARENTS")"
JSON_WEEKDAY_MONDAY="$(json_text "$WEEKDAY_MONDAY")"
JSON_WEEKDAY_TUESDAY="$(json_text "$WEEKDAY_TUESDAY")"
JSON_WEEKDAY_WEDNESDAY="$(json_text "$WEEKDAY_WEDNESDAY")"
JSON_WEEKDAY_THURSDAY="$(json_text "$WEEKDAY_THURSDAY")"
JSON_WEEKDAY_FRIDAY="$(json_text "$WEEKDAY_FRIDAY")"
JSON_WEEKDAY_SATURDAY="$(json_text "$WEEKDAY_SATURDAY")"
JSON_WEEKDAY_SUNDAY="$(json_text "$WEEKDAY_SUNDAY")"
JSON_STARTING_APP="$(json_text "$STARTING_APP")"
JSON_STARTED_APP="$(json_text "$STARTED_APP")"
JSON_EMPTY_STATE_EMOJI="$(json_text "$EMPTY_STATE_EMOJI")"
JSON_EMPTY_STATE_TEXT="$(json_text "$EMPTY_STATE_TEXT")"
JSON_PREVIEW_TITLE="$(json_text "$PREVIEW_TITLE")"
JSON_FEEDBACK_OPTIONS="$(json_text "$FEEDBACK_OPTIONS")"
JSON_SOUND_FEEDBACK="$(json_text "$SOUND_FEEDBACK")"
JSON_SPEECH_FEEDBACK="$(json_text "$SPEECH_FEEDBACK")"
JSON_SPEECH_AVAILABLE="$(json_text "$SPEECH_AVAILABLE")"
JSON_SPEECH_UNAVAILABLE="$(json_text "$SPEECH_UNAVAILABLE")"
JSON_FEEDBACK_HINT="$(json_text "$FEEDBACK_HINT")"
JSON_CELEBRATION_OPTIONS="$(json_text "$CELEBRATION_OPTIONS")"
JSON_CELEBRATION_ENABLED="$(json_text "$CELEBRATION_ENABLED")"
JSON_CELEBRATION_HINT="$(json_text "$CELEBRATION_HINT")"
JSON_ACCESSIBILITY_OPTIONS="$(json_text "$ACCESSIBILITY_OPTIONS")"
JSON_ACCESSIBILITY_LARGE_TEXT="$(json_text "$ACCESSIBILITY_LARGE_TEXT")"
JSON_ACCESSIBILITY_HIGH_CONTRAST="$(json_text "$ACCESSIBILITY_HIGH_CONTRAST")"
JSON_ACCESSIBILITY_REDUCED_MOTION="$(json_text "$ACCESSIBILITY_REDUCED_MOTION")"
JSON_ACCESSIBILITY_KEYBOARD_FOCUS="$(json_text "$ACCESSIBILITY_KEYBOARD_FOCUS")"
JSON_ACCESSIBILITY_HINT="$(json_text "$ACCESSIBILITY_HINT")"

CATALOG_ALL="$(text catalog_all)"
JSON_CATALOG_ALL="$(json_text "$CATALOG_ALL")"
CATALOG_CREATIVE="$(text catalog_creative)"
JSON_CATALOG_CREATIVE="$(json_text "$CATALOG_CREATIVE")"
CATALOG_LEARNING="$(text catalog_learning)"
JSON_CATALOG_LEARNING="$(json_text "$CATALOG_LEARNING")"
CATALOG_GAMES="$(text catalog_games)"
JSON_CATALOG_GAMES="$(json_text "$CATALOG_GAMES")"
CATALOG_WEB="$(text catalog_web)"
JSON_CATALOG_WEB="$(json_text "$CATALOG_WEB")"
CATALOG_REFRESH="$(text catalog_refresh)"
JSON_CATALOG_REFRESH="$(json_text "$CATALOG_REFRESH")"
CATALOG_SEARCH="$(text catalog_search)"
JSON_CATALOG_SEARCH="$(json_text "$CATALOG_SEARCH")"
CATALOG_CATEGORY="$(text catalog_category)"
JSON_CATALOG_CATEGORY="$(json_text "$CATALOG_CATEGORY")"
CATALOG_STATUS="$(text catalog_status)"
JSON_CATALOG_STATUS="$(json_text "$CATALOG_STATUS")"
CATALOG_COUNT="$(text catalog_count)"
JSON_CATALOG_COUNT="$(json_text "$CATALOG_COUNT")"
CATALOG_NO_MATCHES="$(text catalog_no_matches)"
JSON_CATALOG_NO_MATCHES="$(json_text "$CATALOG_NO_MATCHES")"
CATALOG_HINT="$(text catalog_hint)"
JSON_CATALOG_HINT="$(json_text "$CATALOG_HINT")"
CATALOG_DETAILS="$(text catalog_details)"
JSON_CATALOG_DETAILS="$(json_text "$CATALOG_DETAILS")"
CATALOG_UNKNOWN="$(text catalog_unknown)"
JSON_CATALOG_UNKNOWN="$(json_text "$CATALOG_UNKNOWN")"
CATALOG_AGE="$(text catalog_age)"
JSON_CATALOG_AGE="$(json_text "$CATALOG_AGE")"
CATALOG_OFFLINE="$(text catalog_offline)"
JSON_CATALOG_OFFLINE="$(json_text "$CATALOG_OFFLINE")"
CATALOG_OFFLINE_YES="$(text catalog_offline_yes)"
JSON_CATALOG_OFFLINE_YES="$(json_text "$CATALOG_OFFLINE_YES")"
CATALOG_OFFLINE_PARTIAL="$(text catalog_offline_partial)"
JSON_CATALOG_OFFLINE_PARTIAL="$(json_text "$CATALOG_OFFLINE_PARTIAL")"
CATALOG_OFFLINE_NO="$(text catalog_offline_no)"
JSON_CATALOG_OFFLINE_NO="$(json_text "$CATALOG_OFFLINE_NO")"
CATALOG_LICENSE="$(text catalog_license)"
JSON_CATALOG_LICENSE="$(json_text "$CATALOG_LICENSE")"
CATALOG_INPUT="$(text catalog_input)"
JSON_CATALOG_INPUT="$(json_text "$CATALOG_INPUT")"
CATALOG_MOUSE="$(text catalog_mouse)"
JSON_CATALOG_MOUSE="$(json_text "$CATALOG_MOUSE")"
CATALOG_KEYBOARD="$(text catalog_keyboard)"
JSON_CATALOG_KEYBOARD="$(json_text "$CATALOG_KEYBOARD")"
CATALOG_TOUCH="$(text catalog_touch)"
JSON_CATALOG_TOUCH="$(json_text "$CATALOG_TOUCH")"
CATALOG_NETWORK="$(text catalog_network)"
JSON_CATALOG_NETWORK="$(json_text "$CATALOG_NETWORK")"
CATALOG_WEB_PRIVACY="$(text catalog_web_privacy)"
JSON_CATALOG_WEB_PRIVACY="$(json_text "$CATALOG_WEB_PRIVACY")"
CATALOG_SOURCE="$(text catalog_source)"
JSON_CATALOG_SOURCE="$(json_text "$CATALOG_SOURCE")"
CATALOG_REVIEWED="$(text catalog_reviewed)"
JSON_CATALOG_REVIEWED="$(json_text "$CATALOG_REVIEWED")"

backup_if_exists "$RUNTIME_BIN"
backup_if_exists "$SERVER_FILE"
backup_if_exists "$INDEX_FILE"
backup_if_exists "$FRONTEND_STYLES_FILE"
backup_if_exists "$FRONTEND_DESIGN_SYSTEM_FILE"
backup_if_exists "$FRONTEND_STATE_FILE"
backup_if_exists "$FRONTEND_LOCALIZATION_FILE"
backup_if_exists "$FRONTEND_LOCALES_DIR"
backup_if_exists "$FRONTEND_ICONS_FILE"
backup_if_exists "$FRONTEND_DIALOGS_FILE"
backup_if_exists "$FRONTEND_THEME_RUNTIME_FILE"
backup_if_exists "$FRONTEND_ACCESSIBILITY_RUNTIME_FILE"
backup_if_exists "$FRONTEND_FEEDBACK_RUNTIME_FILE"
backup_if_exists "$FRONTEND_CELEBRATION_RUNTIME_FILE"
backup_if_exists "$FRONTEND_TRANSITION_RUNTIME_FILE"
backup_if_exists "$FRONTEND_LAUNCHER_FILE"
backup_if_exists "$FRONTEND_PROFILES_FILE"
backup_if_exists "$FRONTEND_SCHEDULE_FILE"
backup_if_exists "$FRONTEND_ACTIVITY_FILE"
backup_if_exists "$FRONTEND_MEDIA_LIBRARY_STYLES_FILE"
backup_if_exists "$FRONTEND_MEDIA_LIBRARY_FILE"
backup_if_exists "$FRONTEND_SETTINGS_FILE"
backup_if_exists "$FRONTEND_APP_CATALOG_FILE"
backup_if_exists "$FRONTEND_FIRST_RUN_FILE"
backup_if_exists "$FRONTEND_RUNTIME_FILE"
backup_if_exists "$MEDIA_FILE"
backup_if_exists "$MEDIA_LIBRARY_PAGE"
backup_if_exists "$UPDATE_SCRIPT"
backup_if_exists "$CONFIG_FILE"
backup_if_exists "$AUTOSTART_FILE"
backup_if_exists "$DESKTOP_FILE"
backup_if_exists "$APP_DESKTOP_FILE"

# Render templates from src/
render_template "$SRC_DIR/server.py" "$SERVER_FILE" 0644
install -m 0644 "$SRC_DIR/app_detection.py" "$APP_ROOT/app_detection.py"
install -m 0644 "$SRC_DIR/package_provider.py" "$APP_ROOT/package_provider.py"
install -m 0644 "$SRC_DIR/package_install.py" "$APP_ROOT/package_install.py"
install -m 0644 "$SRC_DIR/flatpak_backend.py" "$APP_ROOT/flatpak_backend.py"
install -m 0644 "$SRC_DIR/flatpak_catalog.py" "$APP_ROOT/flatpak_catalog.py"
install -m 0644 "$SRC_DIR/flatpak_catalog.json" "$APP_ROOT/flatpak_catalog.json"
install -m 0644 "$SRC_DIR/packagekit_backend.py" "$APP_ROOT/packagekit_backend.py"
install -m 0644 "$SRC_DIR/application_launcher.py" "$APP_ROOT/application_launcher.py"
install -m 0644 "$SRC_DIR/app_display.py" "$APP_ROOT/app_display.py"
install -m 0644 "$SRC_DIR/launch_status.py" "$APP_ROOT/launch_status.py"
install -m 0644 "$SRC_DIR/activity_store.py" "$APP_ROOT/activity_store.py"
install -m 0644 "$SRC_DIR/daily_budget.py" "$APP_ROOT/daily_budget.py"
install -m 0644 "$SRC_DIR/backup_store.py" "$APP_ROOT/backup_store.py"
install -m 0644 "$SRC_DIR/browser_policy.py" "$APP_ROOT/browser_policy.py"
install -m 0644 "$SRC_DIR/config_store.py" "$APP_ROOT/config_store.py"
install -m 0644 "$SRC_DIR/config_validation.py" "$APP_ROOT/config_validation.py"
install -m 0644 "$SRC_DIR/language_registry.py" "$SRC_DIR/language_registry.json" \
  "$SRC_DIR/translation_data.py" "$SRC_DIR/runtime_locale.py" "$APP_ROOT/"
install -d -m 0755 "$APP_ROOT/translations"
for code in "${LANGUAGE_CODES[@]}"; do
  install -m 0644 "$SRC_DIR/translations/$code.json" "$APP_ROOT/translations/$code.json"
done
install -m 0644 "$SRC_DIR/profile_config.py" "$APP_ROOT/profile_config.py"
install -m 0644 "$SRC_DIR/schedule_rules.py" "$APP_ROOT/schedule_rules.py"
install -m 0644 "$SRC_DIR/lifecycle_state.py" "$APP_ROOT/lifecycle_state.py"
install -m 0644 "$SRC_DIR/service_control.py" "$SRC_DIR/cozy-kids-launcher.service" "$APP_ROOT/"
install -m 0644 "$SRC_DIR/media_library.py" "$APP_ROOT/media_library.py"
install -m 0644 "$SRC_DIR/media_state.py" "$APP_ROOT/media_state.py"
install -m 0644 "$SRC_DIR/media_resume.py" "$APP_ROOT/media_resume.py"
install -m 0644 "$SRC_DIR/retro_games.py" "$APP_ROOT/retro_games.py"
install -m 0644 "$SRC_DIR/retro_device.py" "$APP_ROOT/retro_device.py"
install -m 0644 "$SRC_DIR/retro_benchmark.py" "$SRC_DIR/retro_benchmark_worker.py" "$SRC_DIR/retro_workload.py" "$APP_ROOT/"
install -m 0644 "$SRC_DIR/retro_requirements.json" "$APP_ROOT/retro_requirements.json"
install -m 0644 "$SRC_DIR/retro_saves.py" "$APP_ROOT/retro_saves.py"
install -m 0644 "$SRC_DIR/media_session.py" "$APP_ROOT/media_session.py"
install -m 0644 "$SRC_DIR/parent_auth.py" "$APP_ROOT/parent_auth.py"
install -m 0644 "$SRC_DIR/speech_feedback.py" "$APP_ROOT/speech_feedback.py"
install -m 0644 "$SRC_DIR/runtime_diagnostics.py" "$APP_ROOT/runtime_diagnostics.py"
install -m 0644 "$SRC_DIR/process_state.py" "$APP_ROOT/process_state.py"
install -m 0755 "$SRC_DIR/process_supervisor.py" "$APP_ROOT/process_supervisor.py"
install -m 0644 "$SRC_DIR/timer_state.py" "$APP_ROOT/timer_state.py"
install -m 0644 "$SRC_DIR/update_manager.py" "$APP_ROOT/update_manager.py"
render_template "$SRC_DIR/index.html" "$INDEX_FILE" 0644
render_template "$SRC_DIR/frontend/design-system.css" "$FRONTEND_DESIGN_SYSTEM_FILE" 0644
render_template "$SRC_DIR/frontend/styles.css" "$FRONTEND_STYLES_FILE" 0644
render_template "$SRC_DIR/frontend/state.js" "$FRONTEND_STATE_FILE" 0644
render_template "$SRC_DIR/frontend/localization.js" "$FRONTEND_LOCALIZATION_FILE" 0644
install -d -m 0755 "$FRONTEND_LOCALES_DIR"
for code in "${LANGUAGE_CODES[@]}"; do
  install -m 0644 "$SRC_DIR/frontend/locales/$code.json" "$FRONTEND_LOCALES_DIR/$code.json"
done
render_template "$SRC_DIR/frontend/icons.js" "$FRONTEND_ICONS_FILE" 0644
render_template "$SRC_DIR/frontend/dialogs.js" "$FRONTEND_DIALOGS_FILE" 0644
install -m 0644 "$SRC_DIR/frontend/theme-runtime.js" "$FRONTEND_THEME_RUNTIME_FILE"
install -m 0644 "$SRC_DIR/frontend/accessibility-runtime.js" "$FRONTEND_ACCESSIBILITY_RUNTIME_FILE"
install -m 0644 "$SRC_DIR/frontend/feedback-runtime.js" "$FRONTEND_FEEDBACK_RUNTIME_FILE"
install -m 0644 "$SRC_DIR/frontend/celebration-runtime.js" "$FRONTEND_CELEBRATION_RUNTIME_FILE"
install -m 0644 "$SRC_DIR/frontend/transition-runtime.js" "$FRONTEND_TRANSITION_RUNTIME_FILE"
install -m 0644 "$SRC_DIR/frontend/controller-navigation.js" "$FRONTEND_DIR/controller-navigation.js"
render_template "$SRC_DIR/frontend/launcher-ui.js" "$FRONTEND_LAUNCHER_FILE" 0644
render_template "$SRC_DIR/frontend/profiles.js" "$FRONTEND_PROFILES_FILE" 0644
render_template "$SRC_DIR/frontend/schedule-controls.js" "$FRONTEND_SCHEDULE_FILE" 0644
render_template "$SRC_DIR/frontend/activity-dashboard.js" "$FRONTEND_ACTIVITY_FILE" 0644
install -m 0644 "$SRC_DIR/frontend/media-library.css" "$FRONTEND_MEDIA_LIBRARY_STYLES_FILE"
render_template "$SRC_DIR/frontend/media-library.js" "$FRONTEND_MEDIA_LIBRARY_FILE" 0644
render_template "$SRC_DIR/frontend/parent-settings.js" "$FRONTEND_SETTINGS_FILE" 0644
install -m 0644 "$SRC_DIR/frontend/retro-benchmark.js" "$FRONTEND_DIR/retro-benchmark.js"
install -m 0644 "$SRC_DIR/frontend/app-catalog.js" "$FRONTEND_APP_CATALOG_FILE"
install -m 0644 "$SRC_DIR/frontend/package-catalog.js" "$FRONTEND_DIR/package-catalog.js"
render_template "$SRC_DIR/frontend/first-run.js" "$FRONTEND_FIRST_RUN_FILE" 0644
render_template "$SRC_DIR/frontend/runtime-controls.js" "$FRONTEND_RUNTIME_FILE" 0644
render_template "$SRC_DIR/no-media.html" "$MEDIA_FILE" 0644
render_template "$SRC_DIR/media.html" "$MEDIA_LIBRARY_PAGE" 0644
render_template "$SRC_DIR/launcher.sh" "$RUNTIME_BIN" 0755
install -m 0644 "$SRC_DIR/browser.html" "$APP_ROOT/browser.html"
render_template "$SRC_DIR/overlay.py" "$APP_ROOT/overlay.py" 0755
render_template "$SRC_DIR/timer_watchdog.py" "$APP_ROOT/timer_watchdog.py" 0755

# Install the standalone updater used by the parent UI and the command line.
install -m 0755 "$REPO_DIR/scripts/update.sh" "$UPDATE_SCRIPT"

# Copy theme wallpapers (binary files, no template rendering)
if [[ -d "$SRC_DIR/../themes" ]]; then
  cp -r "$SRC_DIR/../themes" "$APP_ROOT/themes"
fi

# Generate config JSON with proper escaping
python3 - "$CONFIG_FILE" "$ACTIVE_LANG" "$DEFAULT_TITLE" "$DEFAULT_THEME" "$DEFAULT_LAYOUT" "$DEFAULT_PARENT_LABEL" "$DEFAULT_EXIT_LABEL" "$SHUTDOWN_LABEL" "$DEFAULT_TILE_PAINT" "$DEFAULT_TILE_GAMES" "$DEFAULT_TILE_MUSIC" "$DEFAULT_TILE_BROWSER" "$DEFAULT_BROWSER_URL" "$SRC_DIR/recommendations.json" "$RECOMMENDED" <<'PY'
import json, sys, shutil, os
path, lang, title, theme, layout, parent_label, exit_label, shutdown_label, tile_paint, tile_games, tile_music, tile_browser, browser_url, rec_path, recommended = sys.argv[1:16]
config = {
    "configVersion": 2,
    "language": lang,
    "parentLabel": parent_label,
    "exitLabel": exit_label,
    "shutdownLabel": shutdown_label,
    "pinHash": "",
    "autoScanDone": False,
    "setupCompleted": False,
    "activityTrackingEnabled": False,
    "activeProfileId": "default",
    "profiles": [{
        "id": "default",
        "name": "Kiddo",
        "avatar": "🌈",
        "title": title,
        "theme": theme,
        "themeMotionEnabled": True,
        "themeTimeOfDayEnabled": False,
        "soundFeedbackEnabled": False,
        "speechFeedbackEnabled": False,
        "celebrationEnabled": False,
        "accessibilityLargeText": False,
        "accessibilityHighContrast": False,
        "accessibilityReducedMotion": False,
        "accessibilityKeyboardFocus": False,
        "layoutMode": layout,
        "currentPage": 0,
        "timerMinutes": 0,
        "timerWarningMinutes": 5,
        "favorites": [],
        "appLimits": {},
        "tiles": [
            {"id": "paint", "label": tile_paint, "emoji": "🎨", "cmd": ["tuxpaint"], "visible": True},
            {"id": "games", "label": tile_games, "emoji": "🧩", "cmd": ["gcompris"], "visible": True},
            {"id": "music", "label": tile_music, "emoji": "🎵", "cmd": ["special:filme-musik"], "visible": True},
            {"id": "browser", "label": tile_browser, "emoji": "🌐", "cmd": ["special:external-browser:" + browser_url], "visible": False}
        ]
    }]
}
profile = config["profiles"][0]
existing_ids = {"paint", "games", "music", "browser"}
if recommended == "1" and os.path.isfile(rec_path):
    with open(rec_path, 'r', encoding='utf-8') as f:
        recs = json.load(f)
    for rec in recs:
        if rec.get("installOnly"):
            continue
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
            label = rec.get("label_" + lang) or rec.get("label_en") or rec["id"]
            if cmds and found_cmd == cmds[0]:
                tile_cmd = cmds
            elif cmds and cmds[0] in ("kstart", "kstart5"):
                # KDE wrapper: use wrapper + args if available, else bare app
                tile_cmd = cmds if shutil.which(cmds[0]) else [found_cmd]
            else:
                # Normal alt_cmd replacement: keep all args
                tile_cmd = [found_cmd] + list(cmds[1:])
            profile["tiles"].append({
                "id": rec["id"],
                "label": label,
                "emoji": rec.get("emoji", "✨"),
                "cmd": tile_cmd,
                "visible": True
            })
            existing_ids.add(rec["id"])
    if existing_ids > {"paint", "games", "music", "browser"}:
        config["autoScanDone"] = True
with open(path, 'w', encoding='utf-8') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
    f.write('\n')
PY
chmod 0600 "$CONFIG_FILE"

# Copy recommendations data for runtime use
if [[ -f "$SRC_DIR/recommendations.json" ]]; then
  install -m 0644 "$SRC_DIR/recommendations.json" "$APP_ROOT/recommendations.json"
fi

write_file "$AUTOSTART_FILE" 0644 <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$AUTOSTART_NAME
Exec=$RUNTIME_BIN --autostart
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
If the optional user service is enabled, run: $RUNTIME_BIN --service disable

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

chown -R "$TARGET_USER":"$TARGET_USER" "$APP_ROOT" "$CFG_DIR" "$CACHE_DIR" "$BACKUP_ROOT"
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
echo "  $(text cli_user): $TARGET_USER"
echo "  $(text cli_home): $TARGET_HOME"
echo "  $(text cli_language): $ACTIVE_LANG"
echo "  $(text cli_browser): $BROWSER_CMD"
echo "  $(text cli_shutdown_helper): $INSTALL_SHUTDOWN_HELPER"
echo "  $(text cli_backup_dir): $BACKUP_DIR"
echo "$(text next_steps)"
