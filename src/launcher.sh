#!/usr/bin/env bash
set -euo pipefail
if [[ -d /snap/bin ]] && [[ ":$PATH:" != *":/snap/bin:"* ]]; then
  export PATH="$PATH:/snap/bin"
fi
APP_ROOT="$HOME/.local/share/{{APP_ID}}"
PORT="${COZY_KIDS_PORT:-{{DEFAULT_PORT}}}"
CACHE_ROOT="$HOME/.cache/{{APP_ID}}"
PIDFILE="$CACHE_ROOT/server.pid"
BROWSER_PIDFILE="$CACHE_ROOT/browser.pid"
EXIT_FLAGFILE="$CACHE_ROOT/exit-requested"
WATCHDOG_PIDFILE="$CACHE_ROOT/watchdog.pid"
LOCK_FILE="$CACHE_ROOT/launcher.lock"
PROCESS_STATE="$APP_ROOT/process_state.py"
URL="http://127.0.0.1:${PORT}/index.html"
LAUNCH_MODE="{{DEFAULT_LAUNCH_MODE}}"
BROWSER_CMD="{{BROWSER_CMD}}"
BROWSER_OVERRIDE="$HOME/.config/{{APP_ID}}/browser"
if [[ -f "$BROWSER_OVERRIDE" ]]; then
  BROWSER_CMD="$(cat "$BROWSER_OVERRIDE")"
fi
BROWSER_BIN=$(basename "$BROWSER_CMD")

case "$BROWSER_BIN" in
  chromium|chromium-browser|google-chrome|google-chrome-stable|brave|brave-browser|opera|opera-stable|vivaldi|vivaldi-stable|microsoft-edge|microsoft-edge-stable|edge|cachy-browser)
    BROWSER_FAMILY="chromium"
    ;;
  firefox|firefox-esr|librewolf)
    BROWSER_FAMILY="firefox"
    ;;
  *)
    BROWSER_FAMILY="firefox"
    ;;
esac

CHROMIUM_PROFILE="$HOME/.cache/{{APP_ID}}/chromium-profile"
FIREFOX_PROFILE="$HOME/.cache/{{APP_ID}}/firefox-profile"
mkdir -p "$CACHE_ROOT" "$CHROMIUM_PROFILE" "$FIREFOX_PROFILE"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi

process_alive() {
  python3 "$PROCESS_STATE" alive "$1" "$2" 9>&- >/dev/null 2>&1
}

record_process() {
  python3 "$PROCESS_STATE" record "$1" "$2" "$3" 9>&- >/dev/null 2>&1
}

remove_process_record() {
  python3 "$PROCESS_STATE" remove "$1" --pid "$2" 9>&- >/dev/null 2>&1 || true
}

terminate_process() {
  python3 "$PROCESS_STATE" terminate "$1" "$2" 9>&- >/dev/null 2>&1 || true
}

cleanup_runtime() {
  terminate_process "$BROWSER_PIDFILE" browser
  terminate_process "$WATCHDOG_PIDFILE" watchdog
  terminate_process "$PIDFILE" server
}

handle_signal() {
  exit 0
}

trap cleanup_runtime EXIT
trap handle_signal HUP INT TERM

while true; do
  if ! process_alive "$PIDFILE" server; then
    cd "$APP_ROOT"
    COZY_KIDS_ENABLE_SHUTDOWN="{{INSTALL_SHUTDOWN_HELPER}}" \
    COZY_KIDS_PORT="$PORT" \
    python3 "$APP_ROOT/server.py" 9>&- >/dev/null 2>&1 &
    SERVER_START_PID="$!"
    for _server_attempt in $(seq 1 50); do
      process_alive "$PIDFILE" server && break
      kill -0 "$SERVER_START_PID" 2>/dev/null || break
      sleep 0.1 9>&-
    done
    if ! process_alive "$PIDFILE" server; then
      wait "$SERVER_START_PID" 2>/dev/null || true
      echo "Cozy Kids Launcher server failed to start." >&2
      exit 1
    fi
  fi
  if [[ -f "$APP_ROOT/timer_watchdog.py" ]] && ! process_alive "$WATCHDOG_PIDFILE" watchdog; then
    python3 "$APP_ROOT/timer_watchdog.py" --port "$PORT" 9>&- >/dev/null 2>&1 &
    WATCHDOG_PID="$!"
    if ! record_process "$WATCHDOG_PIDFILE" "$WATCHDOG_PID" watchdog; then
      kill "$WATCHDOG_PID" 2>/dev/null || true
      wait "$WATCHDOG_PID" 2>/dev/null || true
    fi
  fi
  case "$LAUNCH_MODE" in
    kiosk)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" --user-data-dir="$CHROMIUM_PROFILE" --no-first-run --disable-session-crashed-bubble --kiosk "$URL" 9>&- >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --no-remote --profile "$FIREFOX_PROFILE" --new-window --kiosk "$URL" 9>&- >/dev/null 2>&1 &
      fi
      ;;
    fullscreen)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" --user-data-dir="$CHROMIUM_PROFILE" --no-first-run --disable-session-crashed-bubble --fullscreen "$URL" 9>&- >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --no-remote --profile "$FIREFOX_PROFILE" --new-window --fullscreen "$URL" 9>&- >/dev/null 2>&1 &
      fi
      ;;
    window|*)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" --user-data-dir="$CHROMIUM_PROFILE" --no-first-run --disable-session-crashed-bubble "$URL" 9>&- >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --no-remote --profile "$FIREFOX_PROFILE" --new-window "$URL" 9>&- >/dev/null 2>&1 &
      fi
      ;;
  esac
  BROWSER_PID="$!"
  if ! record_process "$BROWSER_PIDFILE" "$BROWSER_PID" browser; then
    kill "$BROWSER_PID" 2>/dev/null || true
    wait "$BROWSER_PID" 2>/dev/null || true
    echo "Cozy Kids Launcher browser failed to start." >&2
    exit 1
  fi
  # Poll until browser exits, update trigger appears, or exit is requested
  while process_alive "$BROWSER_PIDFILE" browser; do
    if [[ -f "$APP_ROOT/update-trigger.sh" ]]; then
      break
    fi
    if [[ -f "$EXIT_FLAGFILE" ]]; then
      rm -f "$EXIT_FLAGFILE"
      break 2
    fi
    sleep 1 9>&-
  done
  if [[ -f "$APP_ROOT/update-trigger.sh" ]]; then
    terminate_process "$BROWSER_PIDFILE" browser
    terminate_process "$WATCHDOG_PIDFILE" watchdog
    terminate_process "$PIDFILE" server
    ZENITY_PID=""
    if command -v zenity >/dev/null 2>&1; then
      (zenity --progress --pulsate --title="{{APP_NAME}}" --text="Updating... please wait" --no-cancel --auto-close) 9>&- >/dev/null 2>&1 &
      ZENITY_PID=$!
    fi
    bash "$APP_ROOT/update-trigger.sh" 9>&-
    if [[ -n "$ZENITY_PID" ]]; then
      kill "$ZENITY_PID" 2>/dev/null || true
      wait "$ZENITY_PID" 2>/dev/null || true
    fi
    rm -f "$APP_ROOT/update-trigger.sh"
    # Wait for any lingering browser processes to release profile locks
    sleep 3 9>&-
    # loop back to restart with updated files
  else
    remove_process_record "$BROWSER_PIDFILE" "$BROWSER_PID"
    break
  fi
done
