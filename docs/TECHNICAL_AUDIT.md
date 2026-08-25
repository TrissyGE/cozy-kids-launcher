# Technical audit

This audit captures the modernization priorities identified in August 2026. The goal is to keep Cozy Kids Launcher lightweight and local-first while making releases safer to maintain.

## Completed foundation

- Parent authentication is enforced by the local server for configuration changes, imports/exports, timer administration, updates, package assistance, exit, and shutdown.
- PINs created by current versions use PBKDF2-SHA256 with a random salt. Existing short SHA-256 hashes remain compatible and are upgraded after a successful login.
- The PIN hash is no longer returned by the public config endpoint. Authentication uses a short-lived, HTTP-only, same-site session cookie.
- Cross-site browser POST requests are rejected, JSON request sizes are limited, imported configs are validated, and config writes are atomic.
- User-controlled tile labels and emoji are rendered as text rather than executable HTML.
- Standard-library unit and HTTP integration tests run in CI on supported Python versions.

## Completed release foundation

- A tag-driven workflow checks that `v<version>` matches `VERSION`, runs tests and an isolated installer smoke test, and builds versioned tar/zip archives.
- Every release includes `SHA256SUMS` and a GitHub build-provenance attestation before it is published.
- The updater prefers complete stable release assets, verifies the tar archive, rejects downgrades, and preserves configuration and installer choices.
- Legacy v0.3.x clients remain compatible through `main/VERSION`; current clients use that path only until their first verified release update.
- Releases are published before their exact commit is fast-forwarded to `main`, keeping the legacy source equal to or older than the latest release. A scheduled workflow detects branch drift.
- The server and frontend share the updater's release-first status model, and the launcher owns the update trigger exactly once.

## Next: maintainability

1. Complete a disposable real-device upgrade and rollback drill from v0.4.0 to the next published patch release.
2. Split the large frontend template into focused CSS and JavaScript modules while keeping a dependency-free production build.
3. Split server responsibilities into config, authentication, application discovery, process launching, update discovery, and timer modules.
4. Add structured runtime logging and a small diagnostics export that excludes personal configuration and PIN data.

## Then: platform confidence

1. Test KDE Plasma, GNOME, and XFCE across Ubuntu, Linux Mint, and Zorin OS.
2. Document Wayland and X11 behavior for overlays, focus recovery, and kiosk browsers.
3. Add installer upgrade/rollback coverage and schema-versioned configuration migrations.
4. Exercise keyboard-only, touch, low-resolution, and screen-reader flows.

## Product work after the foundation

- Multiple child profiles
- Scheduled application availability
- Browser allowlists
- Improved accessibility and audio feedback
- Search and bulk editing in Parent settings

These features should follow the release and platform work so new behavior is built on a testable base.
