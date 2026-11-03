# Roadmap

Cozy Kids Launcher is growing into a lightweight, local-first family console for Linux: playful and simple for children, understandable and dependable for parents.

The roadmap is intentionally release-oriented. Stability work comes before the product features that depend on it, and every release must preserve legacy configurations and the stable-`main` updater contract.

## Current execution order — post-v0.6.0

The September 9 review starts from `develop` at `91b7157`, not the earlier
frontend-splitting plan: v0.5.0 and v0.6.0 are already published. New work stays
on topic branches ultimately targeting `develop` (dependent draft PRs may be
stacked until their parent lands); this plan does not bump `VERSION` or
publish a release. See [TECHNICAL_AUDIT.md](TECHNICAL_AUDIT.md) for findings.

The November 2 continuation merged the quality/provider foundation in
[#59](https://github.com/TrissyGE/cozy-kids-launcher/pull/59) and repaired the
Python 3.9 runner in [#61](https://github.com/TrissyGE/cozy-kids-launcher/pull/61).
Terminal-free installation was merged in
[#60](https://github.com/TrissyGE/cozy-kids-launcher/pull/60). The discovery
increment was merged in [#62](https://github.com/TrissyGE/cozy-kids-launcher/pull/62).
Remaining distribution and desktop acceptance
below still applies to release certification.
Owned KDE fullscreen and the real-app desktop probe were merged in
[#63](https://github.com/TrissyGE/cozy-kids-launcher/pull/63), and installed-app
discovery was merged in [#64](https://github.com/TrissyGE/cozy-kids-launcher/pull/64).
The current increment expands sourced Parent guidance and makes completed work
visible in the checklists below; see [review scope](CATALOG_GUIDANCE.md).

1. **Quality repair — merged in #59:** shared local/CI/release checks,
   diagnosed browser assertions, corrected custom-theme/accessibility
   conflicts, and update/install UI states that reflect acknowledged results.
   Regression coverage precedes catalog expansion.
2. **Platform foundation — merged in #59:** detect native package
   managers and prepare allowlisted, explicitly manual installation plans.
   This is not an automatic package executor or a cross-distribution support claim.
3. **Terminal-free installation — merged in #60:** on the
   initial Ubuntu/Mint/Zorin targets, review required packages/download size,
   confirm explicitly, authorize through the desktop's system dialog, show real
   progress, and offer adding the installed app as a tile. No terminal is part
   of the normal catalog flow. Real TuxMath installation
   passed on Ubuntu KDE/Wayland. Tile addition and start passed; a real return
   failure first exposed an SDL input grab. The windowed workaround was rejected:
   TuxMath now uses confirmed, compositor-managed fullscreen on X11/XWayland.
   Launching from the kiosk-fullscreen launcher, entering a game and returning
   through the overlay passed in the KDE/Wayland VM. Further desktop failure scenarios and Mint/Zorin
   acceptance remain open release gates.
4. **Then expand the catalog:** searchable, categorized Parent catalog with
   app details, honest availability, age/offline/privacy/input metadata, and
   source-backed package mappings. Audit desktop-entry discovery and existing
   recommendation wording before expanding the catalog.
   Search, combined filters and sourced detail fields are implemented in a
   merged discovery increment (#62). Its Install action retains the terminal-free
   review, confirmation and PackageKit flow; copying a command is not the normal
   Parent installation path. New app recipes still require fullscreen acceptance.
   Installed-app discovery now implements XDG roots/desktop-ID precedence,
   hidden overrides, locale names and argv-preserving field-code handling in a
   separate increment; see [scope and evidence](APP_DISCOVERY.md).
5. **Then broaden package actions:** update/removal and richer restart recovery;
   verify real disposable APT/DNF/Pacman/Zypper environments and evaluate
   Flatpak remotes separately. The current journal never automatically replays
   an interrupted installation; uncertain state is reported honestly.
6. Continue living-room and packaging milestones below after their prerequisites
   pass. Refresh desktop evidence whenever the affected runtime changes.

### Fullscreen product contract

Fullscreen is the default for both the launcher and child apps. Window mode is
an explicit Parent/developer choice, not a stability workaround counted as a pass.
The installer already defaults to chrome-free `kiosk`; graphical acceptance must
test that default too, not only the windowed diagnostic harness.

- [x] Restore the TuxMath fullscreen recipe without overwriting explicit custom arguments
- [x] Verify TuxMath fullscreen, menu-to-game transition, overlay close and return to a fullscreen launcher on the current KDE/Wayland VM
- [ ] Repeat the corrected TuxMath flow on native X11 and GNOME Wayland, including physical keyboard/touch input
- [x] Replace stripped legacy KDE fullscreen requests with owned, compositor-confirmed fullscreen (#63)
- [x] Add a repeatable real catalog-app desktop probe, including isolated Firefox snap profiles (#63)
- [x] Record KTurtle/KBruch fullscreen, overlay-close and cleanup automation on KDE/Wayland, with manual gaps explicit (#63; [evidence scope](CATALOG_FULLSCREEN.md))
- [ ] Complete the per-app fullscreen audit across the remaining catalog and native GNOME/X11 sessions, including physical input
- [ ] Require fullscreen, usable game input, a reachable close control and launcher return together in per-app desktop acceptance

The current increment is tracked under **Unreleased** in the changelog. Historical
release checkboxes below remain historical; an old desktop report does not
certify every later commit. Task checkboxes record implemented, tested work;
partial tasks are split so completed parts can be checked independently.
Distribution, desktop and publication gates remain separate open tasks until
their own evidence is complete. See the release standard at the end.

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
- [x] Add optional local sounds and Linux text-to-speech feedback
- [x] Add accessibility presets for larger text, contrast, reduced motion, and keyboard-only operation
- [x] Add optional, non-manipulative celebration moments without engagement scoring

## v0.8.0 — Platform & Living Room

### Cross-distribution app catalog

- [x] Add Parent app-store search, category/status filters, counts and keyboard-accessible detail views (#62)
- [x] Show loading, empty, unavailable and error states with retry for app discovery/install assistance (#59–#62)
- [x] Prevent duplicate tiles, including hidden ones, and roll back rejected tile saves (#62)
- [x] Discover installed apps through XDG precedence, desktop-ID overrides, translated names and argv-preserving Exec handling (#64)
- [x] Add metadata fields for age guidance, offline use, license, input and network expectations, showing unknown values explicitly (#62)
- [x] Add initial sourced guidance for Tux Paint, GCompris and YouTube Kids (#62)
- [x] Show localized review dates and supporting HTTPS references in app details, with explicit unknowns and bounded, deduplicated links
- [x] Add sourced guidance for eight existing KDE recommendations and correct KBlocks' no-time-pressure claim ([review scope](CATALOG_GUIDANCE.md))
- [x] Review the remaining six web recommendations with provider sources, including online requirements and profile controls where applicable
- [x] Add sourced learning guidance for Blinken, KWordQuiz and Parley
- [x] Review the remaining eleven native recommendations and document network/privacy findings with explicit unknowns ([catalog guidance](CATALOG_GUIDANCE.md))
- [x] Add curated KolourPaint and KGeography recommendations after package, fullscreen, input and return checks
- [ ] Qualify KStars and Stellarium for the catalog after reliable launch and input across the desktop matrix
- [x] Detect native APT, DNF, Pacman and Zypper environments and prepare allowlisted manual plans (#59; [provider scope](PACKAGE_PROVIDERS.md))
- [x] Add terminal-free PackageKit/APT review, consent, system authorization, progress and add-tile flow (#60)
- [x] Protect existing package routes with Parent/origin checks, catalog-controlled names and expiring single-use confirmation (#60)
- [x] Add private restart journaling that reports uncertainty and never replays installation consent (#60)
- [x] Add explicit APT PackageKit update and removal review, consent and progress for a single selected app
- [x] Reattach known APT PackageKit jobs after a launcher restart, with read-only progress and no replay of consent
- [x] Reconcile jobs that finish while the launcher is offline using exact daemon history and a fresh package lookup
- [ ] Implement tested native DNF/Pacman/Zypper and managed Flatpak execution adapters
- [ ] Complete Ubuntu/Mint/Zorin authorization/failure scenarios and remaining desktop acceptance for direct installation
- [ ] Test catalog discovery and package actions on Debian/Ubuntu derivatives, Fedora, openSUSE, and Arch derivatives

### More languages and extensible translations

- [x] Ship German/English UI resources with generated-locale freshness checks and live language switching
- [x] Introduce one language registry for installer, backend validation and all language pickers
- [x] Move the installer translation table into locale data files shared with browser locale generation, with English fallback and key and placeholder validation
- [x] Move setup and child profile texts into locale data and handle unavailable language files during setup
- [x] Localize themes, media startup text, settings labels, dates and catalog actions through shared data
- [x] Validate count placeholders and select singular or plural catalog and package messages using the active locale
- [x] Translate Spanish across guided installation, child UI, Parent settings, catalog and recovery messages
- [x] Translate French across the same surfaces
- [x] Let existing families change the launcher language in Parent settings while preserving profile names and tile labels
- [x] Apply the saved language to native helper windows and the embedded browser wrapper after an in-app language change
- [x] Add Italian installer, launcher, native helper and catalog translations through the shared locale pipeline
- [ ] Confirm Italian wording and tone with a fluent reviewer
- [x] Make app descriptions, guidance and source labels use locale-key fallbacks so new packs can add translations through data
- [x] Document translation contributions, terminology and review ownership; report missing source keys for draft and enabled languages
- [x] Exercise all five enabled languages in the 800×600 Parent layout with localized counts and keyboard focus recovery
- [ ] Complete physical-device language acceptance for long labels, localized dates and available speech voices
- [x] Add registry-driven RTL layout, mirrored navigation and synthetic browser coverage
- [ ] Complete RTL language acceptance with a reviewed language pack such as Arabic or Hebrew

The [translation guide](LOCALIZATION.md) describes the shared registry,
contributor workflow, and coverage reports. German, English, Spanish, French
and Italian are enabled.

### Lifecycle and reach

- [x] Add an opt-in systemd user service with status, recovery, stop and disable commands ([lifecycle guide](LIFECYCLE.md))
- [x] Keep stable updates as the default and expose an explicit Preview choice in Parent settings and the CLI
- [x] Select immutable release candidates with numeric ordering and return from a candidate to the matching stable release
- [x] Verify preview archives with the existing checksum and rollback path and fail closed when preview discovery is unavailable
- [x] Build and attest preview releases through a workflow path that excludes stable-main promotion
- [ ] Verify the first published release candidate on an opted-in disposable installation
- [ ] Expand the automated and manual compatibility matrix across supported distributions

### Family time and profiles

- [x] Add an optional daily allowance per child, shared across supported app types
- [x] Persist consumption per profile across launcher restarts and profile switches, with defined suspend, midnight and clock-change behavior
- [x] Enforce the allowance on new launches and stop the currently owned activity when time runs out
- [x] Show the next allowed time and remaining budget without exposing the full family schedule in the child-facing view
- [x] Add a local request for more time with PIN-confirmed one-off extensions
- [x] Add Parent-reviewed profile duplication without copying usage history or media resume state

See [daily allowance and profile copying](ARCHITECTURE.md#daily-allowance-and-profile-copying) for runtime behavior.

### Living Room

#### RetroGameCorner

Use RetroArch as the default for each system with a qualified core that matches
or exceeds the standalone emulator in game compatibility, performance, input
and desktop integration. Evaluate standalone emulators first for newer systems
that lack an equivalent core, including Wii U and PS3.

- [x] Put emulator installation in a dedicated RetroGameCorner Parent section using the shared app-store flow
- [x] Show one optional RetroGameCorner Home tile that opens the child's approved games in a cover library
- [x] Support local cover images and opt-in automatic cover downloads from Libretro
  - [x] Read local Miyoo cover art from the adjacent `Imgs/` directory
- [x] Explain local ROMs, BIOS files, controls, age/content choices and save data in Parent settings
- [x] Accept Parent-supplied Game Boy, Game Boy Color and Game Boy Advance ROMs from bounded local folders
- [x] Keep approvals per child, hide folder paths from the child configuration, and handle unavailable or replaced ROMs
- [x] Assign private mGBA save and save-state directories per child and game
- [x] Add NES, Super Nintendo, Sega Master System and Game Gear cartridge games through the Mednafen Parent installer
- [ ] Make PlayStation 1 the next optional system in RetroGameCorner
  - [x] Import Parent-supplied BIOS files locally, validate regional PS1 and supported PSP BIOS checksums and show readiness in Parent settings
  - [x] Verify that Ubuntu RetroArch can launch the upstream Linux x86-64 PCSX ReARMed core with a CHD, the supported PSP BIOS and a private save directory
  - [x] Offer the RetroArch package in the Parent installer and report whether the reviewed PCSX ReARMed core is available
  - [ ] Add a maintained one-click delivery route for the reviewed PCSX ReARMed core, with artifact verification and explicit versioning. Evaluate Beetle PSX or DuckStation if needed for game compatibility
  - [x] Discover single-disc CHDs, enforce per-child approval and verify the firmware, disc and pre-provisioned core before launch
  - [ ] Add CUE/BIN support with every referenced track inside the approved source. Invalidate approval when a disc component changes
  - [ ] Keep memory cards private per child and game. Verify launch, controls and memory-card persistence on the desktop matrix and the physical Linux test laptop
  - [x] Import M3U sets of CHD discs with a single approval, including Miyoo playlists whose entries are resolved within the playlist folder
  - [ ] Verify a disc change requested during gameplay and memory-card persistence on the desktop matrix and the physical Linux test laptop
- [ ] Add save backup and removal controls
- [ ] Compare RetroArch cores for the existing cartridge systems. Switch a system only after verifying that existing game approvals and saves still work or have a tested migration.
- [ ] Add a short local device check in Parent settings that recommends optional systems through the Wii U and PS3 era
  - [ ] Before installation, check each candidate emulator's documented requirements for CPU architecture and instruction sets, memory, graphics API and driver capabilities. Detect whether the launcher can install the emulator on the current Linux distribution separately.
  - [ ] Use bounded, locally generated test workloads that require no family game files. When the emulator is available, measure emulation speed and frame pacing with a representative workload and record the tested settings.
  - [ ] Report recommended, limited, untested and incompatible separately. Explain the result beside the install button. Disable installation for a confirmed hardware incompatibility or unavailable install route, with a distinct explanation for each. Keep the install action available when performance is unknown and a reviewed install route exists.
  - [ ] Scope results to the device, system, RetroArch core or standalone emulator version, and tested settings. Allow a rerun after a driver, core or emulator update. Keep per-game compatibility separate from the device result.
- [ ] Qualify optional systems in groups after PS1
  - [ ] Earlier cartridges and arcade games including Atari 2600/5200/7800, ColecoVision, Intellivision, SG-1000, Mega Drive, PC Engine, Neo Geo and selected arcade boards. Review disc add-ons such as Sega CD and PC Engine CD separately.
  - [ ] Earlier handhelds including Atari Lynx, Neo Geo Pocket / Color, WonderSwan / Color, Nintendo DS and PSP. Evaluate Nintendo 3DS and PlayStation Vita as later handhelds in scope.
  - [ ] Nintendo 64, Saturn and Dreamcast. Qualify firmware, disc formats, controls and save isolation for each system.
  - [ ] PlayStation 2, GameCube, Wii and original Xbox. Test [PCSX2](https://pcsx2.net/docs/setup/requirements/) first for PS2 on the physical Linux laptop and compare performance, input and fullscreen before selection. Review [Dolphin](https://dolphin-emu.org/docs/faq/) and [xemu](https://xemu.app/) for the other systems, including Wii motion input and Xbox firmware setup.
  - [ ] Wii U and PlayStation 3. Qualify [Cemu](https://cemu.info/faq.html) and [RPCS3](https://github.com/RPCS3/rpcs3), including firmware or game installation where required and per-game compatibility guidance. Evaluate [Xenia](https://github.com/xenia-project/xenia) for Xbox 360 in the same era once a Linux installation and launch path passes review.
  - [ ] For each new system, qualify the Parent install flow, supported game formats, required user-supplied files, child approvals, private saves and desktop acceptance before offering it in RetroGameCorner.
- [x] Support bounded single-ROM ZIP archives from handheld game libraries
- [ ] Verify gamepad/keyboard input, actual fullscreen, a reachable close control and return to the launcher for each supported emulator

#### Living-room foundations

- [x] Add optional standard gamepad and keyboard-style remote navigation on Home and in the media library, with modal focus boundaries
- [ ] Verify standard gamepads and physical remotes on the release desktop matrix
- [x] Let parents add bounded local media roots without exposing filesystem paths to the child-facing API
- [x] Refresh the media library when a configured folder disappears or returns, remove stale cards and covers, and preserve favorites
- [ ] Verify physical removable-drive eject and remount behavior on the release desktop matrix
- [ ] Add optional child-friendly folders and categories without recommendations, streaks, or engagement scoring
- [ ] Recover cleanly from suspend, resume, display hotplug, and temporary audio-device loss
- [ ] Define and measure cold-start, idle-memory, and low-powered-device performance budgets

## v1.0.0 — Long-term Stable

### Packaging and downstream distribution

- [ ] Produce a first-party Debian package for Ubuntu, Linux Mint, and Zorin OS
  - [ ] Add a package-managed runtime mode that leaves updates to the system package manager
  - [ ] Publish through a signed first-party APT repository or Ubuntu PPA
- [ ] Produce first-party RPM packages and evaluate signed COPR or Open Build Service distribution after the Debian package layout is stable
- [ ] Publish an Arch Linux AUR recipe after the Debian package layout is stable
- [ ] Publish the Cozy Kids Launcher itself in the Snap Store
  - [ ] Build and test an appropriate confinement/runtime model, including host-app launching, process ownership and store approval requirements
- [ ] Publish the Cozy Kids Launcher itself as a Flatpak on Flathub
  - [ ] Prototype the sandbox/host-launch boundary and preserve the required Parent, app and media behavior
  - [ ] Prepare the Flatpak manifest, app metadata, package-managed update behavior and submission/review workflow
- [ ] Pursue official Debian/Ubuntu and Arch repository adoption only as a long-term downstream-maintainer goal, not a release commitment

Packaging therefore proceeds in the practical order DEB/APT, RPM repositories,
AUR, then Snap Store/Flathub preparation. Store publication distributes the
launcher itself; installed-app discovery and package-provider support are
separate capabilities. Every package format must preserve
local configuration, desktop integration, host-app launching, and the
stable-`main` updater contract.

### Stability contract

- [ ] Publish a compatibility policy for configuration schemas, the loopback API, package migrations, and update channels
- [ ] Complete a documented threat model and security review of Parent authentication, local HTTP boundaries, imports, updates, and process launching
- [ ] Verify clean install, script-to-package migration, upgrade, rollback, backup restore, and uninstall paths on every supported distribution
- [ ] Complete manual screen-reader coverage alongside keyboard, touch, reduced-motion, high-contrast, and low-resolution testing
- [ ] Make release artifacts and repository metadata reproducible, signed where applicable, and independently verifiable
- [ ] Document a sustainable translation, accessibility, security-reporting, and downstream-packaging contribution workflow

## Release standard

A work-item checkbox is complete when its stated scope is implemented and:

- automated tests or an explicit manual test cover it;
- every enabled language has aligned behavior or an explicit, tested fallback;
- old configurations migrate safely;
- diagnostics do not expose private family data;
- relevant documentation and screenshots are updated.

A release milestone additionally requires its open distribution/desktop gates
and the full gate in [RELEASING.md](RELEASING.md). A checked implementation task
does not substitute for an unperformed release or physical-device acceptance.

- [ ] Run the release candidate end to end on the physical Linux test laptop and record real keyboard and gamepad input, including RetroGameCorner, alongside the VM matrix.
