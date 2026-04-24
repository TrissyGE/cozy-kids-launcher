# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - Major Improvements

### Installer Refactoring

- **Split monolithic `install.sh` into separate source files under `src/`**
  - `src/server.py` — Python HTTP server template
  - `src/index.html` — Kids UI template
  - `src/no-media.html` — "No media found" page template
  - `src/launcher.sh` — Runtime launcher script template
- Installer now renders templates via Python instead of embedding massive bash heredocs
- Much easier to maintain and review individual components

### Server Hardening (`src/server.py`)

- Switched from single-threaded `socketserver.TCPServer` to `http.server.ThreadingHTTPServer`
  - Prevents UI freeze when scanning desktop applications
- Fixed file handle leak in `scan_apps()` (now uses `with open(...)`)
- Added proper `.desktop` file parsing
  - Handles `TryExec=` validation
  - Strips `%U`, `%F`, and other field codes from `Exec=` lines
- Hardened `/launch/` endpoint
  - Validates tile IDs with `^[A-Za-z0-9_-]+$` regex
  - Avoids `shell=True` for simple single-word commands
- Replaced fragile `pkill`-based exit with stored browser PID
  - Launcher writes browser PID to `~/.cache/.../browser.pid`
  - Server reads and signals the exact PID for clean shutdown
- Added `/api/verify-pin` endpoint for parent settings authentication

### PIN Protection for Parent Settings

- Added optional PIN gate before entering admin/parent settings
- PIN is SHA-256 hashed (first 16 hex chars stored in `config.json`)
- Admin panel includes PIN set/change/remove inputs
- Config includes `"pinHash": ""` by default (no PIN required initially)
- New translations added for PIN-related UI text

### Improved Tile Reordering UX

- Added **"move down"** button alongside existing "move up"
- Added **admin page navigation** (prev/next buttons with page counter)
  - Tile forms are paginated in admin view, matching kids view
  - No longer limited to editing tiles on the current page only
- Tile form grid expanded to accommodate new buttons

### Installer Fixes

- Fixed `chown` to only touch files the installer actually creates
  - Previous version recursively chowned entire system directories (e.g., `autostart`)
- Generated `config.json` properly escaped via Python `json.dump()`
- Added 12 new translations for PIN and reordering features
- No unreplaced template placeholders in generated files

### New Repository Structure

```
cozy-kids-launcher/
  README.md
  LICENSE
  VERSION
  CHANGELOG.md
  docs/
    ARCHITECTURE.md
    INSTALL.md
    PRIVACY.md
    ROADMAP.md
    SCREENSHOTS.md
  examples/
    config.example.json
  scripts/
    install.sh
    install-one-liner.sh
    update.sh
    deploy.sh
  src/
    server.py
    index.html
    no-media.html
    launcher.sh
```

## [Unreleased] - Automated Updates & Easy Install

### One-Line Installer

- Added `scripts/install-one-liner.sh` — download, extract, and install with a single `curl | bash` command
- No need to clone the repository manually
- README updated to feature the one-liner prominently

### Update Mechanism

- Added `VERSION` file for semver tracking
- Added `scripts/update.sh` — standalone updater
  - Compares installed version with latest on GitHub
  - Downloads and re-runs installer while preserving user config
  - `--check-only` to check without installing
  - `--force` to reinstall even if versions match
- Server: `/api/version` endpoint for local version discovery
- Admin panel: version display + "Check for updates" button

### Simplified Documentation

- Completely rewrote `docs/INSTALL.md` for non-technical parents
  - One-liner command front and center
  - Plain-language prerequisites
  - Step-by-step "what happens after installing"
  - Troubleshooting section with common issues
  - Table of common options in simple terms
  - Update instructions
  - PIN reset instructions

## [Original] - Initial Release

- First working version extracted from a private family laptop setup
- Fullscreen kids launcher via kiosk browser
- Local Python HTTP server
- JSON-based configuration
- Desktop integration (autostart + shortcut)
- Parent settings with editable tiles, themes, and layout modes
