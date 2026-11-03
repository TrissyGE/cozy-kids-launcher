#!/usr/bin/env bash
set -euo pipefail

APP_ID="cozy-kids-launcher"
REPO="${COZY_KIDS_REPO:-TrissyGE/cozy-kids-launcher}"
RELEASE_API_URL="${COZY_KIDS_RELEASE_API_URL:-https://api.github.com/repos/$REPO/releases/latest}"
PREVIEW_API_URL="${COZY_KIDS_PREVIEW_API_URL:-${RELEASE_API_URL%/latest}?per_page=100}"
RAW_URL="${COZY_KIDS_RAW_URL:-https://raw.githubusercontent.com/$REPO/main}"
MAIN_ARCHIVE_URL="${COZY_KIDS_MAIN_ARCHIVE_URL:-https://github.com/$REPO/archive/refs/heads/main.zip}"
APP_ROOT="$HOME/.local/share/$APP_ID"
VERSION_FILE="$APP_ROOT/version"
CHANNEL_FILE="$APP_ROOT/update-channel"
CONFIG_FILE="$HOME/.config/$APP_ID/config.json"
TRACK_FILE="$HOME/.config/$APP_ID/update-track"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UPDATE_MANAGER="$SCRIPT_DIR/update_manager.py"
if [[ ! -f "$UPDATE_MANAGER" ]]; then
  UPDATE_MANAGER="$SCRIPT_DIR/../src/update_manager.py"
fi
RUNTIME_BIN="$HOME/.local/bin/$APP_ID"
TMP_DIR="$(mktemp -d)"
CONFIG_BACKED_UP="0"
ROLLBACK_READY="0"
ROLLBACK_PATHS=(
  "$APP_ROOT"
  "$RUNTIME_BIN"
  "$CONFIG_FILE"
  "$HOME/.config/autostart/cozy-kids-launcher-autostart.desktop"
  "$HOME/Desktop/Cozy Kids Launcher.desktop"
  "$HOME/Schreibtisch/Cozy Kids Launcher.desktop"
  "$HOME/.local/share/applications/cozy-kids-launcher.desktop"
)

restore_snapshot() {
  local index path snapshot
  for index in "${!ROLLBACK_PATHS[@]}"; do
    path="${ROLLBACK_PATHS[index]}"
    case "$path" in
      "$HOME"/*) ;;
      *) echo "Refusing unsafe rollback path: $path" >&2; continue ;;
    esac
    snapshot="$TMP_DIR/rollback/$index"
    rm -rf -- "$path"
    if [[ -f "$snapshot/existed" ]]; then
      mkdir -p "$(dirname "$path")"
      cp -a "$snapshot/content" "$path"
    fi
  done
}

cleanup() {
  local status=$?
  set +e
  if [[ "$status" -ne 0 && "$ROLLBACK_READY" == "1" ]]; then
    echo "Update failed; restoring the previous installation." >&2
    restore_snapshot
  elif [[ "$status" -ne 0 && "$CONFIG_BACKED_UP" == "1" && -f "$TMP_DIR/config-backup.json" ]]; then
    mkdir -p "$(dirname "$CONFIG_FILE")"
    cp "$TMP_DIR/config-backup.json" "$CONFIG_FILE"
  fi
  rm -rf "$TMP_DIR"
  exit "$status"
}
trap cleanup EXIT

usage() {
  cat <<'EOF'
Usage: scripts/update.sh [options]

Options:
  --check-only   Check for an update without installing it
  --force        Reinstall the same version (never downgrades)
  --set-channel stable|preview   Save the update channel without installing
  --legacy-main  Explicitly use the legacy main/VERSION update source
  -h, --help     Show this help
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

download() {
  local url="$1" destination="$2"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL --retry 2 --connect-timeout 10 -o "$destination" "$url"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$destination" "$url"
  else
    die "curl or wget is required"
  fi
}

discover_release() {
  local metadata="$TMP_DIR/latest-release.json" endpoint="$RELEASE_API_URL"
  if [[ "$TRACK" == "preview" ]]; then
    endpoint="$PREVIEW_API_URL"
  fi
  if ! download "$endpoint" "$metadata" 2>/dev/null; then
    return 2
  fi
  python3 "$UPDATE_MANAGER" select "$metadata" "$TRACK" || return 3
}

read_legacy_version() {
  local legacy_file="$TMP_DIR/legacy-version"
  download "$RAW_URL/VERSION" "$legacy_file" || return 1
  head -n1 "$legacy_file" | tr -d '[:space:]'
}

preserved_installer_args() {
  PRESERVED_ARGS=(--user "$(id -un)" --home "$HOME" --force)

  if [[ -f "$CONFIG_FILE" ]]; then
    local language
    language="$(python3 - "$CONFIG_FILE" <<'PY' 2>/dev/null || true
import json
import sys
with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get("language", "")
if value in ("de", "en"):
    print(value)
PY
)"
    if [[ -n "$language" ]]; then
      PRESERVED_ARGS+=(--lang "$language")
    fi
  fi

  if [[ -f "$RUNTIME_BIN" ]]; then
    local launch_mode
    launch_mode="$(sed -n 's/^LAUNCH_MODE="\([^"]*\)".*/\1/p' "$RUNTIME_BIN" | head -n1)"
    case "$launch_mode" in
      window|fullscreen|kiosk) PRESERVED_ARGS+=(--launch-mode "$launch_mode") ;;
    esac
    if grep -Fq 'COZY_KIDS_ENABLE_SHUTDOWN="1"' "$RUNTIME_BIN"; then
      PRESERVED_ARGS+=(--install-shutdown-helper)
    fi
  fi

  if [[ -f "$HOME/.config/$APP_ID/browser" ]]; then
    local browser
    browser="$(head -n1 "$HOME/.config/$APP_ID/browser" | tr -d '[:space:]')"
    browser="$(basename "$browser")"
    if [[ -n "$browser" ]] && command -v "$browser" >/dev/null 2>&1; then
      PRESERVED_ARGS+=(--browser "$browser")
    fi
  fi
}

prepare_snapshot() {
  local index path snapshot
  mkdir -p "$TMP_DIR/rollback"
  for index in "${!ROLLBACK_PATHS[@]}"; do
    path="${ROLLBACK_PATHS[index]}"
    case "$path" in
      "$HOME"/*) ;;
      *) die "Refusing unsafe rollback path: $path" ;;
    esac
    snapshot="$TMP_DIR/rollback/$index"
    mkdir -p "$snapshot"
    if [[ -e "$path" ]]; then
      : > "$snapshot/existed"
      cp -a "$path" "$snapshot/content"
    fi
  done
  ROLLBACK_READY="1"
}

CHECK_ONLY="0"
FORCE="0"
LEGACY_MAIN="0"
SET_TRACK=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only) CHECK_ONLY="1"; shift ;;
    --force) FORCE="1"; shift ;;
    --legacy-main) LEGACY_MAIN="1"; shift ;;
    --set-channel)
      [[ $# -eq 2 && "$CHECK_ONLY" == "0" && "$FORCE" == "0" && "$LEGACY_MAIN" == "0" ]]         || die "Use --set-channel stable|preview on its own"
      SET_TRACK="$2"
      [[ "$SET_TRACK" == "stable" || "$SET_TRACK" == "preview" ]] || die "Expected stable or preview"
      shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

if [[ -n "$SET_TRACK" ]]; then
  python3 "$UPDATE_MANAGER" set-track "$TRACK_FILE" "$SET_TRACK"
  echo "Update channel: $SET_TRACK"
  exit 0
fi

TRACK="$(python3 "$UPDATE_MANAGER" track "$TRACK_FILE")"
[[ "$TRACK" != "preview" || "$LEGACY_MAIN" != "1" ]] || die "Switch to stable before requesting legacy main"
echo "Update channel: $TRACK"

INSTALLED_VERSION="0.0.0"
if [[ -f "$VERSION_FILE" ]]; then
  INSTALLED_VERSION="$(head -n1 "$VERSION_FILE" | tr -d '[:space:]')"
fi
python3 "$UPDATE_MANAGER" compare "$INSTALLED_VERSION" "$INSTALLED_VERSION" >/dev/null || die "Installed version is invalid"

echo "Installed version: $INSTALLED_VERSION"
echo "Checking for updates..."

UPDATE_SOURCE=""
LATEST_VERSION=""
ARCHIVE_NAME=""
ARCHIVE_URL=""
CHECKSUM_URL=""

if [[ "$LEGACY_MAIN" != "1" ]]; then
  set +e
  discover_release > "$TMP_DIR/release-data"
  RELEASE_STATUS=$?
  set -e
  RELEASE_DATA=()
  if [[ "$RELEASE_STATUS" -eq 0 ]]; then
    mapfile -t RELEASE_DATA < "$TMP_DIR/release-data"
  fi
  if [[ "$RELEASE_STATUS" -eq 0 && "${#RELEASE_DATA[@]}" -eq 4 ]]; then
    UPDATE_SOURCE="release"
    LATEST_VERSION="${RELEASE_DATA[0]}"
    ARCHIVE_NAME="${RELEASE_DATA[1]}"
    ARCHIVE_URL="${RELEASE_DATA[2]}"
    CHECKSUM_URL="${RELEASE_DATA[3]}"
  elif [[ "$RELEASE_STATUS" -eq 3 ]]; then
    die "GitHub returned an incomplete or invalid release; refusing an unverified update"
  fi
fi

if [[ -z "$UPDATE_SOURCE" ]]; then
  [[ "$TRACK" == "stable" ]] || die "Preview discovery failed. Retry later."
  if [[ -f "$CHANNEL_FILE" && "$(head -n1 "$CHANNEL_FILE" | tr -d '[:space:]')" == "release" && "$LEGACY_MAIN" != "1" ]]; then
    die "Release discovery failed. This installation has already used verified releases, so mutable main fallback is disabled. Retry later or explicitly use --legacy-main."
  fi
  if [[ "$LEGACY_MAIN" == "1" ]]; then
    echo "Using explicitly requested legacy main/VERSION update source."
  else
    echo "No compatible GitHub Release found; using the updater-compatible main/VERSION fallback."
  fi
  UPDATE_SOURCE="legacy-main"
  LATEST_VERSION="$(read_legacy_version)" || die "Could not fetch the legacy VERSION file"
fi

if [[ "$UPDATE_SOURCE" == "legacy-main" && ! "$LATEST_VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  die "Legacy version is invalid"
fi
ORDER="$(python3 "$UPDATE_MANAGER" compare "$INSTALLED_VERSION" "$LATEST_VERSION")" || die "Latest version is invalid"
echo "Latest version:    $LATEST_VERSION ($UPDATE_SOURCE)"

if [[ "$ORDER" == "1" ]]; then
  echo "Installed version is newer; refusing to downgrade."
  exit 0
fi

if [[ "$ORDER" == "0" && "$FORCE" != "1" ]]; then
  echo "You are up to date."
  exit 0
fi

if [[ "$CHECK_ONLY" == "1" ]]; then
  if [[ "$ORDER" == "0" ]]; then
    echo "Version $LATEST_VERSION can be reinstalled with --force."
  else
    echo "Update available: $LATEST_VERSION (installed: $INSTALLED_VERSION)"
  fi
  exit 0
fi

SOURCE_ROOT=""
if [[ "$UPDATE_SOURCE" == "release" ]]; then
  command -v sha256sum >/dev/null 2>&1 || die "sha256sum is required for verified release updates"
  command -v tar >/dev/null 2>&1 || die "tar is required for release updates"
  echo "Downloading verified release $LATEST_VERSION..."
  download "$ARCHIVE_URL" "$TMP_DIR/$ARCHIVE_NAME" || die "Release download failed"
  download "$CHECKSUM_URL" "$TMP_DIR/SHA256SUMS" || die "Checksum download failed"

  EXPECTED_HASH="$(awk -v file="$ARCHIVE_NAME" '$2 == file || $2 == "*" file {print $1; exit}' "$TMP_DIR/SHA256SUMS")"
  [[ "$EXPECTED_HASH" =~ ^[0-9a-fA-F]{64}$ ]] || die "SHA256SUMS has no valid entry for $ARCHIVE_NAME"
  ACTUAL_HASH="$(sha256sum "$TMP_DIR/$ARCHIVE_NAME" | awk '{print $1}')"
  [[ "${ACTUAL_HASH,,}" == "${EXPECTED_HASH,,}" ]] || die "Release checksum verification failed"
  echo "SHA-256 checksum verified."

  mkdir -p "$TMP_DIR/source"
  tar -xzf "$TMP_DIR/$ARCHIVE_NAME" -C "$TMP_DIR/source"
  SOURCE_ROOT="$TMP_DIR/source/cozy-kids-launcher-$LATEST_VERSION"
else
  echo "Downloading legacy main archive..."
  download "$MAIN_ARCHIVE_URL" "$TMP_DIR/cozy-kids-launcher-main.zip" || die "Legacy download failed"
  if command -v unzip >/dev/null 2>&1; then
    unzip -q "$TMP_DIR/cozy-kids-launcher-main.zip" -d "$TMP_DIR/source"
  elif command -v python3 >/dev/null 2>&1; then
    mkdir -p "$TMP_DIR/source"
    python3 -m zipfile -e "$TMP_DIR/cozy-kids-launcher-main.zip" "$TMP_DIR/source"
  else
    die "unzip or python3 is required for legacy updates"
  fi
  SOURCE_ROOT="$TMP_DIR/source/cozy-kids-launcher-main"
fi

[[ -f "$SOURCE_ROOT/scripts/install.sh" ]] || die "Downloaded update has no installer"
if [[ -f "$CONFIG_FILE" ]]; then
  cp "$CONFIG_FILE" "$TMP_DIR/config-backup.json"
  CONFIG_BACKED_UP="1"
fi

preserved_installer_args
prepare_snapshot
echo "Installing update..."
bash "$SOURCE_ROOT/scripts/install.sh" "${PRESERVED_ARGS[@]}"

if [[ "$CONFIG_BACKED_UP" == "1" ]]; then
  mkdir -p "$(dirname "$CONFIG_FILE")"
  cp "$TMP_DIR/config-backup.json" "$CONFIG_FILE"
  CONFIG_BACKED_UP="0"
fi

[[ -f "$VERSION_FILE" ]] || die "Installer did not write a version file"
INSTALLED_AFTER="$(head -n1 "$VERSION_FILE" | tr -d '[:space:]')"
[[ "$INSTALLED_AFTER" == "$LATEST_VERSION" ]] || die "Installed version $INSTALLED_AFTER does not match expected version $LATEST_VERSION"

if [[ "$UPDATE_SOURCE" == "release" ]]; then
  printf '%s\n' "release" > "$CHANNEL_FILE"
fi
ROLLBACK_READY="0"

echo "Update complete. Version $LATEST_VERSION installed from $UPDATE_SOURCE."
echo "Restart the launcher to use the new version."
