# Install Guide

## The Easy Way (One Line)

Open a terminal and paste this one line. That's it.

```bash
curl -fsSL https://raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main/scripts/install.sh | bash
```

It downloads the launcher, installs it for your user, and sets everything up automatically.

## What You Need First

- A Linux computer (Ubuntu, Linux Mint, or similar)
- Firefox or Chromium browser installed (usually already there)
- Python 3 (usually already there)
- `flock` from `util-linux` (preinstalled on Ubuntu, Linux Mint, and Zorin OS)
- Internet connection for the download

## What Happens After Installing

1. **Log out and log back in** — the kids launcher opens automatically
2. **Your child taps an app tile** to open apps
3. **You tap "Parent"** to customize tiles, add apps, change colors
4. **A shortcut appears on your desktop** to reopen kids mode anytime

That's it. No complex configuration needed.

## Manual Install (If You Prefer)

If you already downloaded the repository:

```bash
bash scripts/install.sh --user $(id -un)
```

Or with specific options:

```bash
bash scripts/install.sh \
  --user $(id -un) \
  --lang auto \
  --theme rosa \
  --layout gross
```

## Common Options

| Option | What it does |
|--------|-------------|
| `--user <name>` | Install for this user (default: current user) |
| `--lang auto` | Detect language automatically (default) |
| `--lang de` | German |
| `--lang en` | English |
| `--theme rosa` | Pink theme (default) |
| `--theme lila` | Purple |
| `--theme blau` | Blue |
| `--theme gruen` | Green |
| `--theme regenbogen` | Rainbow |
| `--layout gross` | Big tiles: 4 per page (default) |
| `--layout klein` | Small tiles: 9 per page |
| `--launch-mode window` | Normal window (default, most reliable) |
| `--launch-mode fullscreen` | Fullscreen |
| `--launch-mode kiosk` | Strict kiosk mode |
| `--install-shutdown-helper` | Allow child to shut down the computer |
| `--force` | Re-install even if already installed |

Ubuntu's confined Firefox snap stores the launcher's dedicated browser profile
under `~/snap/firefox/common`. Native Firefox packages continue to use the
launcher cache under `~/.cache`; existing browser profiles are not reused.
The dedicated profile opts out of Firefox's remote survey messages so that
browser prompts cannot cover the child-facing launcher.

## How to Remove

The installer creates an uninstall note at:

```
~/.local/share/cozy-kids-launcher/uninstall.txt
```

Open that file and delete the listed paths to fully remove the launcher.

Backups of overwritten files are also kept at:

```
~/.local/share/cozy-kids-launcher-backups/<timestamp>/
```

Valid configuration backups appear under **Parent → Backups**. Restoring one
replaces launcher settings only; it does not downgrade the installed program.
The current Parent PIN stays active, and the launcher creates a new safety
snapshot immediately before the restore.

## How to Update

Run the update script that was installed with the launcher:

```bash
bash ~/.local/share/cozy-kids-launcher/update.sh
```

Or check for updates without installing:

```bash
bash ~/.local/share/cozy-kids-launcher/update.sh --check-only
```

The updater prefers a versioned GitHub Release and verifies its SHA-256 checksum before installing it. If this installation predates the first compatible release, it automatically retains the original `main/VERSION` update path. After a verified release has been installed, it will not silently fall back to mutable `main` if GitHub's release endpoint is unavailable.

For an explicit emergency fallback, run:

```bash
bash ~/.local/share/cozy-kids-launcher/update.sh --legacy-main
```

This does not allow downgrades. You can also re-run the original one-line installer; existing v0.3.x installations remain compatible with that path.

## Troubleshooting

**"No supported browser found"**

Install Firefox or Chromium first:

```bash
sudo apt-get install firefox
```

**Kids launcher does not start after login**

Make sure the autostart file exists:

```bash
ls ~/.config/autostart/cozy-kids-launcher-autostart.desktop
```

If missing, re-run the installer.

**Launcher shows a black screen**

Your desktop environment may not support kiosk mode well. Try installing with `--launch-mode window` or `--launch-mode fullscreen`.

**Forgot the parent PIN**

Delete the PIN from the config file:

```bash
python3 -c "import json; d=json.load(open('$HOME/.config/cozy-kids-launcher/config.json')); d['pinHash']=''; json.dump(d, open('$HOME/.config/cozy-kids-launcher/config.json','w'), indent=2)"
```

Then re-open the launcher.

## What Gets Installed Where

| File | Purpose |
|------|---------|
| `~/.local/bin/cozy-kids-launcher` | The command that starts kids mode |
| `~/.local/share/cozy-kids-launcher/` | App files: server, UI, version, updater |
| `~/.local/state/cozy-kids-launcher/runtime.jsonl` | Small rotating technical event log |
| `~/.cache/cozy-kids-launcher/lifecycle.json` | Private current launcher lifecycle state |
| `~/.config/cozy-kids-launcher/config.json` | Your tiles, colors, labels, PIN |
| `~/.local/share/cozy-kids-launcher-backups/` | Private local configuration and installer backups |
| `~/.config/autostart/...` | Auto-starts on login |
| `~/Desktop/Kinder-Modus.desktop` | Desktop shortcut to reopen |

Everything stays on your computer. Nothing is sent to the internet.
