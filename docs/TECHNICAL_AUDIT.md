# Technical audit

This audit captures the modernization priorities identified in August 2026. The goal is to keep Cozy Kids Launcher lightweight and local-first while making releases safer to maintain.

## Completed foundation

- Parent authentication is enforced by the local server for configuration changes, imports/exports, timer administration, updates, package assistance, exit, and shutdown.
- PINs created by current versions use PBKDF2-SHA256 with a random salt. Existing short SHA-256 hashes remain compatible and are upgraded after a successful login.
- The PIN hash is no longer returned by the public config endpoint. Authentication uses a short-lived, HTTP-only, same-site session cookie.
- Cross-site browser POST requests are rejected, JSON request sizes are limited, imported configs are validated, and config writes are atomic.
- User-controlled tile labels and emoji are rendered as text rather than executable HTML.
- Runtime events use bounded rotation, private file permissions, and a fixed privacy allowlist. Parent diagnostics exclude configuration values, PIN data, commands, URLs, usernames, and personal paths.
- A launcher file lock prevents duplicate runtime stacks. Process records bind PIDs to kernel start times and roles, so stale files cannot target reused PIDs or unrelated browsers.
- Standard-library unit and HTTP integration tests run in CI on supported Python versions.

## Completed release foundation

- A tag-driven workflow checks that `v<version>` matches `VERSION`, runs tests and an isolated installer smoke test, and builds versioned tar/zip archives.
- Every release includes `SHA256SUMS` and a GitHub build-provenance attestation before it is published.
- The updater prefers complete stable release assets, verifies the tar archive, rejects downgrades, and preserves configuration and installer choices.
- Legacy v0.3.x clients remain compatible through `main/VERSION`; current clients use that path only until their first verified release update.
- Releases are published before their exact commit is fast-forwarded to `main`, keeping the legacy source equal to or older than the latest release. A scheduled workflow detects branch drift.
- The server and frontend share the updater's release-first status model, and the launcher owns the update trigger exactly once.
- A disposable v0.4.0 installation was upgraded through the published v0.4.1 release with checksum verification and byte-identical configuration preservation.

## Next: maintainability

1. Split the large frontend template into focused CSS and JavaScript modules while keeping a dependency-free production build.
2. Continue splitting server responsibilities into authentication, application discovery, process launching, update discovery, and timer modules.
3. Extend explicit ownership from the core launcher stack to complete per-tile child process trees and crash recovery.

## Then: platform confidence

1. Test KDE Plasma, GNOME, and XFCE across Ubuntu, Linux Mint, and Zorin OS.
2. Document Wayland and X11 behavior for overlays, focus recovery, and kiosk browsers.
3. Expand installer upgrade/rollback coverage as configuration schema migrations evolve.
4. Exercise keyboard-only, touch, low-resolution, and screen-reader flows.

## Product work after the foundation

- Multiple child profiles
- Scheduled application availability
- Browser allowlists
- Improved accessibility and audio feedback
- Search and bulk editing in Parent settings

These features should follow the release and platform work so new behavior is built on a testable base.
