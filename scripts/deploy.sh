#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_DIR"

die() {
  echo "Release check failed: $*" >&2
  exit 1
}

command -v git >/dev/null 2>&1 || die "git is required"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
python3 -c 'import websocket' >/dev/null 2>&1 \
  || die "Python package websocket-client is required for the browser release test"

CURRENT_BRANCH="$(git branch --show-current)"
[[ -n "$CURRENT_BRANCH" ]] || die "run the release check from a named release branch"
[[ "$CURRENT_BRANCH" != "main" ]] \
  || die "main is the stable legacy-updater channel; prepare releases on develop or a release branch"
if git show-ref --verify --quiet refs/remotes/origin/main; then
  git merge-base --is-ancestor refs/remotes/origin/main HEAD \
    || die "the release commit must descend from origin/main for a safe fast-forward promotion"
fi

VERSION="$(tr -d '\r\n' < VERSION)"
[[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || die "VERSION must use x.y.z semantic versioning"
grep -Eq "^## \[$VERSION\] - [0-9]{4}-[0-9]{2}-[0-9]{2}$" CHANGELOG.md \
  || die "CHANGELOG.md needs a dated section for $VERSION"

if [[ -n "$(git status --short)" ]]; then
  die "the working tree must be clean so checks match the commit that will be tagged"
fi

echo "[1/6] Unit and integration tests"
python3 -m unittest discover -s tests -v

echo "[2/6] Browser end-to-end test"
python3 scripts/wsl/browser-e2e.py

echo "[3/6] Python, JSON, and shell validation"
python3 -m py_compile \
  src/server.py src/app_detection.py src/application_launcher.py src/activity_store.py src/backup_store.py src/browser_policy.py src/config_store.py src/config_validation.py src/profile_config.py src/schedule_rules.py src/lifecycle_state.py src/media_library.py src/media_state.py src/media_resume.py src/media_session.py src/parent_auth.py src/runtime_diagnostics.py src/process_state.py src/process_supervisor.py src/overlay.py src/timer_state.py src/timer_watchdog.py src/update_manager.py \
  scripts/take-screenshots.py scripts/linux/desktop_smoke.py scripts/wsl/browser_driver.py scripts/wsl/browser-e2e.py scripts/wsl/capture-page.py scripts/wsl/probe-web-targets.py
python3 -m json.tool examples/config.example.json >/dev/null
python3 -m json.tool src/recommendations.json >/dev/null
bash -n \
  scripts/install.sh scripts/update.sh scripts/deploy.sh \
  scripts/wsl/setup-test-env.sh scripts/wsl/check-mpv-resume.sh \
  scripts/wsl/check-vlc-resume.sh \
  scripts/wsl/run-gui-smoke.sh src/launcher.sh

echo "[4/6] Isolated installer smoke test"
TEST_HOME="$(mktemp -d)"
trap 'rm -rf "$TEST_HOME"' EXIT
bash scripts/install.sh \
  --user "$(id -un)" \
  --home "$TEST_HOME" \
  --lang en \
  --launch-mode window \
  --skip-browser-check \
  --force >/dev/null
test -x "$TEST_HOME/.local/bin/cozy-kids-launcher"
test -x "$TEST_HOME/.local/share/cozy-kids-launcher/update.sh"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/app_detection.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/application_launcher.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/backup_store.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/browser_policy.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/config_store.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/config_validation.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/profile_config.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/lifecycle_state.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/media_library.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/media_state.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/media_resume.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/media_session.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/parent_auth.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/runtime_diagnostics.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/process_state.py"
test -x "$TEST_HOME/.local/share/cozy-kids-launcher/process_supervisor.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/timer_state.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/update_manager.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/frontend/icons.js"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/frontend/theme-runtime.js"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/media.html"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/frontend/media-library.css"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/frontend/media-library.js"
cmp VERSION "$TEST_HOME/.local/share/cozy-kids-launcher/version"
python3 - "$TEST_HOME/.config/cozy-kids-launcher/config.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
if config.get("configVersion") != 2:
    raise SystemExit("Installed config does not use schema version 2")
if config.get("activeProfileId") != "default" or len(config.get("profiles", [])) != 1:
    raise SystemExit("Installed config does not contain its default profile")
PY

echo "[5/6] Archive dry run"
PREFIX="cozy-kids-launcher-$VERSION/"
git archive --format=tar --prefix="$PREFIX" HEAD | gzip -n > "$TEST_HOME/release.tar.gz"
tar -tzf "$TEST_HOME/release.tar.gz" > "$TEST_HOME/archive-contents.txt"
grep -Fxq "${PREFIX}VERSION" "$TEST_HOME/archive-contents.txt"
grep -Fxq "${PREFIX}scripts/install.sh" "$TEST_HOME/archive-contents.txt"
sha256sum "$TEST_HOME/release.tar.gz" >/dev/null

echo "[6/6] Tag checks"
if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
  die "tag v$VERSION already exists"
fi

echo "Release v$VERSION is ready to tag."
echo "Push only the release tag; the hosted workflow publishes it before promoting the exact commit to main."
echo "See docs/RELEASING.md. This check does not create tags, push, or publish anything."
