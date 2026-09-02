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

The frontend stays dependency-free and is split by responsibility:

- `src/index.html` contains the document structure and template-provided labels
- `src/frontend/design-system.css` contains shared spacing, sizing, radius, focus, and motion tokens plus reusable control and surface primitives
- `src/frontend/styles.css` contains launcher-specific themes, visual rules, and responsive layout
- `src/frontend/state.js` contains shared state and localized UI strings
- `src/frontend/icons.js` contains the dependency-free local SVG registry and the safe text fallback for custom tile emoji
- `src/frontend/dialogs.js` owns accessible confirmation dialogs and focus restoration
- `src/frontend/theme-runtime.js` applies shared world-theme motion and local time-of-day classes to the launcher, media library, and isolated Parent preview
- `src/frontend/launcher-ui.js` renders the child-facing launcher, themes, paging, and PIN gate
- `src/media.html` and `src/frontend/media-library.*` render the local cover library and submit only opaque media IDs
- `src/frontend/parent-settings.js` owns the Overview, Children, Apps & Media, Screen Time, Appearance, and System sections plus tile editing, recommendations, and updates
- `src/frontend/runtime-controls.js` owns timer flows, device status, import/export, backups, and keyboard control

The installer renders or copies these files below the local application root. The Python server serves them as ordinary static assets, so development and production require no package manager or bundler.

World effects are two additive, profile-scoped booleans in the existing version 2 configuration. Missing values remain disabled for upgrade compatibility, while new installations enable only gentle motion. The runtime uses CSS animation, schedules a class refresh at the next local day-period boundary, and never calls a time or location service. The operating system's reduced-motion preference always suppresses the animation.

Asynchronous frontend resources use explicit loading, empty, error, and success
states. Configuration remains the only startup-critical request: a failure leaves
an actionable localized retry screen, while app, browser, recommendation, and
feature discovery fail independently without hiding configured launcher tiles.
Retry actions repeat only their local request, and failed discovery never clears
or rewrites the saved browser or tile configuration.

Interface chrome uses a local, stroke-based SVG icon registry with no font or
network dependency. Known built-in tile emoji receive matching local artwork at
render time; stored values are not migrated, and every unrecognized or custom
emoji is still inserted with `textContent`. Existing configurations therefore
retain both their data and the ability to use arbitrary emoji tiles.

### 2. Local HTTP server

A tiny Python HTTP server:

- serves the frontend
- loads and saves config JSON
- validates imported and edited configuration before an atomic write
- lists installed applications
- resolves legacy media, website, and application commands into one launch path
- launches configured programs with a shared overlay lifecycle
- handles shutdown and exit actions

`src/server.py` remains the localhost HTTP composition root. Domain behavior is
kept in focused standard-library modules: configuration storage and validation,
Parent authentication, app/browser discovery, embedded-browser policy, application launching, media
discovery, timer state, update discovery/triggering, lifecycle state, process
ownership, backups, and privacy-safe diagnostics. The server supplies installed
paths and turns module results into the existing HTTP responses; the modules do
not depend on the HTTP handler.

### 3. Launch adapters

Every tile is posted to `/launch/<tile-id>`. The server normalizes the existing command formats into one of three actions:

- **media** — opens every populated media directory as a VLC or MPV playlist, with a desktop opener as fallback
- **web** — redirects compatible embedded sites to the wrapper or starts the selected browser in a dedicated external profile
- **app** — starts an argument vector directly without a shell

Existing `special:` commands and older `xdg-open URL` browser tiles remain compatible. Embedded tiles automatically allow their configured start origin and may carry at most 20 additional exact `http(s)` origins in `browserAllowedOrigins`. `browser_policy.py` canonicalizes that list; the server accepts `browser.html` only when its tile and URL match the active configuration, then emits a per-request `frame-src` Content Security Policy. The wrapper sandbox cannot navigate the launcher top level, and a blocked frame navigation produces a local child-friendly explanation. External mode intentionally sits outside this navigation boundary and is labelled accordingly in Parent settings. Recommended public media sites use external mode because framing policies, login flows, and DRM make third-party iframe behavior unreliable.

The read-only `/api/media` foundation scans only the configured local Videos
and Music roots, skips hidden content and links outside those roots, and caps a
scan at 5,000 directories, 20,000 files, and 2,000 returned items. It exposes
stable opaque IDs, display titles, media kinds, and optional local cover
URLs—never filesystem paths. Cover requests are resolved back through a fresh
bounded catalog and can serve only adjacent `.jpg`, `.jpeg`, `.png`, or `.webp`
sidecars and conventional `cover`/`folder` images of at most 10 MiB. The
Launcher UI opens `media.html` for the existing media command and renders the
catalog with dependency-free, keyboard-accessible HTML. `/api/media/play`
accepts only an opaque catalog ID plus a currently visible media-tile ID,
rechecks that tile's schedule, resolves the file through a fresh scan, and then
uses the same owned process and activity boundary as other local launches. A
direct POST to the legacy `/launch/<media-tile>` route still opens the
all-folder playlist for compatibility.

`media_state.py` owns child-specific library preferences outside the exported
configuration schema. It stores only opaque media IDs in a private atomic file,
with independent favorites and most-recent-first history for at most 20
profiles. Favorites are capped at 200 and history at 50 items. `/api/media`
filters both lists through the current bounded catalog before returning them,
and `/api/media/favorite` accepts only a current catalog item plus a visible,
currently available media tile. A successful individual launch moves that item
to the active profile's recent list; deleting a profile removes its media state.

Individual media playback prefers MPV when it is installed, while the legacy
all-folder route keeps its established VLC-first player order. For individual
MPV launches, `media_resume.py` creates a private native
`watch-later` directory for the active profile. MPV is told to retain only its
`start` property, to check the source modification time before resuming, and not
to write filenames into those files. The directory path and playback position
remain outside the HTTP API and exported configuration.

When MPV is unavailable, `media_session.py` starts a dedicated VLC instance
with its bundled stdin remote-control interface, samples time and duration, and
stores the final useful position through `media_resume.py`. The private atomic
record is capped at 200 items and 64 KiB, and contains only opaque media IDs,
whole seconds, file size, and modification time. It never stores a path or
title, ignores stale positions when a file changes, and clears positions near
the beginning or end. VLC's global recent-play and continue-playback features
are disabled for this launch. Celluloid, Totem, and desktop openers continue to
start from the beginning because they do not provide an equally controlled
dependency-free contract. A missing adapter or unavailable storage skips resume
and uses normal playback, while position read/write failures do not interrupt
an already started player.
Deleting a profile removes all of its resume data without following symbolic
links.

`application_launcher.py` owns action normalization and orchestration. It starts
argument vectors below `process_supervisor.py`, waits for a verified process
record, and only then starts `overlay.py`. Missing ownership or overlay startup
fails closed and tears down the newly owned process tree.

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
- the launcher holds a non-blocking file lock, so autostart and shortcut clicks cannot create duplicate browser/server stacks
- server, main browser, active-tile supervisor, overlay, and watchdog records combine PID, kernel start time, and a fixed role
- stale or forged records are discarded without signalling their numeric PID, preventing PID reuse from targeting an unrelated process
- Firefox and Chromium use dedicated launcher profiles; ownership never falls back to a global browser `pgrep`
- launcher cleanup and updates terminate only processes whose complete identity still matches their record
- local apps, media players, and external browsers run below one active-tile supervisor instead of being found later by command name
- the supervisor starts in an isolated session and acts as a Linux child subreaper, retaining ownership across normal forks and double-forks
- the overlay closes the verified supervisor; it never kills every matching executable or falls back to closing whichever window happens to be active
- launching another tile, exiting, updating, or stopping the launcher first terminates the previous tile's complete owned process tree
- the launcher checks its local server while the kiosk is open; a failed server causes the owned browser and watchdog to close before the complete stack is restarted
- runtime recovery is limited to three attempts within 60 seconds with a short increasing delay; exhausting the limit closes the stack and shows a localized error instead of looping or leaving a blank kiosk
- the launcher's `EXIT` trap applies the same owned-process cleanup when the launcher itself fails or is stopped
- an atomic private lifecycle file records only allowlisted state, reason, and bounded recovery attempt; the complete transition contract is documented in [LIFECYCLE.md](LIFECYCLE.md)
- authenticated shutdown and Parent exit actions write short-lived intents, allowing the cleanup trap to distinguish them from an ordinary session logout without trusting arbitrary signal metadata

The precise X11 and Wayland guarantees for browser modes, overlay stacking, and
focus recovery are documented in [DISPLAY_BEHAVIOR.md](DISPLAY_BEHAVIOR.md).

### 7. Configuration lifecycle

- every current configuration carries an integer `configVersion`
- files without a version are treated as legacy schema 0 and migrated atomically
- schema 2 stores child-specific appearance, tiles, favorites, and limits in a bounded `profiles` collection while keeping language, Parent authentication, browser choice, and system controls global
- schema 0 and 1 configurations become a `default` profile without losing their existing child-facing settings
- the runtime and `/api/config` retain the original flat active-profile view so existing frontend code and API clients continue to work during the incremental v0.6.0 rollout
- profile creation, selection, and deletion use dedicated Parent-authenticated endpoints; the active profile and the final remaining profile cannot be deleted
- the child-facing profile picker exposes only profile summaries and sends a switch through the same Parent PIN/session boundary; switching profiles also separates local recent-app UI state and clears the active runtime timer
- optional `weeklySchedule` and `appAvailability` rules are stored inside each profile as bounded local-time windows; missing or disabled rules preserve the unrestricted legacy behavior
- `schedule_rules.py` validates and evaluates both rule types, `/api/availability/status` exposes only the current child-safe result, and `/launch/<tile-id>` repeats the same decision before any process or browser can start
- `schedule-controls.js` edits those rules entirely through safe DOM APIs and polls the local status without disturbing focus; the launcher disables unavailable tiles and explains profile-wide and per-app blocks in an accessible dialog
- embedded browser pages return to the launcher when their tile becomes unavailable; native and external launches pass the stable tile ID to their overlay, which closes only its explicitly owned process when the same local status boundary changes
- optional activity tracking is a global boolean that defaults to false; when enabled, `activity_store.py` keeps only profile IDs, tile IDs, start timestamps, and completed durations in a private, bounded 90-day/1,000-record local store
- native, media, and external-browser durations are finalized by the already-owned `process_supervisor.py`; embedded pages use an opaque in-memory token and a loopback finish request, so client-provided timestamps or labels are never trusted
- `/api/activity`, `/api/activity/export`, and `/api/activity/clear` use the existing Parent-access boundary, including a valid session whenever a PIN is configured; deleting a child profile also removes its retained activity, while tracking I/O failures never change application launch behavior
- `activity-dashboard.js` resolves current profile and tile labels from a separately returned display catalog, renders at most 12 recent records, and keeps exports limited to the stored identifiers and timestamps rather than copying labels, commands, or URLs
- new installations set `setupCompleted` to false and use a five-step local first-run flow; missing flags on existing configurations are treated as completed, so upgrades never force the wizard onto current families
- German and English UI dictionaries are generated from the installer's canonical translations, shipped as local JSON assets, and loaded before the first render; the installer-rendered strings remain an offline fallback
- migrations preserve unknown keys so newer optional data is not discarded accidentally
- files from a schema newer than the installed launcher are rejected instead of being rewritten
- imported and edited configurations pass through the same migration and validation boundary
- Parent settings discover only timestamped `config.json` backups below the fixed local backup root; the API returns metadata, never filesystem paths or configuration values
- restore requests accept a strict backup identifier rather than a path, reject symlinks and oversized or invalid files, and pass the result through the current schema validator
- restores replace configuration only, never installed program code; the active Parent PIN is preserved and a private snapshot of the current configuration is written first

### 8. Runtime diagnostics

- the server writes size-limited JSON-line event logs under `~/.local/state/cozy-kids-launcher/`
- rotation retains three small backup files instead of allowing unbounded growth
- event names and detail fields use a fixed privacy allowlist; arbitrary messages and configuration values are rejected
- a successful automatic recovery records only its bounded attempt number, never process IDs or user data
- the Parent settings download contains technical versions, configuration readability and schema version, and recent allowlisted events
- diagnostics include only the allowlisted current lifecycle state, reason, and bounded recovery attempt
- diagnostics never include PIN data, titles, tile labels, commands, URLs, usernames, home paths, or browser-profile data
- logs and diagnostics remain local unless a parent deliberately shares the downloaded file

## Why not do everything in Plasma directly?

Because desktop-shell configuration becomes brittle fast:

- folder views cache strangely
- screen mappings drift
- widget layouts are fragile
- switching modes by rewriting Plasma config is unreliable

The browser-overlay approach is much more robust.
