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

echo "[1/5] Unit and integration tests"
python3 -m unittest discover -s tests -v

echo "[2/5] Python, JSON, and shell validation"
python3 -m py_compile \
  src/server.py src/config_store.py src/runtime_diagnostics.py src/process_state.py src/process_supervisor.py src/overlay.py src/timer_watchdog.py \
  scripts/take-screenshots.py scripts/wsl/capture-page.py scripts/wsl/probe-web-targets.py
python3 -m json.tool examples/config.example.json >/dev/null
python3 -m json.tool src/recommendations.json >/dev/null
bash -n \
  scripts/install.sh scripts/update.sh scripts/deploy.sh \
  scripts/wsl/setup-test-env.sh scripts/wsl/run-gui-smoke.sh src/launcher.sh

echo "[3/5] Isolated installer smoke test"
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
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/config_store.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/runtime_diagnostics.py"
test -f "$TEST_HOME/.local/share/cozy-kids-launcher/process_state.py"
test -x "$TEST_HOME/.local/share/cozy-kids-launcher/process_supervisor.py"
cmp VERSION "$TEST_HOME/.local/share/cozy-kids-launcher/version"
python3 - "$TEST_HOME/.config/cozy-kids-launcher/config.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)
if config.get("configVersion") != 1:
    raise SystemExit("Installed config does not use schema version 1")
PY

echo "[4/5] Archive dry run"
PREFIX="cozy-kids-launcher-$VERSION/"
git archive --format=tar --prefix="$PREFIX" HEAD | gzip -n > "$TEST_HOME/release.tar.gz"
tar -tzf "$TEST_HOME/release.tar.gz" > "$TEST_HOME/archive-contents.txt"
grep -Fxq "${PREFIX}VERSION" "$TEST_HOME/archive-contents.txt"
grep -Fxq "${PREFIX}scripts/install.sh" "$TEST_HOME/archive-contents.txt"
sha256sum "$TEST_HOME/release.tar.gz" >/dev/null

echo "[5/5] Tag checks"
if git rev-parse -q --verify "refs/tags/v$VERSION" >/dev/null; then
  die "tag v$VERSION already exists"
fi

echo "Release v$VERSION is ready to tag."
echo "Push only the release tag; the hosted workflow publishes it before promoting the exact commit to main."
echo "See docs/RELEASING.md. This check does not create tags, push, or publish anything."
