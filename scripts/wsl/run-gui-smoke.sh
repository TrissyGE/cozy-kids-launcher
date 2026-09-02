#!/usr/bin/env bash
set -euo pipefail

VISIBLE=1
VISIBLE_SECONDS=7
PORT="${COZY_KIDS_TEST_PORT:-38439}"

usage() {
  cat <<'EOF'
Usage: scripts/wsl/run-gui-smoke.sh [--headless] [--visible-seconds N]

Runs an isolated WSLg smoke test without touching the normal launcher profile.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --headless)
      VISIBLE=0
      shift
      ;;
    --visible-seconds)
      [[ $# -ge 2 ]] || { usage >&2; exit 2; }
      VISIBLE_SECONDS="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
done

if [[ -z "${WSL_DISTRO_NAME:-}" ]] && ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "This test must run inside WSL 2." >&2
  exit 1
fi
if [[ -z "${DISPLAY:-}" ]] || [[ -z "${PULSE_SERVER:-}" ]]; then
  echo "WSLg display or audio forwarding is unavailable. Run 'wsl --update' in Windows first." >&2
  exit 1
fi
if ! [[ "$VISIBLE_SECONDS" =~ ^[1-9][0-9]*$ ]]; then
  echo "--visible-seconds must be a positive integer." >&2
  exit 2
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_ROOT="${COZY_KIDS_TEST_ROOT:-$HOME/.local/state/cozy-kids-launcher/wsl-smoke}"
TEST_HOME="$TEST_ROOT/home"
ARTIFACTS="$TEST_ROOT/artifacts"
LOGS="$TEST_ROOT/logs"
MEDIA="$TEST_HOME/Videos"
SERVER_PID=""

mkdir -p "$TEST_HOME" "$ARTIFACTS" "$LOGS" "$MEDIA" "$TEST_HOME/Music"
HEADLESS_PROFILES="$(mktemp -d "$TEST_ROOT/headless-profiles.XXXXXX")"

cleanup() {
  process_state="$TEST_HOME/.local/share/cozy-kids-launcher/process_state.py"
  if [[ -f "$process_state" ]]; then
    HOME="$TEST_HOME" python3 "$process_state" terminate \
      "$TEST_HOME/.cache/cozy-kids-launcher/overlay.pid" overlay >/dev/null 2>&1 || true
    HOME="$TEST_HOME" python3 "$process_state" terminate \
      "$TEST_HOME/.cache/cozy-kids-launcher/tile-process.pid" tile-process >/dev/null 2>&1 || true
  fi
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  pkill -f -- "--user-data-dir=$HEADLESS_PROFILES/" 2>/dev/null || true
  case "$HEADLESS_PROFILES" in
    "$TEST_ROOT"/headless-profiles.*)
      rm -rf -- "$HEADLESS_PROFILES"
      ;;
  esac
}
trap cleanup EXIT

required=(curl ffmpeg ffprobe glxinfo pactl python3 vlc)
for command_name in "${required[@]}"; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing dependency: $command_name" >&2
    echo "Run: sudo bash scripts/wsl/setup-test-env.sh" >&2
    exit 1
  }
done
python3 -c 'import websocket' >/dev/null 2>&1 || {
  echo "Missing Python websocket module. Run: sudo bash scripts/wsl/setup-test-env.sh" >&2
  exit 1
}

if command -v google-chrome >/dev/null 2>&1; then
  BROWSER=google-chrome
elif command -v google-chrome-stable >/dev/null 2>&1; then
  BROWSER=google-chrome-stable
elif command -v chromium >/dev/null 2>&1; then
  BROWSER=chromium
else
  echo "A Chromium-family browser is required for this smoke test." >&2
  exit 1
fi

if [[ -e /dev/dxg ]] && [[ -z "${GALLIUM_DRIVER:-}" ]]; then
  export GALLIUM_DRIVER=d3d12
fi

echo "[1/8] Verifying WSLg display, audio, and graphics"
pactl info > "$LOGS/pulseaudio.txt"
glxinfo -B > "$LOGS/opengl.txt"
grep -E "OpenGL vendor|OpenGL renderer" "$LOGS/opengl.txt" || true

echo "[2/8] Creating deterministic video and audio fixtures"
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=960x540:rate=30" \
  -f lavfi -i "sine=frequency=523:sample_rate=48000" \
  -t 4 -shortest -c:v libx264 -pix_fmt yuv420p -c:a aac \
  "$MEDIA/cozy-kids-test.mp4"
ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "sine=frequency=659:sample_rate=48000" \
  -t 3 "$TEST_HOME/Music/cozy-kids-test.wav"
ffprobe -v error -show_entries stream=codec_type,codec_name \
  -of json "$MEDIA/cozy-kids-test.mp4" > "$ARTIFACTS/media-fixture.json"

echo "[3/8] Installing an isolated launcher profile"
bash "$REPO_DIR/scripts/install.sh" \
  --user "$(id -un)" \
  --home "$TEST_HOME" \
  --lang en \
  --browser "$BROWSER" \
  --launch-mode window \
  --force > "$LOGS/install.txt"
test -x "$TEST_HOME/.local/share/cozy-kids-launcher/update.sh"

python3 - "$TEST_HOME/.config/cozy-kids-launcher/config.json" "$BROWSER" <<'PY'
import json
import sys

path = sys.argv[1]
browser = sys.argv[2]
with open(path, encoding="utf-8") as handle:
    config = json.load(handle)
config["setupCompleted"] = True
config["browser"] = browser
profile = next(
    profile
    for profile in config["profiles"]
    if profile["id"] == config["activeProfileId"]
)
profile["tiles"].extend([
    {
        "id": "wsl-embedded",
        "label": "Embedded web test",
        "emoji": "🧪",
        "cmd": ["special:browser:https://example.com"],
        "visible": True,
    },
    {
        "id": "wsl-external",
        "label": "External web test",
        "emoji": "🌐",
        "cmd": ["special:external-browser:https://example.com"],
        "visible": True,
    },
])
with open(path, "w", encoding="utf-8") as handle:
    json.dump(config, handle, ensure_ascii=False, indent=2)
    handle.write("\n")
PY

echo "[4/8] Starting the local server and checking its API"
HOME="$TEST_HOME" COZY_KIDS_PORT="$PORT" \
  python3 "$TEST_HOME/.local/share/cozy-kids-launcher/server.py" \
  > "$LOGS/server.txt" 2>&1 &
SERVER_PID=$!
for _ in $(seq 1 50); do
  if curl -fsS "http://127.0.0.1:$PORT/api/config" > "$ARTIFACTS/config.json" 2>/dev/null; then
    break
  fi
  sleep 0.1
done
curl -fsS "http://127.0.0.1:$PORT/api/config" >/dev/null

echo "[5/8] Rendering launcher and current website screenshots"
HOME="$TEST_HOME" python3 "$REPO_DIR/scripts/wsl/capture-page.py" \
  --browser "$BROWSER" \
  --profile "$HEADLESS_PROFILES/launcher" \
  --output "$ARTIFACTS/launcher.png" \
  --url "http://127.0.0.1:$PORT/index.html" \
  --ready-expression "document.querySelectorAll('#grid .tile:not(.placeholder)').length > 0" \
  > "$LOGS/chrome-launcher.txt" 2>&1
if ! HOME="$TEST_HOME" python3 "$REPO_DIR/scripts/wsl/capture-page.py" \
  --browser "$BROWSER" \
  --profile "$HEADLESS_PROFILES/direct-kika" \
  --output "$ARTIFACTS/direct-kika.png" \
  --url "https://www.kika.de" \
  --ready-expression "document.body && document.body.innerText.length > 100" \
  > "$LOGS/chrome-kika.txt" 2>&1; then
  echo "KiKA screenshot unavailable; the independent HTTP probe will still run."
fi

echo "[6/8] Exercising the unified media launch route"
curl -fsS -X POST "http://127.0.0.1:$PORT/launch/music" >/dev/null
sleep 1
pgrep -f "vlc.*$TEST_HOME/Videos" > "$ARTIFACTS/vlc-pids.txt"

echo "[7/8] Exercising embedded and external web launch routes"
embedded_location="$(curl -sS -o /dev/null -w '%{redirect_url}' -X POST \
  "http://127.0.0.1:$PORT/launch/wsl-embedded")"
[[ "$embedded_location" == *"/browser.html?url="* ]]
if [[ "$VISIBLE" == "1" ]]; then
  curl -fsS -X POST "http://127.0.0.1:$PORT/launch/wsl-external" >/dev/null
  sleep "$VISIBLE_SECONDS"
fi

echo "[8/8] Probing current web recommendations"
python3 "$REPO_DIR/scripts/wsl/probe-web-targets.py" --json \
  > "$ARTIFACTS/web-targets.json" || true

echo
echo "WSLg smoke test passed."
echo "Artifacts: $ARTIFACTS"
echo "Logs:      $LOGS"
