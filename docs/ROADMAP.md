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

## v0.6.0 — Family Edition & Delight

### Family Edition

- [x] Add multiple child profiles with separate avatars, themes, tiles, favorites, and limits
  - [x] Introduce a versioned local profile model and authenticated management API without breaking the existing launcher API
  - [x] Add profile creation, editing, deletion, and selection to the Parent and child-facing interfaces
- [x] Add a guided first-run setup for language, child, apps, time rules, and appearance
- [x] Add weekly screen-time schedules and per-app availability rules
  - [x] Add a bounded local-time schedule model, child-safe status API, and server-side launch enforcement
  - [x] Add the Parent editor, child-facing blocked states, and native-app boundary enforcement
- [x] Add a local, optional parent dashboard for recent activity and usage duration
  - [x] Add bounded opt-in local activity storage, owned-runtime duration capture, and Parent-protected read and clear APIs
  - [x] Add the bilingual Parent dashboard, local export, and removal controls
- [x] Add a browser allowlist with understandable navigation boundaries
- [x] Keep all profile and activity data local, exportable, and removable

### Delight

- [x] Add a cover-based local media library with favorites, recents, and resume support
  - [x] Add a bounded, path-private local catalog API with sidecar and folder-cover discovery
  - [x] Add the child-facing cover library and launch individual media items
  - [x] Add bounded per-profile media favorites and recents
  - [x] Add reliable per-profile resume positions where a player exposes a controllable local contract
    - [x] Isolate MPV's documented native resume state per child profile
    - [x] Capture VLC positions through a supervised local adapter without using global viewing history
    - [x] Keep Celluloid, Totem, and desktop openers as explicit start-over fallbacks
- [x] Add animated world themes and optional time-of-day variants
- [x] Add subtle navigation, launch, success, and return transitions
- [ ] Add optional local sounds and Linux text-to-speech feedback
- [ ] Add accessibility presets for larger text, contrast, reduced motion, and keyboard-only operation
- [ ] Add optional, non-manipulative celebration moments without engagement scoring

## v0.8.0 — Platform

### Cross-distribution app catalog

- [ ] Redesign the Parent app catalog with search, child-friendly categories, detail views, and clear install, retry, update, and removal states
- [ ] Expand the curated catalog with more educational, creative, media, and accessible apps such as GCompris, Tux Paint, KolourPaint, KTurtle, KGeography, KStars, and Stellarium where each distribution provides a maintained package
- [ ] Show age guidance, offline capability, license, input methods, and privacy/network expectations before a parent installs an app
- [ ] Replace distribution-specific install commands with tested package-provider adapters for APT, DNF, Pacman, Zypper, and suitable Flatpak remotes
- [ ] Keep every package action Parent-authenticated, explicitly confirmed, argv-based, allowlisted, and free of downloaded arbitrary shell scripts
- [ ] Preserve install progress and recoverable error state across a launcher restart without collecting package or family telemetry
- [ ] Test catalog discovery and package actions on Debian/Ubuntu derivatives, Fedora, openSUSE, and Arch derivatives

### Packaging and lifecycle

- [ ] Add more installer and interface languages beyond German and English
- [ ] Produce a first-party Debian package for Ubuntu, Linux Mint, and Zorin OS
  - [ ] Add a package-managed runtime mode that leaves updates to the system package manager
  - [ ] Publish through a signed first-party APT repository or Ubuntu PPA
- [ ] Produce first-party RPM packages and evaluate signed COPR or Open Build Service distribution after the Debian package layout is stable
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

## v0.9.0 — Living Room

- [ ] Add optional gamepad and simple remote-control navigation with the same focus and modal boundaries as keyboard input
- [ ] Let parents add bounded local media roots without exposing filesystem paths to the child-facing API
- [ ] Handle removable-media disconnect and reconnect states without stale covers, crashes, or path leakage
- [ ] Add optional child-friendly folders and categories without recommendations, streaks, or engagement scoring
- [ ] Recover cleanly from suspend, resume, display hotplug, and temporary audio-device loss
- [ ] Define and measure cold-start, idle-memory, and low-powered-device performance budgets

## v1.0.0 — Long-term Stable

- [ ] Publish a compatibility policy for configuration schemas, the loopback API, package migrations, and update channels
- [ ] Complete a documented threat model and security review of Parent authentication, local HTTP boundaries, imports, updates, and process launching
- [ ] Verify clean install, script-to-package migration, upgrade, rollback, backup restore, and uninstall paths on every supported distribution
- [ ] Complete manual screen-reader coverage alongside keyboard, touch, reduced-motion, high-contrast, and low-resolution testing
- [ ] Make release artifacts and repository metadata reproducible, signed where applicable, and independently verifiable
- [ ] Document a sustainable translation, accessibility, security-reporting, and downstream-packaging contribution workflow

## Release standard

A roadmap checkbox is not complete until:

- automated tests or an explicit manual test cover it;
- German and English behavior remain aligned;
- old configurations migrate safely;
- diagnostics do not expose private family data;
- relevant documentation and screenshots are updated;
- the release passes the full gate in [RELEASING.md](RELEASING.md).
