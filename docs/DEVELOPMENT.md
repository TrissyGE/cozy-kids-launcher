# Development

Cozy Kids Launcher intentionally uses the Python standard library and plain HTML, CSS, and JavaScript. A development checkout therefore has no package-install step.

## Run the automated checks

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 scripts/wsl/browser-e2e.py
python3 -m py_compile src/server.py src/app_detection.py src/application_launcher.py src/backup_store.py src/config_store.py src/config_validation.py src/profile_config.py src/lifecycle_state.py src/media_library.py src/parent_auth.py src/process_state.py src/process_supervisor.py src/runtime_diagnostics.py src/overlay.py src/timer_state.py src/timer_watchdog.py src/update_manager.py scripts/generate-locales.py scripts/take-screenshots.py scripts/linux/desktop_smoke.py scripts/wsl/browser_driver.py scripts/wsl/browser-e2e.py
bash -n scripts/install.sh scripts/update.sh scripts/deploy.sh scripts/wsl/setup-test-env.sh scripts/wsl/run-gui-smoke.sh src/launcher.sh
python3 -m py_compile scripts/wsl/capture-page.py scripts/wsl/probe-web-targets.py
python3 -m json.tool examples/config.example.json >/dev/null
python3 -m json.tool src/recommendations.json >/dev/null
python3 -m json.tool src/frontend/locales/de.json >/dev/null
python3 -m json.tool src/frontend/locales/en.json >/dev/null
python3 scripts/generate-locales.py --check
```

The test suite renders the server template with test values, starts it on an ephemeral localhost port, and exercises the HTTP API against temporary config and cache directories. On Linux it also serves synthetic release and legacy archives from an ephemeral local HTTP server to test successful verification, checksum rejection, compatibility fallback, and fail-closed behavior. The launcher lifecycle tests perform isolated installations and drive real startup, successful and failed update, shutdown, logout, server recovery, and exhausted-recovery flows while checking that every owned process is cleaned up. A separate process-supervisor test follows a forked child that ignores `SIGTERM` while proving an unrelated instance of the same executable remains alive. It does not touch an installed launcher.

`scripts/wsl/browser-e2e.py` creates another isolated installation and drives guided first run with live language switching, home, PIN, child-profile management and selection, Parent settings, timer, theme, and update-state journeys through real Chromium. It also sends real keyboard and emulated touch input, applies reduced-motion and forced-colors preferences, and checks first run, home, and Parent settings at 800x600. It needs a supported Chromium-family browser plus the Python `websocket-client` package (`python3-websocket` in the WSL test environment). Diagnostics and screenshots are written below `.test-artifacts/browser-e2e/`.

GitHub Actions runs the API checks on every pull request and on pushes to `main` and `develop` with the oldest and newest supported Python versions. A separate Chromium job runs the browser journeys, and the release workflow repeats them before publishing.

## Branch model

`main` is consumed directly by already-installed v0.3.x updaters, so it must always equal the latest published release commit. Do not develop or merge ordinary pull requests there. Work on `develop` and short-lived topic branches; the tag-driven release workflow publishes a tested release first and only then fast-forwards the exact tagged commit to `main`.

The complete naming, pull-request, release-branch, and hotfix policy is in [BRANCHING.md](BRANCHING.md). The scheduled **Stable main invariant** workflow detects drift between `main` and the latest published release. See [RELEASING.md](RELEASING.md) before changing branch or repository rules.

## Refresh the public screenshots

On Linux or in WSL with a Chromium-family browser installed:

```bash
python3 scripts/take-screenshots.py
```

The script installs the current checkout into a temporary home, creates a clean English demo configuration, and writes the four README images at 1440×900. It does not read or modify the current user's launcher profile. See [SCREENSHOTS.md](SCREENSHOTS.md).

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
