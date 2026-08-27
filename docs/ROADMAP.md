# Roadmap

Cozy Kids Launcher is growing into a lightweight, local-first family console for Linux: playful and simple for children, understandable and dependable for parents.

The roadmap is intentionally release-oriented. Stability work comes before the product features that depend on it, and every release must preserve legacy configurations and the stable-`main` updater contract.

## v0.4.1 — Project polish

- [x] Rebuild the GitHub landing page around current screenshots and concise navigation
- [x] Add deterministic screenshots generated from an isolated demo profile
- [x] Document the `main`, `develop`, topic, release, and hotfix branch lifecycle
- [x] Add contribution guidance and a pull-request template
- [x] Make the one-line installer work without a separate `unzip` command
- [x] Localize theme and browser-setting labels consistently
- [x] Repair the website-tile editor layout

## v0.5.0 — Solid Core

### Maintainability

- [ ] Split the frontend into focused style and JavaScript modules without adding a production build dependency
- [ ] Split server responsibilities into configuration, authentication, discovery, launching, media, timer, and update modules
- [x] Add a versioned configuration schema with tested, automatic migrations
- [x] Add structured runtime logging with safe rotation
- [x] Add a privacy-safe diagnostics export that excludes PINs and personal configuration values

### Runtime stability

- [x] Enforce a single launcher instance and make process ownership explicit
- [x] Detect server and launcher failures and recover without leaving a blank kiosk window
- [x] Track launched child processes reliably and close only the process tree owned by its tile
- [x] Make backup discovery and restoration available from Parent settings
- [x] Define and test clean startup, logout, shutdown, update, and crash-recovery states

### Test confidence

- [ ] Add browser end-to-end coverage for home, PIN, settings, timer, themes, and update states
- [ ] Complete release smoke tests on GNOME, KDE Plasma, and XFCE
- [ ] Document and test X11 and Wayland behavior for focus, overlays, and kiosk browsers
- [ ] Exercise touch, keyboard-only, reduced-motion, high-contrast, and low-resolution flows

### Design foundation

- [ ] Introduce shared design tokens and reusable controls
- [ ] Redesign Parent settings as Overview, Children, Apps & Media, Screen Time, Appearance, and System sections
- [ ] Add a live preview, search, filtering, bulk actions, consistent dialogs, and clear empty/error/loading states
- [ ] Create a coherent local icon system while keeping custom emoji tiles available

## v0.6.0 — Family Edition

- [ ] Add multiple child profiles with separate avatars, themes, tiles, favorites, and limits
- [ ] Add a guided first-run setup for language, child, apps, time rules, and appearance
- [ ] Add weekly screen-time schedules and per-app availability rules
- [ ] Add a local, optional parent dashboard for recent activity and usage duration
- [ ] Add a browser allowlist with understandable navigation boundaries
- [ ] Keep all profile and activity data local, exportable, and removable

## v0.7.0 — Delight

- [ ] Add a cover-based local media library with favorites, recents, and resume support
- [ ] Add animated world themes and optional time-of-day variants
- [ ] Add subtle navigation, launch, success, and return transitions
- [ ] Add optional local sounds and Linux text-to-speech feedback
- [ ] Add accessibility presets for larger text, contrast, reduced motion, and keyboard-only operation
- [ ] Add optional, non-manipulative celebration moments without engagement scoring

## v0.8.0 — Platform

- [ ] Produce a first-party Debian package for Ubuntu, Linux Mint, and Zorin OS
- [ ] Evaluate additional packaging only where host-app launching and desktop integration remain reliable
- [ ] Add a supported user-service lifecycle with useful status and recovery commands
- [ ] Add stable and opt-in preview update channels without weakening immutable releases
- [ ] Expand the automated and manual compatibility matrix across supported distributions

## Release standard

A roadmap checkbox is not complete until:

- automated tests or an explicit manual test cover it;
- German and English behavior remain aligned;
- old configurations migrate safely;
- diagnostics do not expose private family data;
- relevant documentation and screenshots are updated;
- the release passes the full gate in [RELEASING.md](RELEASING.md).
