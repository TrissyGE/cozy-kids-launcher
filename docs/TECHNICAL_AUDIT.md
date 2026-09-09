# Technical audit

This audit preserves the August 2026 modernization history and the September 9,
2026 follow-up review. The goal is to keep Cozy Kids Launcher lightweight and
local-first while making releases safer to maintain.

## September 9 review: current findings and scope

Reviewed baseline: `develop` at `91b7157` (PR #58), with published v0.6.0 and
`main` at `01dd9f0`. The working tree was clean. The frontend/server split,
profiles, schedules, activity, and media work is already present.

The latest baseline [CI run](https://github.com/TrissyGE/cozy-kids-launcher/actions/runs/33668153728)
passed both Python jobs but failed the saved-accessibility browser assertion.
An isolated local baseline passed **277 unit/integration tests** and all **18
core/accessibility journeys**. The failure screenshot showed the intended
appearance, but does not prove which computed property caused the assertion.
The follow-up uses a bounded wait for the same exact values and reports each
observed property; it does not weaken the criteria or retry the entire journey.

Confirmed defects addressed by the current increment:

- Custom theme CSS variables and background opacity survived switches to a
  built-in theme or a profile with fewer custom values. Custom inline colors
  could also override high contrast in the launcher, media library, and preview.
- The media fallback-cover rule also colored its nested play symbol, making the
  symbol invisible against the play badge. It now targets only the placeholder.
- The update action displayed success and scheduled an exit even after an HTTP
  failure or missing acknowledgement. It now requires `status: triggered`;
  cancellation and failure leave the launcher running with an actionable error.
- Package assistance always suggested `sudo apt install -y`, and the browser
  guessed that command even after authorization/network failures. It now shows
  only the server's native manual plan, or an honest unavailable/error state.
  Closed dialogs ignore late responses, and malformed package types return 400.
- Local, CI, and release checks had diverging hardcoded source lists. Their
  multi-file `bash -n` commands only checked the first file. A shared discovery
  runner checks every script separately; a deliberately broken second-script
  regression protects this behavior. CI bounds job duration and cancels only
  superseded PR runs.

Evidence is generated through `python3 scripts/check.py`, including new focused
browser regressions in `scripts/wsl/browser_regressions.py`. Native-provider
fixtures prove selection and command preparation, **not successful package
transactions**. No real updates, package installations, or desktop VMs are
started by this increment's automated checks. Neither `main` nor published
release tags are changed.

Next: review catalog metadata and desktop-entry parsing, add the searchable
catalog/detail UX, then implement and verify the package lifecycle on real
distributions. [ROADMAP.md](ROADMAP.md) records the execution order;
[PACKAGE_PROVIDERS.md](PACKAGE_PROVIDERS.md) records the deliberately limited
first provider mappings. This review is not a complete security audit or a new
GNOME/KDE/XFCE certification.

## Completed foundation

- Parent authentication is enforced by the local server for configuration changes, imports/exports, timer administration, updates, package assistance, exit, and shutdown.
- PINs created by current versions use PBKDF2-SHA256 with a random salt. Existing short SHA-256 hashes remain compatible and are upgraded after a successful login.
- The PIN hash is no longer returned by the public config endpoint. Authentication uses a short-lived, HTTP-only, same-site session cookie.
- Cross-site browser POST requests are rejected, JSON request sizes are limited, imported configs are validated, and config writes are atomic.
- User-controlled tile labels and emoji are rendered as text rather than executable HTML.
- Runtime events use bounded rotation, private file permissions, and a fixed privacy allowlist. Parent diagnostics exclude configuration values, PIN data, commands, URLs, usernames, and personal paths.
- A launcher file lock prevents duplicate runtime stacks. Process records bind PIDs to kernel start times and roles, so stale files cannot target reused PIDs or unrelated browsers.
- The launcher supervises its local server, replaces a failed runtime stack atomically, and stops after a bounded retry window instead of leaving a blank or endlessly restarting kiosk.
- Tile launches use an isolated process supervisor and Linux subreaper. Overlay, tile changes, updates, and launcher shutdown terminate only that recorded tree; command-name and active-window kill fallbacks are gone.
- Parent settings list validated local configuration backups without exposing their contents or paths. Restores preserve the current PIN and create a private pre-restore snapshot.
- Startup, logout, authenticated shutdown, update, and crash recovery follow an explicit private lifecycle-state contract with real Linux integration coverage.
- Standard-library unit and HTTP integration tests run in CI on supported Python versions.
- The frontend is split into focused CSS, shared state, launcher UI, Parent settings, and runtime-control modules while retaining the dependency-free installer and runtime.
- The local server delegates authentication, configuration, application discovery, process launching, media, timer, and update responsibilities to focused standard-library modules while preserving its API contract.
- X11 and Wayland display boundaries are documented and tested: X11 automation verifies the overlay close path and launcher focus recovery, while Wayland reports keep compositor-controlled stacking and focus as explicit manual observations.
- The primary Ubuntu 24.04 desktop matrix passed on commit `2947605`: GNOME 46/Wayland with Firefox 154 kiosk, Plasma 5.27/Wayland with Chrome 152 fullscreen, and XFCE 4.18/X11 with Chrome 152 kiosk. Each machine-readable report records `outcome: passed`, and every row includes fresh-login, display, overlay, focus, singleton-shortcut, and clean-poweroff observations.
- Chromium journeys exercise real keyboard and touch input, reduced-motion and forced-colors preferences, and the 800x600 home and Parent layouts. Focus and gesture handling stop at dialog and Parent-settings boundaries.

## Completed release foundation

- A tag-driven workflow checks that `v<version>` matches `VERSION`, runs tests and an isolated installer smoke test, and builds versioned tar/zip archives.
- Every release includes `SHA256SUMS` and a GitHub build-provenance attestation before it is published.
- The updater prefers complete stable release assets, verifies the tar archive, rejects downgrades, and preserves configuration and installer choices.
- Legacy v0.3.x clients remain compatible through `main/VERSION`; current clients use that path only until their first verified release update.
- Releases are published before their exact commit is fast-forwarded to `main`, keeping the legacy source equal to or older than the latest release. A scheduled workflow detects branch drift.
- The server and frontend share the updater's release-first status model, and the launcher owns the update trigger exactly once.
- A disposable v0.4.0 installation was upgraded through the published v0.4.1 release with checksum verification and byte-identical configuration preservation.

## Next: platform confidence

1. Extend the passing Ubuntu desktop matrix to Linux Mint and Zorin OS, plus optional X11 rows where the distribution still supports them.
2. Expand installer upgrade/rollback coverage as configuration schema migrations evolve.
3. Add manual screen-reader coverage on the supported Linux desktops.

## Product work after the foundation

Multiple child profiles, scheduled application availability, exact-origin
browser allowlists, search/bulk editing in Parent settings, opt-in local audio
feedback, fixed unscored celebration moments, and combinable accessibility
presets are now covered by the v0.6.0 work.

The next product increment is the v0.8.0 catalog and provider work, following
the post-v0.6.0 quality repairs above.
