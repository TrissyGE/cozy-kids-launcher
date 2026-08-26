# Development

Cozy Kids Launcher intentionally uses the Python standard library and plain HTML, CSS, and JavaScript. A development checkout therefore has no package-install step.

## Run the automated checks

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile src/server.py src/config_store.py src/overlay.py src/timer_watchdog.py scripts/take-screenshots.py
bash -n scripts/install.sh scripts/update.sh scripts/deploy.sh scripts/wsl/setup-test-env.sh scripts/wsl/run-gui-smoke.sh src/launcher.sh
python3 -m py_compile scripts/wsl/capture-page.py scripts/wsl/probe-web-targets.py
python3 -m json.tool examples/config.example.json >/dev/null
python3 -m json.tool src/recommendations.json >/dev/null
```

The test suite renders the server template with test values, starts it on an ephemeral localhost port, and exercises the HTTP API against temporary config and cache directories. On Linux it also serves synthetic release and legacy archives from an ephemeral local HTTP server to test successful verification, checksum rejection, compatibility fallback, and fail-closed behavior. It does not touch an installed launcher.

GitHub Actions runs the same checks on every pull request and on pushes to `main` and `develop` with the oldest and newest supported Python versions.

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
