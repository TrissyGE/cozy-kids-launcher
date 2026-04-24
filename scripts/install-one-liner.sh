#!/usr/bin/env bash
set -euo pipefail

# One-liner install for Cozy Kids Launcher
# Usage: curl -fsSL https://raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main/scripts/install-one-liner.sh | bash

REPO="TrissyGE/cozy-kids-launcher"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "$TMP_DIR"' EXIT

USER_NAME="${SUDO_USER:-${USER:-$(id -un 2>/dev/null || true)}}"

echo ""
echo "========================================="
echo "  Cozy Kids Launcher - Easy Installer"
echo "========================================="
echo ""

# Check prerequisites
if ! command -v bash >/dev/null 2>&1; then
    echo "Error: bash is required."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is not installed. Please install it first."
    exit 1
fi

BROWSER=""
for b in firefox chromium chromium-browser google-chrome; do
    if command -v "$b" >/dev/null 2>&1; then
        BROWSER="$b"
        break
    fi
done

if [[ -z "$BROWSER" ]]; then
    echo "Error: No supported browser found."
    echo "Please install Firefox or Chromium first, then re-run this installer."
    exit 1
fi

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
unzip -q "$TMP_DIR/repo.zip" -d "$TMP_DIR/"

echo "Installing for user: $USER_NAME"
cd "$TMP_DIR/cozy-kids-launcher-main"
bash scripts/install.sh --user "$USER_NAME" --lang auto --browser auto --skip-browser-check

echo ""
echo "========================================="
echo "  Installation complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo "  1. Log out and log back in"
echo "  2. The kids launcher starts automatically"
echo "  3. Tap the 'Parent' button to customize tiles and apps"
echo "  4. Use the desktop shortcut to reopen kids mode anytime"
echo ""
