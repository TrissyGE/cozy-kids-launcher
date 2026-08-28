# Contributing

Thanks for helping make Cozy Kids Launcher friendlier and more reliable for families.

## Before you start

Read the [branching guide](docs/BRANCHING.md). In short: branch from `develop`, open ordinary pull requests against `develop`, and do not use `main` for development. `main` is the stable channel used by legacy updaters.

```bash
git switch develop
git pull --ff-only
git switch -c feature/short-description
```

The project has no application dependency-install step. Development requires Python 3 and a POSIX shell; graphical smoke tests additionally require Linux or WSLg.

## Run the checks

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile src/server.py src/app_detection.py src/config_store.py src/config_validation.py src/media_library.py src/parent_auth.py src/runtime_diagnostics.py src/process_state.py src/overlay.py src/timer_state.py src/timer_watchdog.py src/update_manager.py scripts/take-screenshots.py
bash -n scripts/install.sh scripts/update.sh scripts/deploy.sh src/launcher.sh
python3 -m json.tool examples/config.example.json >/dev/null
python3 -m json.tool src/recommendations.json >/dev/null
```

For launcher, browser, audio, or video changes, also use the [WSLg smoke-test environment](docs/WSL_TESTING.md) or a disposable Linux profile.

## Visible changes

Keep the German and English interfaces aligned. If a change affects the primary UI, regenerate the public screenshots from a clean demo profile:

```bash
python3 scripts/take-screenshots.py
```

The script supports Linux and WSL and does not alter the current user's launcher installation. See [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md) for details.

## Pull-request checklist

- The change is focused and the motivation is documented.
- Automated tests cover new behavior or the pull request explains the manual test.
- Legacy configuration files still load.
- User-controlled values remain treated as data, not HTML or shell code.
- English and German labels remain consistent.
- Relevant documentation and screenshots are updated.
- Updater changes preserve the compatibility rules in [docs/RELEASING.md](docs/RELEASING.md).

By contributing, you agree that your work is provided under the repository's [MIT License](LICENSE).
