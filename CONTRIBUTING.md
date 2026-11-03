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
python3 scripts/check.py
```

This runs the same static, unit/integration, and Chromium checks used by CI.
Browser tests need a Chromium-family browser and `websocket-client`; see
[Development](docs/DEVELOPMENT.md) for prerequisites and focused test commands.
No real family profile or system package installation is changed by these tests.

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

## Maintain a change

- For translations, follow the [language-pack workflow](docs/LOCALIZATION.md).
  Test long strings and keyboard focus on the supported compact layout, and
  ask a fluent speaker to review new or substantially changed translations.
- For accessibility, describe the input methods and settings you exercised.
  Use the [desktop checklist](docs/DESKTOP_TESTING.md) to separate automated
  focus tests from physical and screen-reader observations.
- For a suspected vulnerability, use GitHub's private vulnerability reporting
  option when available. Otherwise contact a maintainer privately before
  sharing reproduction details. Remove PINs, paths and family data from reports.
- For downstream packaging, document the distribution and package versions,
  update owner, and migration and rollback evidence. Apply the
  [compatibility policy](docs/COMPATIBILITY.md) and
  [package-provider boundaries](docs/PACKAGE_PROVIDERS.md).

By contributing, you agree that your work is provided under the repository's [MIT License](LICENSE).
