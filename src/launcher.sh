#!/usr/bin/env bash
set -euo pipefail
if [[ -d /snap/bin ]] && [[ ":$PATH:" != *":/snap/bin:"* ]]; then
  export PATH="$PATH:/snap/bin"
fi
APP_ROOT="$HOME/.local/share/{{APP_ID}}"
PORT="${COZY_KIDS_PORT:-{{DEFAULT_PORT}}}"
PIDFILE="$HOME/.cache/{{APP_ID}}/server.pid"
BROWSER_PIDFILE="$HOME/.cache/{{APP_ID}}/browser.pid"
EXIT_FLAGFILE="$HOME/.cache/{{APP_ID}}/exit-requested"
URL="http://127.0.0.1:${PORT}/index.html"
LAUNCH_MODE="{{DEFAULT_LAUNCH_MODE}}"
BROWSER_CMD="{{BROWSER_CMD}}"
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
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" --user-data-dir="$CHROMIUM_PROFILE" --no-first-run --disable-session-crashed-bubble --kiosk "$URL" >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --new-window --kiosk "$URL" >/dev/null 2>&1 &
      fi
      ;;
    fullscreen)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" --user-data-dir="$CHROMIUM_PROFILE" --no-first-run --disable-session-crashed-bubble --fullscreen "$URL" >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --new-window --fullscreen "$URL" >/dev/null 2>&1 &
      fi
      ;;
    window|*)
      if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
        "$BROWSER_CMD" --user-data-dir="$CHROMIUM_PROFILE" --no-first-run --disable-session-crashed-bubble "$URL" >/dev/null 2>&1 &
      else
        "$BROWSER_CMD" --new-window "$URL" >/dev/null 2>&1 &
      fi
      ;;
  esac
  sleep 1
  BROWSER_PID="$!"
  if [[ "$BROWSER_FAMILY" == "chromium" ]]; then
    # Chromium forks many child processes (--type=renderer, gpu, etc.).
    # The main process is the one without a --type= flag.
    for _b in chromium chromium-browser google-chrome google-chrome-stable chrome brave brave-browser opera opera-stable vivaldi vivaldi-stable microsoft-edge microsoft-edge-stable edge cachy-browser; do
      _pid=$(pgrep -a -x "$_b" 2>/dev/null | grep -v -- "--type=" | awk '{print $1}' | tail -1 || true)
      if [[ -n "$_pid" ]]; then
        BROWSER_PID="$_pid"
        break
      fi
    done
  else
    # Firefox: the $! wrapper execs into the real process, but $! may
    # have been a transient wrapper. Fall back to pgrep if $! is dead.
    if ! kill -0 "$BROWSER_PID" 2>/dev/null; then
      for _b in firefox firefox-esr librewolf; do
        _pid=$(pgrep -n -x "$_b" 2>/dev/null) && { BROWSER_PID="$_pid"; break; }
      done
    fi
  fi
  echo "$BROWSER_PID" > "$BROWSER_PIDFILE"
  # Poll until browser exits, update trigger appears, or exit is requested
  while kill -0 "$BROWSER_PID" 2>/dev/null; do
    if [[ -f "$APP_ROOT/update-trigger.sh" ]]; then
      break
    fi
    if [[ -f "$EXIT_FLAGFILE" ]]; then
      rm -f "$EXIT_FLAGFILE"
      break 2
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
