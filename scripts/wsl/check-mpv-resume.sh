#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${WSL_DISTRO_NAME:-}" ]] && ! grep -qi microsoft /proc/version 2>/dev/null; then
  echo "This test must run inside WSL 2." >&2
  exit 1
fi
for command_name in ffmpeg mpv python3; do
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
FIRST_LOG="$TEST_ROOT/first-launch.log"
SECOND_LOG="$TEST_ROOT/second-launch.log"

cleanup() {
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
  -t 12 -shortest -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac \
  "$MEDIA_FILE"

mapfile -d '' -t PLAYER_COMMAND < <(
  python3 - "$REPO_DIR/src" "$RESUME_ROOT" "$MEDIA_FILE" <<'PY'
import os
import sys

sys.path.insert(0, sys.argv[1])
from media_library import media_player_command
from media_resume import prepare_profile_resume_directory

resume_directory = prepare_profile_resume_directory(sys.argv[2], "default")
command = media_player_command("mpv", [sys.argv[3]], resume_directory)
for argument in command:
    os.write(1, os.fsencode(argument) + b"\0")
PY
)

PLAYER_COMMAND=(
  "${PLAYER_COMMAND[@]:0:${#PLAYER_COMMAND[@]}-1}"
  --no-config
  --vo=null
  --ao=null
  --terminal=yes
  "${PLAYER_COMMAND[-1]}"
)

"${PLAYER_COMMAND[@]}" > "$FIRST_LOG" 2>&1 &
PLAYER_PID=$!
sleep 2
kill -TERM "$PLAYER_PID"
wait "$PLAYER_PID" || true

mapfile -t RESUME_FILES < <(find "$RESUME_ROOT/default" -maxdepth 1 -type f -print)
[[ "${#RESUME_FILES[@]}" -ge 1 ]]
mapfile -t POSITION_FILES < <(
  grep -l -E '^start=[1-9][0-9]*(\.[0-9]+)?$' "${RESUME_FILES[@]}"
)
[[ "${#POSITION_FILES[@]}" -eq 1 ]]
for resume_file in "${RESUME_FILES[@]}"; do
  grep -Eq '^(start=[1-9][0-9]*(\.[0-9]+)?|# redirect entry)$' "$resume_file"
  [[ "$(wc -l < "$resume_file")" -eq 1 ]]
done

"${PLAYER_COMMAND[@]}" > "$SECOND_LOG" 2>&1 &
PLAYER_PID=$!
sleep 1
kill -TERM "$PLAYER_PID"
wait "$PLAYER_PID" || true
grep -Eq 'Resuming playback|Starting playback at 00:0[1-9]' "$SECOND_LOG"

echo "MPV per-profile resume smoke test passed."
