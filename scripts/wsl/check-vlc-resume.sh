#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${WSL_DISTRO_NAME:-}" ]] && ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "This test must run inside WSL 2." >&2
  exit 1
fi
for command_name in ffmpeg python3 vlc; do
  command -v "$command_name" >/dev/null 2>&1 || {
    echo "Missing dependency: $command_name" >&2
    echo "Run: sudo bash scripts/wsl/setup-test-env.sh" >&2
    exit 1
  }
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
TEST_ROOT="$(mktemp -d)"
MEDIA_FILE="$TEST_ROOT/resume-test.mp4"
RESUME_ROOT="$TEST_ROOT/state"
MEDIA_ID="111111111111111111111111"
SESSION_PID=""
PROCESS_RECORD="$TEST_ROOT/tile-process.json"
SUPERVISOR="$REPO_DIR/src/process_supervisor.py"

cleanup() {
  if [[ -n "$SESSION_PID" ]] && kill -0 "$SESSION_PID" 2>/dev/null; then
    python3 "$REPO_DIR/src/process_state.py" terminate \
      "$PROCESS_RECORD" tile-process --marker "$SUPERVISOR" 2>/dev/null || true
    if kill -0 "$SESSION_PID" 2>/dev/null; then
      kill -TERM "$SESSION_PID" 2>/dev/null || true
    fi
    wait "$SESSION_PID" 2>/dev/null || true
  fi
  case "$TEST_ROOT" in
    /tmp/tmp.*)
      rm -rf -- "$TEST_ROOT"
      ;;
  esac
}
trap cleanup EXIT

ffmpeg -hide_banner -loglevel error -y \
  -f lavfi -i "testsrc2=size=320x180:rate=24" \
  -f lavfi -i "sine=frequency=523:sample_rate=48000" \
  -t 30 -shortest -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac \
  "$MEDIA_FILE"

start_session() {
  python3 "$SUPERVISOR" \
    --record "$PROCESS_RECORD" \
    --marker "$SUPERVISOR" \
    -- \
    python3 "$REPO_DIR/src/media_session.py" \
      --resume-root "$RESUME_ROOT" \
      --profile-id default \
      --media-id "$MEDIA_ID" \
      --media-path "$MEDIA_FILE" \
      -- vlc --intf=dummy --play-and-exit --no-video --aout=dummy "$MEDIA_FILE" &
  SESSION_PID=$!
  for _ in $(seq 1 50); do
    [[ -f "$PROCESS_RECORD" ]] && return
    sleep 0.1
  done
  echo "VLC resume supervisor did not publish its process record" >&2
  return 1
}

start_session
sleep 7
python3 "$REPO_DIR/src/process_state.py" terminate \
  "$PROCESS_RECORD" tile-process --marker "$SUPERVISOR"
wait "$SESSION_PID"
SESSION_PID=""

STATE_FILE="$RESUME_ROOT/default/vlc-positions.json"
SAVED_POSITION="$(python3 - "$STATE_FILE" "$MEDIA_ID" "$MEDIA_FILE" <<'PY'
import json
import sys

path, media_id, media_path = sys.argv[1:]
with open(path, encoding="utf-8") as handle:
    document = json.load(handle)
if document.get("resumeStateVersion") != 1 or len(document.get("items", [])) != 1:
    raise SystemExit("unexpected VLC resume document")
item = document["items"][0]
if set(item) != {"id", "positionSeconds", "mtimeNs", "size"}:
    raise SystemExit("unexpected VLC resume fields")
if item["id"] != media_id or not 5 <= item["positionSeconds"] < 20:
    raise SystemExit("VLC did not save a useful position")
payload = json.dumps(document)
if media_path in payload or media_path.rsplit("/", 1)[-1] in payload:
    raise SystemExit("VLC resume state exposed a media path")
print(item["positionSeconds"])
PY
)"

start_session
for _ in $(seq 1 50); do
  ADAPTER_PID="$(pgrep -P "$SESSION_PID" -f media_session.py | head -1 || true)"
  VLC_PID="$(pgrep -P "${ADAPTER_PID:-0}" -x vlc | head -1 || true)"
  [[ -n "$VLC_PID" ]] && break
  sleep 0.1
done
[[ -n "${VLC_PID:-}" ]]
tr '\0' '\n' < "/proc/$VLC_PID/cmdline" \
  | grep -Fx -- "--start-time=$SAVED_POSITION" >/dev/null
sleep 2
python3 "$REPO_DIR/src/process_state.py" terminate \
  "$PROCESS_RECORD" tile-process --marker "$SUPERVISOR"
wait "$SESSION_PID"
SESSION_PID=""
RESUMED_POSITION="$(python3 - "$STATE_FILE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    print(json.load(handle)["items"][0]["positionSeconds"])
PY
)"
[[ "$RESUMED_POSITION" -ge "$((SAVED_POSITION + 1))" ]]

echo "VLC per-profile resume smoke test passed."
