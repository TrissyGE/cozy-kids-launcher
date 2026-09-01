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

- [x] Split the frontend into focused style and JavaScript modules without adding a production build dependency
- [x] Split server responsibilities into configuration, authentication, discovery, launching, media, timer, and update modules
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

- [x] Add browser end-to-end coverage for home, PIN, settings, timer, themes, and update states
- [x] Complete release smoke tests on GNOME, KDE Plasma, and XFCE
  - [x] Add a repeatable in-session harness with machine-readable reports
  - [x] Record passing GNOME Wayland, KDE Plasma Wayland, and XFCE X11 VM reports
- [x] Document and test X11 and Wayland behavior for focus, overlays, and kiosk browsers
- [x] Exercise touch, keyboard-only, reduced-motion, high-contrast, and low-resolution flows

### Design foundation

- [x] Introduce shared design tokens and reusable controls
- [x] Redesign Parent settings as Overview, Children, Apps & Media, Screen Time, Appearance, and System sections
- [x] Add a live preview, search, filtering, bulk actions, consistent dialogs, and clear empty/error/loading states
  - [x] Add a live preview
  - [x] Add app search and visibility filtering
  - [x] Add bulk actions
  - [x] Make confirmation dialogs consistent
  - [x] Complete empty, error, and loading states
- [x] Create a coherent local icon system while keeping custom emoji tiles available

## v0.6.0 — Family Edition

- [ ] Add multiple child profiles with separate avatars, themes, tiles, favorites, and limits
  - [x] Introduce a versioned local profile model and authenticated management API without breaking the existing launcher API
  - [x] Add profile creation, editing, deletion, and selection to the Parent and child-facing interfaces
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

- [ ] Add more installer and interface languages beyond German and English
- [ ] Produce a first-party Debian package for Ubuntu, Linux Mint, and Zorin OS
  - [ ] Add a package-managed runtime mode that leaves updates to the system package manager
  - [ ] Publish through a signed first-party APT repository or Ubuntu PPA
- [ ] Publish an Arch Linux AUR recipe after the Debian package layout is stable
- [ ] Evaluate a classic-confined Snap and request Snap Store approval if host-app launching remains reliable
- [ ] Treat Flatpak as a feasibility track: prefer a reduced or self-hosted build unless sandbox integration and current Flathub policy become compatible with the launcher
- [ ] Pursue official Debian/Ubuntu and Arch repository adoption only as a long-term downstream-maintainer goal, not a release commitment
- [ ] Add a supported user-service lifecycle with useful status and recovery commands
- [ ] Add stable and opt-in preview update channels without weakening immutable releases
- [ ] Expand the automated and manual compatibility matrix across supported distributions

Packaging therefore proceeds in the practical order DEB/APT, AUR, classic Snap,
then Flatpak feasibility. Every package format must preserve local configuration,
desktop integration, host-app launching, and the stable-`main` updater contract.

## Release standard

A roadmap checkbox is not complete until:

- automated tests or an explicit manual test cover it;
- German and English behavior remain aligned;
- old configurations migrate safely;
- diagnostics do not expose private family data;
- relevant documentation and screenshots are updated;
- the release passes the full gate in [RELEASING.md](RELEASING.md).
