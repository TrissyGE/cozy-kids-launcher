#!/usr/bin/env bash
set -euo pipefail

APP_ID="cozy-kids-launcher"
REPO="TrissyGE/cozy-kids-launcher"
RAW_URL="https://raw.githubusercontent.com/$REPO/main"
APP_ROOT="$HOME/.local/share/$APP_ID"
VERSION_FILE="$APP_ROOT/version"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

usage() {
  cat <<'EOF'
Usage: scripts/update.sh [options]

Options:
  --check-only   Only check if an update is available, don't install
  --force        Re-install even if versions match
  -h, --help     Show this help
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

# Simple semver compare: returns 0 if $1 >= $2
version_ge() {
  local a="$1" b="$2"
  # Use sort -V if available (GNU coreutils)
  # Checks if b <= a (equivalent to a >= b)
  if printf '%s\n%s\n' "$b" "$a" | sort -V -C 2>/dev/null; then
    return 0
  fi
  # Fallback: naive numeric compare
  local IFS=.
  read -ra A <<< "$a"
  read -ra B <<< "$b"
  local i
  for (( i=0; i<${#A[@]} || i<${#B[@]}; i++ )); do
    local av="${A[i]:-0}"
    local bv="${B[i]:-0}"
    if (( av > bv )); then return 0; fi
    if (( av < bv )); then return 1; fi
  done
  return 0
}

CHECK_ONLY="0"
FORCE="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check-only)
      CHECK_ONLY="1"
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

# Read installed version
INSTALLED_VERSION="0.0.0"
if [[ -f "$VERSION_FILE" ]]; then
  INSTALLED_VERSION="$(head -n1 "$VERSION_FILE" | tr -d '[:space:]')"
fi

echo "Installed version: $INSTALLED_VERSION"

# Fetch latest version from GitHub
echo "Checking for updates..."
LATEST_VERSION=""
if command -v curl >/dev/null 2>&1; then
  LATEST_VERSION="$(curl -fsSL "$RAW_URL/VERSION" 2>/dev/null | head -n1 | tr -d '[:space:]')" || true
elif command -v wget >/dev/null 2>&1; then
  LATEST_VERSION="$(wget -qO- "$RAW_URL/VERSION" 2>/dev/null | head -n1 | tr -d '[:space:]')" || true
fi

if [[ -z "$LATEST_VERSION" ]]; then
  die "Could not fetch latest version. Check your internet connection."
fi

echo "Latest version:    $LATEST_VERSION"

if [[ "$FORCE" != "1" ]] && version_ge "$INSTALLED_VERSION" "$LATEST_VERSION"; then
  echo "You are up to date."
  exit 0
fi

if [[ "$CHECK_ONLY" == "1" ]]; then
  echo "Update available: $LATEST_VERSION (installed: $INSTALLED_VERSION)"
  echo "Run without --check-only to update."
  exit 0
fi

echo "Downloading update..."

# Download the repo as zip
if command -v curl >/dev/null 2>&1; then
  curl -fsSL -o "$TMP_DIR/cozy-kids-launcher.zip" "https://github.com/$REPO/archive/refs/heads/main.zip" || die "Download failed"
elif command -v wget >/dev/null 2>&1; then
  wget -qO "$TMP_DIR/cozy-kids-launcher.zip" "https://github.com/$REPO/archive/refs/heads/main.zip" || die "Download failed"
else
  die "curl or wget is required"
fi

unzip -q "$TMP_DIR/cozy-kids-launcher.zip" -d "$TMP_DIR/"
REPO_DIR="$TMP_DIR/cozy-kids-launcher-main"

# Preserve existing config
if [[ -f "$HOME/.config/$APP_ID/config.json" ]]; then
  cp "$HOME/.config/$APP_ID/config.json" "$TMP_DIR/config-backup.json"
fi

# Re-run installer with preserved settings
echo "Installing update..."
cd "$REPO_DIR"
bash scripts/install.sh --user "$(id -un)" --force

# Restore config (installer may have overwritten it)
if [[ -f "$TMP_DIR/config-backup.json" ]]; then
  cp "$TMP_DIR/config-backup.json" "$HOME/.config/$APP_ID/config.json"
fi

echo "Update complete. Version $LATEST_VERSION installed."
echo "Restart the launcher to use the new version."
