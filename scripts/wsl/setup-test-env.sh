#!/usr/bin/env bash
set -euo pipefail

WITH_CHROME=1
if [[ "${1:-}" == "--without-chrome" ]]; then
  WITH_CHROME=0
elif [[ -n "${1:-}" ]]; then
  echo "Usage: scripts/wsl/setup-test-env.sh [--without-chrome]" >&2
  exit 2
fi

if [[ -z "${WSL_DISTRO_NAME:-}" ]] && ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "This setup is intended for an Ubuntu distribution running under WSL 2." >&2
  exit 1
fi

if [[ "$(id -u)" -eq 0 ]]; then
  SUDO=()
elif command -v sudo >/dev/null 2>&1; then
  SUDO=(sudo)
else
  echo "Run this script as root or install sudo first." >&2
  exit 1
fi

echo "Installing WSLg test dependencies..."
"${SUDO[@]}" apt-get update
"${SUDO[@]}" apt-get install -y \
  curl \
  dbus-x11 \
  ffmpeg \
  fonts-noto-color-emoji \
  jq \
  mesa-utils \
  pulseaudio-utils \
  python3 \
  python3-tk \
  python3-websocket \
  vlc \
  wmctrl \
  x11-apps \
  xdotool

if [[ "$WITH_CHROME" == "1" ]] && ! command -v google-chrome >/dev/null 2>&1; then
  if [[ "$(dpkg --print-architecture)" != "amd64" ]]; then
    echo "Google Chrome's Linux package is only installed automatically on amd64; skipping."
  else
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    curl -fsSL \
      -o "$TMP_DIR/google-chrome-stable_current_amd64.deb" \
      https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
    "${SUDO[@]}" apt-get install -y "$TMP_DIR/google-chrome-stable_current_amd64.deb"
  fi
fi

echo
echo "WSLg test environment is ready."
echo "Run: bash scripts/wsl/run-gui-smoke.sh"
