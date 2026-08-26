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
TILE_PROCESS_PIDFILE="$CACHE_ROOT/tile-process.pid"
OVERLAY_PIDFILE="$CACHE_ROOT/overlay.pid"
EXIT_FLAGFILE="$CACHE_ROOT/exit-requested"
WATCHDOG_PIDFILE="$CACHE_ROOT/watchdog.pid"
LOCK_FILE="$CACHE_ROOT/launcher.lock"
PROCESS_STATE="$APP_ROOT/process_state.py"
URL="http://127.0.0.1:${PORT}/index.html"
LAUNCH_MODE="{{DEFAULT_LAUNCH_MODE}}"
BROWSER_CMD="{{BROWSER_CMD}}"
BROWSER_OVERRIDE="$HOME/.config/{{APP_ID}}/browser"
RECOVERY_MAX_ATTEMPTS="${COZY_KIDS_RECOVERY_MAX_ATTEMPTS:-3}"
RECOVERY_WINDOW_SECONDS="${COZY_KIDS_RECOVERY_WINDOW_SECONDS:-60}"
RECOVERY_BACKOFF_SECONDS="${COZY_KIDS_RECOVERY_BACKOFF_SECONDS:-1}"
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

normalize_integer() {
  local value="$1"
  local fallback="$2"
  local minimum="$3"
  local maximum="$4"
  if [[ "$value" =~ ^[0-9]+$ ]] && (( ${#value} <= 9 )); then
    value="$((10#$value))"
    if (( value >= minimum && value <= maximum )); then
      printf '%d' "$value"
      return
    fi
  fi
  printf '%d' "$fallback"
}

RECOVERY_MAX_ATTEMPTS="$(normalize_integer "$RECOVERY_MAX_ATTEMPTS" 3 1 10)"
RECOVERY_WINDOW_SECONDS="$(normalize_integer "$RECOVERY_WINDOW_SECONDS" 60 1 3600)"
RECOVERY_BACKOFF_SECONDS="$(normalize_integer "$RECOVERY_BACKOFF_SECONDS" 1 0 60)"
RECOVERY_ATTEMPTS=0
RECOVERY_WINDOW_STARTED=0
NEXT_RECOVERY_ATTEMPT=0
SERVER_CHILD_PID=""
WATCHDOG_CHILD_PID=""
BROWSER_CHILD_PID=""

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

wait_for_child() {
  local pid="${1:-}"
  if [[ -n "$pid" ]]; then
    wait "$pid" 2>/dev/null || true
  fi
}

stop_runtime_children() {
  terminate_process "$OVERLAY_PIDFILE" overlay
  terminate_process "$TILE_PROCESS_PIDFILE" tile-process
  terminate_process "$BROWSER_PIDFILE" browser
  terminate_process "$WATCHDOG_PIDFILE" watchdog
  terminate_process "$PIDFILE" server
  wait_for_child "$BROWSER_CHILD_PID"
  wait_for_child "$WATCHDOG_CHILD_PID"
  wait_for_child "$SERVER_CHILD_PID"
  BROWSER_CHILD_PID=""
  WATCHDOG_CHILD_PID=""
  SERVER_CHILD_PID=""
}

cleanup_runtime() {
  stop_runtime_children
}

show_recovery_failure() {
  echo "{{RUNTIME_FAILURE_BODY}}" >&2
  if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    zenity --error --timeout=15 --title="{{RUNTIME_FAILURE_TITLE}}" --text="{{RUNTIME_FAILURE_BODY}}" 9>&- >/dev/null 2>&1 || true
  fi
}

schedule_recovery() {
  local now delay
  now="$(date +%s)"
  if (( RECOVERY_WINDOW_STARTED == 0 || now - RECOVERY_WINDOW_STARTED > RECOVERY_WINDOW_SECONDS )); then
    RECOVERY_WINDOW_STARTED="$now"
    RECOVERY_ATTEMPTS=0
  fi
  RECOVERY_ATTEMPTS="$((RECOVERY_ATTEMPTS + 1))"
  stop_runtime_children
  if (( RECOVERY_ATTEMPTS > RECOVERY_MAX_ATTEMPTS )); then
    show_recovery_failure
    return 1
  fi
  NEXT_RECOVERY_ATTEMPT="$RECOVERY_ATTEMPTS"
  delay="$((RECOVERY_BACKOFF_SECONDS * RECOVERY_ATTEMPTS))"
  echo "Cozy Kids Launcher is recovering the runtime (attempt ${RECOVERY_ATTEMPTS}/${RECOVERY_MAX_ATTEMPTS})." >&2
  if (( delay > 0 )); then
    sleep "$delay" 9>&-
  fi
  return 0
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
    COZY_KIDS_RECOVERY_ATTEMPT="$NEXT_RECOVERY_ATTEMPT" \
    python3 "$APP_ROOT/server.py" 9>&- >/dev/null 2>&1 &
    SERVER_CHILD_PID="$!"
    for _server_attempt in $(seq 1 50); do
      process_alive "$PIDFILE" server && break
      kill -0 "$SERVER_CHILD_PID" 2>/dev/null || break
      sleep 0.1 9>&-
    done
    if ! process_alive "$PIDFILE" server; then
      wait_for_child "$SERVER_CHILD_PID"
      SERVER_CHILD_PID=""
      if schedule_recovery; then
        continue
      fi
      exit 1
    fi
    NEXT_RECOVERY_ATTEMPT=0
  fi
  if [[ -f "$APP_ROOT/timer_watchdog.py" ]] && ! process_alive "$WATCHDOG_PIDFILE" watchdog; then
    python3 "$APP_ROOT/timer_watchdog.py" --port "$PORT" 9>&- >/dev/null 2>&1 &
    WATCHDOG_CHILD_PID="$!"
    if ! record_process "$WATCHDOG_PIDFILE" "$WATCHDOG_CHILD_PID" watchdog; then
      kill "$WATCHDOG_CHILD_PID" 2>/dev/null || true
      wait_for_child "$WATCHDOG_CHILD_PID"
      WATCHDOG_CHILD_PID=""
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
  BROWSER_CHILD_PID="$!"
  if ! record_process "$BROWSER_PIDFILE" "$BROWSER_CHILD_PID" browser; then
    kill "$BROWSER_CHILD_PID" 2>/dev/null || true
    wait_for_child "$BROWSER_CHILD_PID"
    BROWSER_CHILD_PID=""
    show_recovery_failure
    exit 1
  fi
  RUNTIME_REASON=""
  # Poll until browser exits, update/exit is requested, or the server fails.
  while process_alive "$BROWSER_PIDFILE" browser; do
    if [[ -f "$APP_ROOT/update-trigger.sh" ]]; then
      RUNTIME_REASON="update"
      break
    fi
    if [[ -f "$EXIT_FLAGFILE" ]]; then
      RUNTIME_REASON="exit"
      break
    fi
    if ! process_alive "$PIDFILE" server; then
      RUNTIME_REASON="server-failed"
      break
    fi
    sleep 1 9>&-
  done

  if [[ -z "$RUNTIME_REASON" ]]; then
    if [[ -f "$APP_ROOT/update-trigger.sh" ]]; then
      RUNTIME_REASON="update"
    elif [[ -f "$EXIT_FLAGFILE" ]]; then
      RUNTIME_REASON="exit"
    elif ! process_alive "$PIDFILE" server; then
      RUNTIME_REASON="server-failed"
    else
      RUNTIME_REASON="browser-exited"
    fi
  fi

  if [[ "$RUNTIME_REASON" == "exit" ]]; then
    rm -f "$EXIT_FLAGFILE"
    break
  elif [[ "$RUNTIME_REASON" == "server-failed" ]]; then
    if schedule_recovery; then
      continue
    fi
    exit 1
  elif [[ "$RUNTIME_REASON" == "update" ]]; then
    stop_runtime_children
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
    RECOVERY_ATTEMPTS=0
    RECOVERY_WINDOW_STARTED=0
    # loop back to restart with updated files
  else
    remove_process_record "$BROWSER_PIDFILE" "$BROWSER_CHILD_PID"
    wait_for_child "$BROWSER_CHILD_PID"
    BROWSER_CHILD_PID=""
    break
  fi
done
