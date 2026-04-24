# Install Guide

## Status

The repository now includes a first real installer at `scripts/install.sh`.

It is meant to turn the current proven setup into a reusable user-level install flow, while still keeping the project local-first and understandable.

Current scope:

- installs into one Linux user account
- writes a ready-to-run local launcher setup
- creates autostart and desktop shortcut entries
- auto-detects the system language for installer defaults
- supports manual language override with `--lang`
- keeps shutdown integration optional
- supports configurable browser launch mode

## Target platform

Currently intended for:

- Ubuntu-based Linux
- KDE Plasma desktop session
- local user autostart
- Firefox or Chromium-style kiosk browser
- systemd-based systems

## Quick start

Run from the repository root:

```bash
bash scripts/install.sh --user your-child-user
```

Useful options:

```bash
bash scripts/install.sh \
  --user your-child-user \
  --lang auto \
  --browser auto \
  --theme rosa \
  --layout gross \
  --launch-mode window
```

## Language handling

The installer now supports:

- `--lang auto` to detect system language from `LANG` / locale
- `--lang de`
- `--lang en`

The detected or chosen language is used for:

- default launcher title
- parent button label
- exit button label
- shutdown button label
- desktop shortcut naming
- autostart entry naming
- fallback no-media screen

This is intentionally simple because the amount of fixed UI text is small.

The generated launcher UI now also uses the selected language for:

- parent settings title
- admin placeholders and action buttons
- layout labels
- tile editor labels
- default starter tile names
- default kid-safe browser shortcut target

## What the installer creates

User-level paths:

- `~/.local/bin/cozy-kids-launcher`
- `~/.local/share/cozy-kids-launcher/`
- `~/.config/cozy-kids-launcher/config.json`
- `~/.config/autostart/cozy-kids-launcher-autostart.desktop`
- `~/Desktop/Cozy Kids Launcher.desktop` or `~/Schreibtisch/Kinder-Modus.desktop` depending on system layout
- `~/.local/share/applications/cozy-kids-launcher.desktop`

Inside the app directory, the installer writes:

- local Python server
- launcher UI
- no-media fallback page
- uninstall note

## Runtime model

A working install uses these building blocks:

1. local config JSON
2. local Python launcher server on localhost
3. fullscreen browser window in kiosk mode
4. user autostart entry
5. desktop shortcut to reopen kids mode
6. optional local shutdown action

## Supported installer options

- `--user <name>` install target user
- `--home <path>` override resolved home directory
- `--lang <auto|de|en>` language selection
- `--browser <auto|firefox|chromium|chromium-browser|google-chrome>`
- `--title <text>` custom default title
- `--theme <rosa|lila|blau|gruen|regenbogen>`
- `--layout <gross|klein>`
- `--launch-mode <window|fullscreen|kiosk>`
- `--parent-label <text>`
- `--exit-label <text>`
- `--install-shutdown-helper`
- `--force`

## Browser handling

The launcher start mode is now configurable:

- `window` default, most robust
- `fullscreen` good compromise when supported cleanly
- `kiosk` strict mode, but may behave differently depending on desktop environment, VM, graphics stack, or Firefox build

This changed because kiosk mode can render a black screen in some otherwise valid environments even when the launcher itself works.

When `--browser auto` is used, the installer currently checks in this order:

1. Firefox
2. Chromium
3. chromium-browser
4. Google Chrome

If none are found, installation aborts with a clear error.

## Shutdown behavior

Shutdown is optional.

By default, the UI still includes the shutdown button label, but the backend only performs a shutdown when the install was created with:

```bash
--install-shutdown-helper
```

This keeps the default install safer while preserving the feature path.

## Backups and rollback

Before overwriting generated files, the installer creates backups under:

- `~/.local/share/cozy-kids-launcher-backups/<timestamp>/`

It also writes uninstall notes to:

- `~/.local/share/cozy-kids-launcher/uninstall.txt`

## Current limitations

This is a strong first universal installer pass, but not the final packaging endpoint yet.

Still to improve:

- proper per-language tile defaults beyond the base UI labels
- optional protected parent settings PIN
- broader desktop-environment testing beyond Plasma
- distro-specific shutdown packaging polish
- richer browser command templating for edge cases

## Recommendation

Right now this installer is best suited for:

- technically comfortable parents
- tinkerers
- Linux users happy to test and refine a near-release setup
