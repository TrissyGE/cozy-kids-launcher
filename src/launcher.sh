#!/usr/bin/env bash
set -euo pipefail
APP_ROOT="$HOME/.local/share/{{APP_ID}}"
PORT="${COZY_KIDS_PORT:-{{DEFAULT_PORT}}}"
PIDFILE="$HOME/.cache/{{APP_ID}}/server.pid"
BROWSER_PIDFILE="$HOME/.cache/{{APP_ID}}/browser.pid"
URL="http://127.0.0.1:${PORT}/index.html"
LAUNCH_MODE="{{DEFAULT_LAUNCH_MODE}}"
mkdir -p "$HOME/.cache/{{APP_ID}}"
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
    "$BROWSER_CMD" --new-window --kiosk "$URL" &
    ;;
  fullscreen)
    "$BROWSER_CMD" --new-window --fullscreen "$URL" &
    ;;
  window|*)
    "$BROWSER_CMD" --new-window "$URL" &
    ;;
esac
BROWSER_PID=$!
echo "$BROWSER_PID" > "$BROWSER_PIDFILE"
wait "$BROWSER_PID"
