# Roadmap

## Completed

- [x] Package current working setup into a single installer
- [x] Remove machine-specific assumptions
- [x] Add optional PIN for parent settings
- [x] Admin page navigation (paginated tile editing)
- [x] One-line installer (`curl | bash`)
- [x] Standalone update mechanism with version check
- [x] Hardened Python server (threading, input validation, no `shell=True`)
- [x] Curated app recommendations with auto-detection
- [x] German and English language support
- [x] Simplified install documentation for non-technical parents
- [x] Support Chromium as well as Firefox
- [x] **Custom theme** — freely adjustable colors & background image
- [x] **Drag-and-drop** tile reordering in admin panel
- [x] **Screen time timer** with visual warning and block screen
- [x] **In-app overlay** (close button + timer) for every app type
- [x] **Keyboard navigation** (arrow keys, Enter, Escape)
- [x] **Automatic update check** on startup with badge notification
- [x] Export/import of launcher configs
- [x] Server-side parent authentication and modern PIN hashing
- [x] Config validation, atomic writes, and safe text rendering
- [x] Automated unit/API tests and GitHub Actions CI
- [x] Reproducible WSLg browser/audio/video smoke-test environment
- [x] Unified media, website, and local-app launch path
- [x] Tag-driven release workflow with versioned archives, checksums, provenance, and installer smoke test
- [x] Release-first updater with verified assets, downgrade protection, and v0.3.x compatibility fallback
- [x] Stable-main release promotion so legacy clients can never receive code newer than the latest release

## Near term

- [ ] Enable immutable releases in GitHub and publish the first versioned release
- [ ] Complete a real-device upgrade/rollback drill before the first public release
- [ ] Modularize the frontend and local server without adding runtime dependencies
- [ ] Capture polished screenshots for GitHub (reflecting v0.3.x features)
- [ ] Complete release smoke matrix on GNOME, KDE Plasma, and XFCE virtual machines
- [ ] **Favorites / "Last launched" highlight** improvements
- [ ] **Better admin layout** — search/filter tiles, batch visibility toggle

## Future ideas

- [ ] Multiple child profiles with separate tile sets
- [ ] Scheduled availability of specific apps (time-based rules)
- [ ] Whitelist browser mode (URL restrictions)
- [ ] Optional audio feedback and accessibility modes
- [ ] In-app timer / screen-time countdown display for kids
- [ ] Simple keyboard-only mode for accessibility

See the [technical audit](TECHNICAL_AUDIT.md) for the ordered modernization plan.
