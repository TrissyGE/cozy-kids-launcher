# Changelog

All notable changes to this project will be documented in this file.

## [0.3.0] - Screen Time Timer

### Screen Time Timer

- **Timer is OFF by default** — parents must explicitly start it from the admin panel
- **Preset durations**: 15, 30, 60 minutes, or custom value (1–180 minutes)
- **Visual warning**: 5 minutes before time runs out, a friendly overlay appears
- **Fullscreen block screen**: when time is up, a styled overlay blocks all interaction
  - Works across the launcher, embedded browser, external browser, and native apps/games
  - PIN-protected extension (15/30/60/custom minutes)
  - "Exit" button to close kids mode immediately
- **System watchdog** (`timer_watchdog.py`): a separate Tkinter process that polls the server
  - Covers native apps and games that the browser overlay cannot reach
  - Always-on-top fullscreen window when timer expires
  - Styled to match the launcher theme (rounded cards, emoji, theme colours)
- **Browser timer UI**: both `index.html` and `browser.html` show a live countdown badge
  - Warning and block overlays as fallback when the watchdog is not running
- **Admin panel**: new timer section with duration selector, custom input, start/stop button, and status display

### New Files

- `src/timer_watchdog.py` — system-level fullscreen timer block overlay

### UI Improvements

- **Visual start feedback**: clicking a tile now shows a friendly overlay with the app's emoji and "Starting..." text, so kids know something is happening while the app loads
- **Touch swipe navigation**: swipe left/right on touchscreens to change pages (navigation arrows remain for mouse users)
- **Bouncy tile animations**: tiles gently scale up and wiggle on hover/tap, making the UI feel alive and playful for children
- **Clock badge**: top-right corner shows the current time with a day-phase emoji (🌅 morning, ☀️ day, 🌇 evening, 🌙 night)
- **Battery badge**: top-left corner shows battery level and charging status when the browser supports the Battery API
- **"Last launched" highlight**: the most recently clicked tile gets a glowing border and a ⭐ star badge, making favorite apps easier to find
- **Improved empty state**: when no tiles are visible, a friendly message with a large emoji appears instead of a blank grid
- **Admin live preview**: a mini preview panel in the parent settings shows exactly how the kids screen currently looks

### Bug Fixes

- **Theme wallpapers not installed**: `scripts/install.sh` now copies the `themes/` directory (containing `.jpg` wallpaper files) to `~/.local/share/cozy-kids-launcher/themes/`. Previously, world themes that rely on background images appeared with blank backgrounds.

### Updated Files

- `src/server.py` — new API endpoints: `/api/timer/status`, `/api/timer/start`, `/api/timer/stop`, `/api/timer/extend`
- `src/index.html` — timer badge, warning/block overlays, admin timer controls
- `src/browser.html` — timer badge and overlays for embedded browser
- `src/launcher.sh` — starts the watchdog alongside the server
- `scripts/install.sh` — new translations, copies watchdog, timer config defaults

## [0.2.9] - Browser Apps, Streaming Support & Bug Fixes

### Bug Fixes

- **KDE Apps fullscreen fallback**: All KDE apps now use `kstart` (Plasma 6) instead of `kstart5` (Plasma 5) as the primary wrapper. `alt_cmds` contains only the bare app binary so the "installed" check verifies the actual app, not the wrapper.
- **KDE Apps on Plasma 6**: Wrapper detection in `load_recommendations()` now ignores `kstart`/`kstart5` when checking if an app is installed.
- **Shutdown button**: No longer requires `--install-shutdown-helper` flag. Auto-detects `systemctl` or `loginctl` and enables the button dynamically. Hidden on systems where shutdown is unavailable.
- **Security fix**: Removed `shell=True` from the `/launch/` endpoint to prevent command injection from user-editable configs.
- **PIN button label**: Admin panel now correctly shows "PIN ändern" instead of duplicating "PIN entfernen" when a PIN is already set.
- **Exit kids mode**: Server now shuts down itself after handling `/exit-kids`, and kills the browser PID. `launcher.sh` detects the browser death and exits its `while true` loop cleanly.
- **Deleted tiles reappearing**: Added `autoScanDone` flag to config. `autoScanRecommendations()` only runs once per installation. Existing configs are migrated with `autoScanDone: true` so they won't suddenly add new tiles.
- **GCompris fullscreen lost**: Installer `--recommended` logic now preserves command-line arguments (e.g. `--fullscreen`) when using an `alt_cmd`.
- **PBS Kids iframe blocked**: Moved to external-browser mode (like YouTube Kids) because PBSKids also sends X-Frame-Options.
- **External browser glitchy / no fullscreen**: Switched from `--fullscreen` to `--kiosk` for Chromium-based external browsers. `--kiosk` is more reliable for app-mode windows.

### New Browser Apps

- **PBS Kids** (embedded) — learning games and videos
- **ZDFtivi** (embedded) — German kids TV channel
- **KiKA** (embedded) — ARD/ZDF kids channel

### Streaming Pseudo-Apps (External Browser)

- **YouTube Kids** — runs as external Chromium app-mode with overlay home button (Firefox blocks YouTube in iframes due to X-Frame-Options)
- **Netflix Kids** — launches Chromium in app-fullscreen mode with a floating overlay home button
- **Disney+** — same external-browser overlay approach
- **Prime Kids** (Amazon Prime Video kids section) — same approach
- DRM-protected sites cannot be embedded in iframes, so they launch in a separate Chromium window
- A small always-on-top Tkinter overlay shows a home button to return to the launcher

### Embedded Browser (`src/browser.html`)

- Fullscreen iframe for kid-friendly websites
- Large floating home button (🏠) top-left, always visible
- URL validation (only `http://` and `https://` allowed)
- Sandboxed iframe without `allow-popups` to prevent unwanted new windows

### External Browser Overlay (`src/overlay.py`)

- Small always-on-top window with a home button
- Tracks the external browser PID and kills it cleanly on click (SIGTERM → wait → SIGKILL)
- Auto-closes if the browser process dies on its own
- Uses `wmctrl` / `xdotool` to bring the launcher back to the foreground

### Admin Panel Improvements

- New "🌐 Browser-Seite" option in the app dropdown
- When selected, shows a URL input field and a type selector (embedded / external)
- Parents can now add any website as a launcher tile

### New Files

- `src/browser.html` — embedded iframe browser
- `src/overlay.py` — external browser overlay utility

## [0.2.8] - Theme Editor & Visual Theme Chooser

### 9 New World Themes

- **Wald** — green forest background with tree-themed tiles
- **Weltraum** — purple cosmic background with futuristic tiles
- **Ocean** — blue underwater background with wave-shaped tiles
- **Dinosaurier** — prehistoric jungle with dotted green tiles
- **Baustelle** — sunny construction site with dashed orange tiles
- **Prinzessin** — magical pink kingdom with glowing tiles
- **Bauernhof** — red farm scene with bordered tiles
- **Katzen** — cozy cat interior with warm rounded tiles
- **Hunde** — dog park meadow with soft rounded tiles

### Visual Theme Chooser

- Replaced plain theme dropdown with a **visual grid overlay**
- Shows color swatches for 5 color themes (Rosa, Lila, Blau, Grün, Regenbogen)
- Shows image thumbnails for 9 world themes
- Selected theme highlighted with colored border and slight scale-up
- Opens as a centered modal overlay to keep admin layout clean

### Theme System Architecture

- Themes now set **CSS custom properties** for buttons, inputs, shadows, and borders
- Each world theme gets a **real background image** loaded via `/themes/*.jpg`
- Background images fade in smoothly via a dedicated `#themeBg` layer
- Images stored in `~/.local/share/cozy-kids-launcher/themes/`
- Each theme has **unique tile styling** (borders, radius, shadows)

### Installer Updates

- Guided setup now lists all 14 themes with numbered options
- Theme validation accepts all 14 theme names

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

### Config Export/Import

- Added **Export** button in parent settings — downloads `cozy-kids-config.json`
- Added **Import** button — uploads and validates a config JSON file
- Server endpoints: `GET /api/export-config` and `POST /api/import-config`
- Import validates that the file contains a `tiles` array before saving
- All strings fully translated (German + English)
- Patched both source templates and installed runtime files for immediate testing

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
