# Development

Cozy Kids Launcher intentionally uses the Python standard library and plain HTML, CSS, and JavaScript. A development checkout therefore has no package-install step.

## Run the automated checks

From the repository root:

```bash
python3 scripts/check.py
```

This non-publishing command is the shared entry point for development, CI, and
the automated part of the release gate. It stops on failure. Python templates,
JSON, and **each** shell script under `src`, `scripts`, `tests`, and `examples`
are discovered automatically, followed by locale freshness, unit/integration,
and browser tests. JavaScript behavior is exercised in Chromium, not compiled
by the static Python check. Never pass multiple scripts to one `bash -n` call:
only the first is checked.

For targeted iteration (run the complete command before handing off a PR):

```bash
python3 scripts/check.py --only static
python3 scripts/check.py --only unit
python3 scripts/check.py --only browser
python3 scripts/wsl/browser-e2e.py --suite regressions --artifacts .test-artifacts/regressions
```

On Windows, run these inside WSL, for example
`wsl.exe --cd /mnt/c/path/to/cozy-kids-launcher python3 scripts/check.py`.
Do not start a full desktop VM for unit or headless-browser changes. Real
compositor, login, audio, DRM, and package-manager claims still require the
relevant disposable environment.

The test suite renders the server template with test values, starts it on an ephemeral localhost port, and exercises the HTTP API against temporary config and cache directories. On Linux it also serves synthetic release and legacy archives from an ephemeral local HTTP server to test successful verification, checksum rejection, compatibility fallback, and fail-closed behavior. The launcher lifecycle tests perform isolated installations and drive real startup, successful and failed update, shutdown, logout, server recovery, and exhausted-recovery flows while checking that every owned process is cleaned up. A separate process-supervisor test follows a forked child that ignores `SIGTERM` while proving an unrelated instance of the same executable remains alive. It does not touch an installed launcher.

`scripts/wsl/browser-e2e.py` creates another isolated installation and drives guided first run with live language switching, home, PIN, child-profile management and selection, the opt-in activity dashboard and privacy-minimized export, Parent settings, schedules, timer, theme, and update-state journeys through real Chromium. It also sends real keyboard and emulated touch input, applies reduced-motion and forced-colors preferences, and checks first run, home, and Parent settings at 800x600. It needs a supported Chromium-family browser plus the Python `websocket-client` package (`python3-websocket` in the WSL test environment). Diagnostics and screenshots are written below `.test-artifacts/browser-e2e/`.

GitHub Actions runs the API checks on every pull request and on pushes to `main` and `develop` with the oldest and newest supported Python versions. A separate Chromium job runs the browser journeys, and the release workflow repeats them before publishing.

The browser suite also covers custom-theme resets and accessibility precedence
in the launcher, Parent preview, and media library, plus rejected, offline,
malformed, pending, and acknowledged update/install requests. These mutations
use local fixtures: no real update or system package installation is started.
Bounded rendering assertions report individual observed values on failure;
retrying an entire failed journey is not a substitute for diagnosing it.

## Small, verifiable iterations

1. Inspect `git status`, current `develop`, open PRs, and the latest CI result.
   Do not infer the current implementation from an old chat or roadmap alone.
2. Work on one topic branch from `develop`; preserve unrelated local edits.
3. Reproduce the issue, add focused tests, then use the complete shared check.
4. Update the changelog and roadmap with the exact implemented scope and test
   evidence. A mocked provider plan is not a tested native installation.
5. Push and use `gh pr create --base develop`, then `gh pr checks` to inspect
   the actual PR checks. After an approved merge, inspect the new `develop`
   CI run too. A green older PR does not establish current branch health.

Merging and publishing are separate decisions. Keep `VERSION`, tags, and
`main` unchanged during ordinary development. See [ROADMAP.md](ROADMAP.md)
for the current execution order and [PACKAGE_PROVIDERS.md](PACKAGE_PROVIDERS.md)
for the first platform increment's limits.

## Branch model

`main` is consumed directly by already-installed v0.3.x updaters, so it must always equal the latest published release commit. Do not develop or merge ordinary pull requests there. Work on `develop` and short-lived topic branches; the tag-driven release workflow publishes a tested release first and only then fast-forwards the exact tagged commit to `main`.

The complete naming, pull-request, release-branch, and hotfix policy is in [BRANCHING.md](BRANCHING.md). The scheduled **Stable main invariant** workflow detects drift between `main` and the latest published release. See [RELEASING.md](RELEASING.md) before changing branch or repository rules.

## Refresh the public screenshots

On Linux or in WSL with a Chromium-family browser installed:

```bash
python3 scripts/take-screenshots.py
```

The script installs the current checkout into a temporary home, creates clean English demo profiles and content, and writes the public gallery images at 1440×900. It does not read or modify the current user's launcher profile. See [SCREENSHOTS.md](SCREENSHOTS.md).

## Release gate

`bash scripts/deploy.sh` runs the full local release-readiness gate, including an isolated installer smoke test. Pushing a `v<version>` tag runs the independent release workflow and publishes versioned, attested artifacts only after all gates pass. See [RELEASING.md](RELEASING.md) for the compatibility contract and release procedure.

## WSLg smoke test on Windows

Windows developers can exercise the real Linux browser, VLC, audio, GPU, and launcher routes through WSLg:

```bash
sudo bash scripts/wsl/setup-test-env.sh
bash scripts/wsl/run-gui-smoke.sh
```

See [WSL_TESTING.md](WSL_TESTING.md) for isolation details, artifacts, DRM limitations, and the full desktop test matrix.

## Full Linux desktop matrix

GNOME, KDE Plasma, and XFCE release evidence must come from complete disposable VM sessions. The reusable harness, required environments, manual observations, and JSON report contract are documented in [DESKTOP_TESTING.md](DESKTOP_TESTING.md). The different automated and manual guarantees for X11 and Wayland are documented in [DISPLAY_BEHAVIOR.md](DISPLAY_BEHAVIOR.md). WSLg results do not replace these compositor and login tests.

## Manual Linux smoke test

Use a disposable Linux user or virtual machine:

```bash
bash scripts/install.sh --skip-browser-check --launch-mode window
~/.local/bin/cozy-kids-launcher
```

Verify at least:

1. The kids screen loads and tiles launch.
2. A newly configured PIN is required after reopening Parent settings.
3. Settings, config export/import, timer controls, update, exit, and shutdown reject requests without an authenticated parent session when a PIN exists.
4. Legacy configurations still load and a legacy PIN is upgraded after the first successful login.
5. Labels containing characters such as `<`, `>`, `&`, quotes, and emoji render as text.

## Template source

Files in `src/` contain `{{PLACEHOLDER}}` values. `scripts/install.sh` renders them into the user's application directory. Make changes to the templates in this repository, not to generated files under `~/.local/share/cozy-kids-launcher/`.
