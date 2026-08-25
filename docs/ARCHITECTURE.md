# Architecture

## Design principle

Do not replace the desktop session.

Instead:

- keep a normal Linux desktop as the base
- start a fullscreen kids launcher on top
- allow easy exit back to desktop

This avoids fragile desktop-environment hacks and makes the setup easier to maintain.

## Components

### 1. Fullscreen browser UI

A local HTML/CSS/JS app renders:

- title
- tile grid
- paging
- parent settings
- shutdown / exit controls

### 2. Local HTTP server

A tiny Python HTTP server:

- serves the frontend
- loads and saves config JSON
- validates imported and edited configuration before an atomic write
- lists installed applications
- resolves legacy media, website, and application commands into one launch path
- launches configured programs with a shared overlay lifecycle
- handles shutdown and exit actions

### 3. Launch adapters

Every tile is posted to `/launch/<tile-id>`. The server normalizes the existing command formats into one of three actions:

- **media** — opens every populated media directory as a VLC or MPV playlist, with a desktop opener as fallback
- **web** — redirects compatible embedded sites to the wrapper or starts the selected browser in a dedicated external profile
- **app** — starts an argument vector directly without a shell

Existing `special:` commands and older `xdg-open URL` browser tiles remain compatible. Recommended public media sites use external mode because framing policies, login flows, and DRM make third-party iframe behavior unreliable.

### 4. Parent security boundary

- the public config API exposes only whether a PIN exists, never its hash
- successful PIN verification creates a short-lived HTTP-only session
- configuration, timer administration, updates, exit, and shutdown require that session when a PIN is configured
- new PINs use salted PBKDF2-SHA256 hashes; legacy hashes are upgraded after login
- cross-site browser requests are rejected by the localhost server

### 5. Update and release boundary

- the browser asks the local server for update status; it does not contact a mutable repository file directly
- the installed updater prefers a complete stable GitHub Release and verifies its archive against `SHA256SUMS`
- installations that have successfully consumed a release remember that channel and fail closed when release discovery is unavailable
- the legacy `main/VERSION` source remains available before that migration so existing v0.3.x updaters keep working
- `main` is kept identical to the latest published release; development occurs on other branches and a release is published before its tagged commit is fast-forwarded to `main`
- the server only writes an update trigger; `launcher.sh` stops the UI and executes that trigger exactly once

### 6. Desktop integration

- autostart launches kids mode after login
- desktop shortcut reopens kids mode
- shutdown listener allows safe local poweroff

## Why not do everything in Plasma directly?

Because desktop-shell configuration becomes brittle fast:

- folder views cache strangely
- screen mappings drift
- widget layouts are fragile
- switching modes by rewriting Plasma config is unreliable

The browser-overlay approach is much more robust.
