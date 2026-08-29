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
LIFECYCLE_STATE_FILE="$CACHE_ROOT/lifecycle.json"
LIFECYCLE_REQUEST_FILE="$CACHE_ROOT/lifecycle-request.json"
LOCK_FILE="$CACHE_ROOT/launcher.lock"
PROCESS_STATE="$APP_ROOT/process_state.py"
LIFECYCLE_STATE_SCRIPT="$APP_ROOT/lifecycle_state.py"
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
CHROMIUM_FLAGS=(
  --user-data-dir="$CHROMIUM_PROFILE"
  --no-first-run
  --password-store=basic
  --hide-crash-restore-bubble
  --disable-session-crashed-bubble
  --disable-translate
  --disable-features=Translate
)
mkdir -p "$CACHE_ROOT" "$CHROMIUM_PROFILE" "$FIREFOX_PROFILE"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  exit 0
fi
if [[ "${1:-}" == "--autostart" ]]; then
  # A cold GNOME boot can reach graphical-session.target well before Mutter
  # applies browser fullscreen requests reliably. Desktop/manual launches stay
  # immediate; only login autostart waits for the compositor to settle.
  sleep 30
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
ACTIVE_RECOVERY_ATTEMPT=0
SERVER_CHILD_PID=""
WATCHDOG_CHILD_PID=""
BROWSER_CHILD_PID=""
LIFECYCLE_STATE="starting"
LIFECYCLE_STOP_REASON="session-ended"
LIFECYCLE_FAILURE_REASON="unexpected-exit"
RUNTIME_START_REASON="initial-start"

lifecycle_begin() {
  local reason="$1"
  if python3 "$LIFECYCLE_STATE_SCRIPT" begin "$LIFECYCLE_STATE_FILE" "$reason" 9>&- >/dev/null 2>&1; then
    LIFECYCLE_STATE="starting"
  fi
}

lifecycle_transition() {
  local state="$1"
  local reason="$2"
  local attempt="${3:-}"
  if [[ -n "$attempt" ]]; then
    if python3 "$LIFECYCLE_STATE_SCRIPT" transition "$LIFECYCLE_STATE_FILE" "$state" "$reason" --attempt "$attempt" 9>&- >/dev/null 2>&1; then
      LIFECYCLE_STATE="$state"
    fi
  elif python3 "$LIFECYCLE_STATE_SCRIPT" transition "$LIFECYCLE_STATE_FILE" "$state" "$reason" 9>&- >/dev/null 2>&1; then
    LIFECYCLE_STATE="$state"
  fi
  return 0
}

consume_lifecycle_request() {
  python3 "$LIFECYCLE_STATE_SCRIPT" consume-request "$LIFECYCLE_REQUEST_FILE" 9>&- 2>/dev/null || true
}

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

configure_chromium_profile() {
  local preferences="$CHROMIUM_PROFILE/Default/Preferences"
  mkdir -p "$(dirname "$preferences")"
  python3 - "$preferences" "$LAUNCH_MODE" 9>&- <<'PY' >/dev/null 2>&1 || true
import json
import os
import sys
import tempfile

path = sys.argv[1]
launch_mode = sys.argv[2]
preferences = {}
if os.path.exists(path):
    try:
        with open(path, encoding="utf-8") as source:
            preferences = json.load(source)
    except (OSError, ValueError):
        raise SystemExit(0)

translate = preferences.setdefault("translate", {})
if not isinstance(translate, dict):
    translate = {}
    preferences["translate"] = translate
translate["enabled"] = False

# Chromium can prefer a cached maximized/windowed placement over a later
# --start-fullscreen or --kiosk request. Remove only that placement when an
# explicit display mode is selected; ordinary window mode keeps user geometry.
if launch_mode in ("fullscreen", "kiosk"):
    browser = preferences.get("browser")
    if isinstance(browser, dict):
        browser.pop("window_placement", None)

fd, temporary = tempfile.mkstemp(prefix="Preferences.", dir=os.path.dirname(path))
try:
    with os.fdopen(fd, "w", encoding="utf-8") as destination:
        json.dump(preferences, destination, separators=(",", ":"))
        destination.write("\n")
        destination.flush()
        os.fsync(destination.fileno())
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
PY
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
  local status=$?
  stop_runtime_children
  if [[ "$status" -ne 0 ]]; then
    if [[ "$LIFECYCLE_STATE" != "failed" ]]; then
      lifecycle_transition failed "$LIFECYCLE_FAILURE_REASON"
    fi
  elif [[ "$LIFECYCLE_STATE" != "failed" ]]; then
    if [[ "$LIFECYCLE_STATE" != "stopping" ]]; then
      lifecycle_transition stopping "$LIFECYCLE_STOP_REASON"
    fi
    if [[ "$LIFECYCLE_STATE" == "stopping" ]]; then
      lifecycle_transition stopped "$LIFECYCLE_STOP_REASON"
    fi
  fi
  return 0
}

show_recovery_failure() {
  echo "{{RUNTIME_FAILURE_BODY}}" >&2
  if command -v zenity >/dev/null 2>&1 && [[ -n "${DISPLAY:-}${WAYLAND_DISPLAY:-}" ]]; then
    zenity --error --timeout=15 --title="{{RUNTIME_FAILURE_TITLE}}" --text="{{RUNTIME_FAILURE_BODY}}" 9>&- >/dev/null 2>&1 || true
  fi
}

schedule_recovery() {
  local failure_reason="$1"
  local now delay
  now="$(date +%s)"
  if (( RECOVERY_WINDOW_STARTED == 0 || now - RECOVERY_WINDOW_STARTED > RECOVERY_WINDOW_SECONDS )); then
    RECOVERY_WINDOW_STARTED="$now"
    RECOVERY_ATTEMPTS=0
  fi
  RECOVERY_ATTEMPTS="$((RECOVERY_ATTEMPTS + 1))"
  if (( RECOVERY_ATTEMPTS > RECOVERY_MAX_ATTEMPTS )); then
    LIFECYCLE_FAILURE_REASON="recovery-exhausted"
    lifecycle_transition failed recovery-exhausted
    stop_runtime_children
    show_recovery_failure
    return 1
  fi
  lifecycle_transition recovering "$failure_reason" "$RECOVERY_ATTEMPTS"
  stop_runtime_children
  NEXT_RECOVERY_ATTEMPT="$RECOVERY_ATTEMPTS"
  delay="$((RECOVERY_BACKOFF_SECONDS * RECOVERY_ATTEMPTS))"
  echo "Cozy Kids Launcher is recovering the runtime (attempt ${RECOVERY_ATTEMPTS}/${RECOVERY_MAX_ATTEMPTS})." >&2
  if (( delay > 0 )); then
    sleep "$delay" 9>&-
  fi
  lifecycle_transition starting recovery "$RECOVERY_ATTEMPTS"
  RUNTIME_START_REASON="recovery"
  return 0
}

handle_signal() {
  local signal_name="$1"
  local requested_reason
  requested_reason="$(consume_lifecycle_request)"
  if [[ -n "$requested_reason" ]]; then
    LIFECYCLE_STOP_REASON="$requested_reason"
  elif [[ "$signal_name" == "HUP" || "$signal_name" == "TERM" ]]; then
    LIFECYCLE_STOP_REASON="logout"
  elif [[ "$signal_name" == "INT" ]]; then
    LIFECYCLE_STOP_REASON="manual-stop"
  else
    LIFECYCLE_STOP_REASON="session-ended"
  fi
  lifecycle_transition stopping "$LIFECYCLE_STOP_REASON"
  exit 0
}

trap cleanup_runtime EXIT
trap 'handle_signal HUP' HUP
trap 'handle_signal INT' INT
trap 'handle_signal TERM' TERM

rm -f "$LIFECYCLE_REQUEST_FILE"
lifecycle_begin initial-start

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
      if schedule_recovery startup-failed; then
        continue
      fi
      exit 1
    fi
    ACTIVE_RECOVERY_ATTEMPT="$NEXT_RECOVERY_ATTEMPT"
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
  if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
    configure_chromium_profile
  fi
  case "$LAUNCH_MODE" in
    kiosk)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" "${CHROMIUM_FLAGS[@]}" --kiosk "$URL" 9>&- >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --no-remote --profile "$FIREFOX_PROFILE" --new-window --kiosk "$URL" 9>&- >/dev/null 2>&1 &
      fi
      ;;
    fullscreen)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" "${CHROMIUM_FLAGS[@]}" --start-fullscreen "$URL" 9>&- >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --no-remote --profile "$FIREFOX_PROFILE" --new-window --fullscreen "$URL" 9>&- >/dev/null 2>&1 &
      fi
      ;;
    window|*)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" "${CHROMIUM_FLAGS[@]}" "$URL" 9>&- >/dev/null 2>&1 &
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
    LIFECYCLE_FAILURE_REASON="browser-start-failed"
    lifecycle_transition failed browser-start-failed
    show_recovery_failure
    exit 1
  fi
  if [[ "$RUNTIME_START_REASON" == "recovery" ]]; then
    lifecycle_transition running recovered "$ACTIVE_RECOVERY_ATTEMPT"
  elif [[ "$RUNTIME_START_REASON" == "update-complete" ]]; then
    lifecycle_transition running update-complete
  else
    lifecycle_transition running ready
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
    LIFECYCLE_STOP_REASON="$(consume_lifecycle_request)"
    LIFECYCLE_STOP_REASON="${LIFECYCLE_STOP_REASON:-parent-exit}"
    lifecycle_transition stopping "$LIFECYCLE_STOP_REASON"
    rm -f "$EXIT_FLAGFILE"
    break
  elif [[ "$RUNTIME_REASON" == "server-failed" ]]; then
    if schedule_recovery server-failed; then
      continue
    fi
    exit 1
  elif [[ "$RUNTIME_REASON" == "update" ]]; then
    lifecycle_transition updating update-requested
    LIFECYCLE_FAILURE_REASON="update-failed"
    stop_runtime_children
    ZENITY_PID=""
    if command -v zenity >/dev/null 2>&1; then
      (zenity --progress --pulsate --title="{{APP_NAME}}" --text="Updating... please wait" --no-cancel --auto-close) 9>&- >/dev/null 2>&1 &
      ZENITY_PID=$!
    fi
    UPDATE_STATUS=0
    bash "$APP_ROOT/update-trigger.sh" 9>&- || UPDATE_STATUS=$?
    if [[ -n "$ZENITY_PID" ]]; then
      kill "$ZENITY_PID" 2>/dev/null || true
      wait "$ZENITY_PID" 2>/dev/null || true
    fi
    rm -f "$APP_ROOT/update-trigger.sh"
    if [[ "$UPDATE_STATUS" -ne 0 ]]; then
      exit "$UPDATE_STATUS"
    fi
    # Wait for any lingering browser processes to release profile locks
    sleep 3 9>&-
    RECOVERY_ATTEMPTS=0
    RECOVERY_WINDOW_STARTED=0
    lifecycle_transition starting update-complete
    RUNTIME_START_REASON="update-complete"
    LIFECYCLE_FAILURE_REASON="unexpected-exit"
    # loop back to restart with updated files
  else
    LIFECYCLE_STOP_REASON="browser-exited"
    lifecycle_transition stopping browser-exited
    remove_process_record "$BROWSER_PIDFILE" "$BROWSER_CHILD_PID"
    wait_for_child "$BROWSER_CHILD_PID"
    BROWSER_CHILD_PID=""
    break
  fi
done
