#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="$HOME/.local/share/{{APP_ID}}"
PORT="${COZY_KIDS_PORT:-{{DEFAULT_PORT}}}"
PIDFILE="$HOME/.cache/{{APP_ID}}/server.pid"
BROWSER_PIDFILE="$HOME/.cache/{{APP_ID}}/browser.pid"
URL="http://127.0.0.1:${PORT}/index.html"
LAUNCH_MODE="{{DEFAULT_LAUNCH_MODE}}"
mkdir -p "$HOME/.cache/{{APP_ID}}"
while true; do
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null; then
    :
  else
    cd "$APP_ROOT"
    COZY_KIDS_ENABLE_SHUTDOWN="{{INSTALL_SHUTDOWN_HELPER}}" \
    COZY_KIDS_PORT="$PORT" \
    python3 "$APP_ROOT/server.py" >/dev/null 2>&1 &
    sleep 1
  fi
  case "$LAUNCH_MODE" in
    kiosk)
      "{{BROWSER_CMD}}" --new-window --kiosk "$URL" >/dev/null 2>&1 &
      ;;
    fullscreen)
      "{{BROWSER_CMD}}" --new-window --fullscreen "$URL" >/dev/null 2>&1 &
      ;;
    window|*)
      "{{BROWSER_CMD}}" --new-window "$URL" >/dev/null 2>&1 &
      ;;
  esac
  sleep 1
  BROWSER_PID=$(pgrep -n -x "firefox" 2>/dev/null || pgrep -n -x "chromium" 2>/dev/null || pgrep -n -x "chromium-browser" 2>/dev/null || pgrep -n -x "google-chrome" 2>/dev/null || echo "$!")
  echo "$BROWSER_PID" > "$BROWSER_PIDFILE"
  # Poll until browser exits or update trigger appears
  while kill -0 "$BROWSER_PID" 2>/dev/null; do
    if [[ -f "$APP_ROOT/update-trigger.sh" ]]; then
      break
    fi
    sleep 1
  done
  if [[ -f "$APP_ROOT/update-trigger.sh" ]]; then
    if [[ -f "$PIDFILE" ]]; then
      kill "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null || true
      rm -f "$PIDFILE"
    fi
    ZENITY_PID=""
    if command -v zenity >/dev/null 2>&1; then
      (zenity --progress --pulsate --title="{{APP_NAME}}" --text="Updating... please wait" --no-cancel --auto-close) >/dev/null 2>&1 &
      ZENITY_PID=$!
    fi
    bash "$APP_ROOT/update-trigger.sh"
    if [[ -n "$ZENITY_PID" ]]; then
      kill "$ZENITY_PID" 2>/dev/null || true
      wait "$ZENITY_PID" 2>/dev/null || true
    fi
    rm -f "$APP_ROOT/update-trigger.sh"
    # Wait for any lingering browser processes to release profile locks
    sleep 3
    # loop back to restart with updated files
  else
    break
  fi
done
