# Roadmap

Cozy Kids Launcher is a lightweight, local-first family console for Linux.
Children get a clear home screen. Parents manage apps, media, accessibility,
and time on the device.

## Current execution order

[v0.8.0](https://github.com/TrissyGE/cozy-kids-launcher/releases/tag/v0.8.0)
is the stable baseline. It shipped the searchable Parent app store, daily
allowances, child folders, five interface languages, and RetroGameCorner.
The release candidate was accepted on the physical Linux laptop and in all
three desktop VMs. [Desktop evidence](DESKTOP_TESTING.md#v08-desktop-vm-acceptance)

| Target | First outcome | Readiness |
| --- | --- | --- |
| [v0.8.1](#v081--everyday-use) | Simpler Parent settings, faster game approval, and focused desktop fixes | Existing UI, local data, and test environments |
| [v0.8.5](#v085--desktop-and-package-qualification) | DEB pilot, additional provider coverage, and repeatable physical-device evidence | Distribution snapshots, current package builds, and the test laptop |
| [v0.9.0](#v090--retrogamecorner-expansion) | Qualify new systems in small groups, starting with candidates that fit the existing library | Reviewed emulator routes, preserved saves, and real gameplay evidence |
| [v1.0.0](#v100--stable-support) | Document and verify the support, accessibility, and recovery contract | Supported combinations explicitly defined and tested |
| [Longer-term work](#longer-term-work) | Newer consoles, additional distribution channels, and RTL languages | Hardware, sandbox, signing, or upstream review |

Work in coherent feature blocks on topic branches targeting `develop`. Use
focused checks while iterating and repeat the affected desktop journeys once the
block is ready. Each release candidate follows the release standard below.
PS1 promotion and new app or emulator mappings advance individually when their
acceptance evidence is ready. [Branching](BRANCHING.md)

## v0.8.1 — Everyday use

### Parent settings

- [x] **Make frequently used controls easy to reach.** Show the active child
  consistently in the editor. Keep save, back, and confirmation actions
  reachable at 800×600 across all five languages. Cover long labels, zoom,
  keyboard order, and focus return in Screen Time, Apps & Media, and
  RetroGameCorner.
- [x] **Explain the current screen-time rules in one place.** Show today's
  used and remaining allowance, extra minutes already granted, and the next
  applicable schedule restriction for the active child. Use the existing
  local allowance and schedule state, including disabled rules and midnight
  rollover. Keep Parent-authorized extra time available with a custom duration.
- [x] **Preview a backup before restoring it.** Show its date, schema, profile
  count, and which settings would be replaced. Report incompatible backups
  before confirmation. Exercise cancelled and failed restores and confirm that
  the previous family configuration is recoverable.

### RetroGameCorner

- [x] **Approve several games for the active child.** Add Parent search,
  console filtering, selected-title counts, and an explicit confirmation.
  Reuse the per-game approval checks and report individual failures when a
  source disappears or a file changes during the operation.
- [x] **Remember the child's library view.** Keep the selected console or
  grouping mode across library visits for that profile. Offer an obvious
  return to all games and handle a missing console or empty list gracefully
  after a drive is removed or a profile is switched.

### Focused desktop acceptance

- [ ] **Close the known installation gaps on available Ubuntu and Zorin
  sessions.** Exercise consent, a cancelled system authorization, a failed
  install, and a successful retry through the Parent app store. Check that
  installation status and the offer to add a tile reflect the result on APT
  and APTcc. Use the existing Zorin success path as the baseline.
  [Provider scope](PACKAGE_PROVIDERS.md) · [Zorin qualification](https://github.com/TrissyGE/cozy-kids-launcher/pull/100)
  - [x] Verify a fresh Blinken package review on Ubuntu and Zorin, and confirm
    that a real PackageKit authorization denial on Ubuntu reports an error.
  - [ ] Finish graphical authorization cancellation, failure, and successful
    retry on both target desktops.
- [ ] **Finish the targeted TuxMath fullscreen checks.** Exercise a real game,
  usable input, the close overlay, and return to the fullscreen child launcher
  on GNOME Wayland and XFCE X11. Include physical keyboard and touch where
  available and retain the prior Plasma Wayland result for its tested revision.
  [Fullscreen evidence](CATALOG_FULLSCREEN.md)
  - [x] Confirm owned fullscreen and overlay close on Plasma Wayland and
    XFCE X11, and exercise a real number-typing round with XTest on XFCE.
  - [ ] Resolve the GNOME Wayland fullscreen timeout and finish the physical
    input check.

## v0.8.5 — Desktop and package qualification

### Visual refresh

- [ ] **Give Cozy Kids a more distinct, modern visual identity.** Start with
  a consistent type scale, spacing, icon style, and clearer focus and action
  states. Apply them to Home, Parent settings, and the media and retro
  libraries, using the large tiles and illustrated worlds as the foundation.
  Review the resulting screens at 800×600 and on a living-room display,
  including large text, high contrast, keyboard, and controller use. Refresh
  the README and website gallery from the finished launcher.

### Native packages and catalog

- [ ] **Qualify the first-party DEB on Mint and Zorin.** Repeat clean first
  start, script migration, upgrade, rollback, backup restore, uninstall, and
  reinstall. Use the reproducible build and the passing Ubuntu package
  lifecycle as the starting point. Confirm the optional user service and
  desktop entry on the affected sessions, including the first launch after
  login. [Package scope](PACKAGING.md)
- [ ] **Offer a first-party DEB pilot through a release candidate.** Decide how
  to publish and verify candidate packages after the target lifecycles pass.
  Document which installs the system package manager owns and how a family
  returns to the script installation. Signed APT repository or PPA publication
  is a separate milestone.
- [ ] **Qualify a small set of native catalog apps across providers.** Finish
  the outstanding Linux Mint authorization and failure checks. Reuse the
  existing Fedora, openSUSE, and Arch container probes, then exercise the
  same catalog journeys on target desktops. Expand to derivatives after the
  release report identifies the tested combinations. Audit the remaining
  native apps in batches using the fullscreen contract, including a GNOME
  X11 session where available.
  [Native package testing](NATIVE_PACKAGE_TESTING.md)
- [ ] **Add the next reviewed user-scoped Flathub app.** Choose an app that
  benefits families and has a supportable permission profile. Verify the exact
  app/runtime review, install, launch, return, and source switching. The
  initial Tux Paint mapping is the reference.
  [App-store scope](APP_STORE.md)

### Living Room and physical coverage

- [ ] **Finish the supported-emulator input and return matrix.** Record actual
  fullscreen, keyboard and controller gameplay, audible output, save
  persistence, close-overlay reachability, and launcher return for mGBA
  and Mednafen. Cover a standard controller and a
  keyboard-style remote on Home and in the libraries. The v0.8 laptop run
  already exercised physical input and Game Boy save persistence.
- [ ] **Finish the PS1 preview acceptance.** Verify a durable, reviewed source
  for the pinned core, real gameplay with audio and private saves on the test
  laptop, and in-game disc changes with memory-card persistence on the desktop
  matrix. Evaluate Beetle PSX or DuckStation if the current core cannot meet
  the compatibility or sourcing requirements.
  [PS1 test scope](RETRO_BENCHMARK.md)
- [ ] **Qualify reconnect and recovery.** Use the recorded Zorin suspend and
  Miyoo remount checks as starting evidence. Cover removable storage eject
  and remount, controller reconnect, suspend/resume with an app active,
  monitor hotplug, and audio-device loss/reconnection on the applicable
  desktop sessions. Confirm approved items, saves, focus, and the close
  control recover consistently.
- [ ] **Establish complete low-powered baselines.** Repeat cold-start and idle
  PSS measurements on the physical laptop with the same browser, profile,
  and conditions. Record a complete series, investigate the main idle-memory
  cost, and verify improvements against the provisional budget.
  [Performance procedure](DESKTOP_TESTING.md#first-launch-and-idle-memory-budgets)
- [ ] **Repeat a shared physical-language pass.** On the laptop, check long
  labels, keyboard and touch navigation, localized dates and numbers, and
  installed speech voices and fallback for all five supported languages.
  Keep the locale registry and the language contribution guide current.
  [Localization](LOCALIZATION.md)

## v0.9.0 — RetroGameCorner expansion

Keep emulator setup in Parent settings and use the shared graphical installation
flow. Prefer RetroArch where a reviewed core matches or exceeds the standalone
option in compatibility, performance, input, and fullscreen/return. Use
standalone emulators where they offer the better supported path. Families
provide their own games and any required firmware.

- [ ] **Add a small group of earlier cartridge systems first.** Evaluate
  Mega Drive, PC Engine, Atari and Sega cartridge systems, then additional
  older handhelds such as Neo Geo Pocket, WonderSwan, and Lynx. Keep ColecoVision,
  Intellivision, Neo Geo and selected arcade boards as separate candidates when
  firmware or board-specific formats require more work. Review Sega CD and
  PC Engine CD separately.
- [ ] **Compare RetroArch cores for the existing cartridge systems.** Qualify
  each switch using real input, performance, and desktop behavior. Preserve
  prior approvals, saves, and save states where compatible. Provide a tested
  migration or a clear fallback to the existing emulator where formats differ.
- [ ] **Make device and install decisions understandable.** Show each
  reviewed emulator's CPU, memory, graphics API, and driver checks beside its
  separately verified install route. Explain whether performance is supported
  by a tested workload, limited, incompatible, or untested. Disable installation
  for confirmed incompatibility or an unavailable route and show the reason.
  Measure with bounded, locally generated workloads where supported. Scope
  results to device, driver, emulator/core, settings, and workload, and offer
  a rerun when the scope changes. Distinguish PS1 workload throughput from
  visible gameplay performance.
  [Device preflight](RETRO_DEVICE.md)
- [ ] **Pilot later families one at a time.** Assess Nintendo 64, Saturn,
  Dreamcast, Nintendo DS, and PSP after the cartridge and PS1 acceptance.
  Start PS2 evaluation with [PCSX2](https://pcsx2.net/docs/setup/requirements/)
  on the physical laptop. Qualify GameCube and Wii with
  [Dolphin](https://dolphin-emu.org/docs/faq/) and original Xbox with
  [xemu](https://xemu.app/) as independent candidates. Include dual-screen,
  motion control, or firmware setup where the system requires it.

A console becomes available after its package route, supported file formats,
required firmware, parent approval, per-child saves, gameplay input, and
desktop return pass real tests. Performance reports cover the tested setup
and keep game compatibility separate.

## v1.0.0 — Stable support

- [ ] **Define and verify the support matrix.** Publish the distribution,
  desktop, browser, package provider, and emulator combinations backed by
  evidence. Complete install, upgrade, rollback, backup restore, uninstall,
  and script/package migration on each advertised installation route. Extend
  coverage to additional combinations when tests and maintenance are available.
- [ ] **Complete the documented threat model and defensive review.** Cover
  Parent authentication, the loopback API, config and file imports, updates,
  package authorization, and ownership of launched processes. Build on the
  existing local trust boundaries and compatibility policy.
  [Compatibility](COMPATIBILITY.md)
- [ ] **Finish manual accessibility acceptance.** Verify screen-reader
  announcements and focus, keyboard and touch journeys, reduced motion, high
  contrast, and low resolution. Publish the tested tools and flows.
- [ ] **Qualify signed package publication.** Choose a first-party signed APT
  repository or PPA after the DEB pilot. Extend the existing reproducible
  release and checksum process to published package artifacts and signed
  repository metadata. Verify the update and rollback paths from a clean client.

## Longer-term work

- [ ] **Wii U / PlayStation 3 and later handhelds.** Review current RPCS3 and
  Cemu hardware and driver requirements, supported install routes, performance,
  parent-supplied firmware and game setup, input, and per-game compatibility. Evaluate
  Nintendo 3DS and PlayStation Vita independently. Evaluate Xbox 360 through
  Xenia after a viable Linux installation and launch path is available.
- [ ] **Complex package maintenance.** Qualify RPM update/removal only after
  provider restrictions are reliable at execution time and real version-to-version
  tests and graphical acceptance pass. Review system-wide Flatpak and app
  update/removal separately from user-scoped installation.
- [ ] **Distribute the launcher in more formats.** Evaluate first-party RPM
  builds with signed COPR or Open Build Service, then an Arch AUR recipe after
  the DEB layout is established. For Snap Store and Flathub, prototype
  distribution of the launcher itself and verify sandbox/host-app launching,
  process ownership, permissions, update behavior, and store review requirements.
  Treat official Debian/Ubuntu and Arch archive adoption as a downstream
  maintainer effort.
- [ ] **Add a reviewed RTL language.** Extend the existing registry and RTL
  layout coverage with Arabic or Hebrew. Validate translations, mirrored
  controls, mixed-direction text, and physical input before enabling the pack.
- [ ] **Revisit KStars and Stellarium.** Qualify both separately after resolving
  the observed KDE Wayland startup and GNOME Wayland launch/input failures.
  Preserve meaningful use, a reachable close control, and return to the launcher.
  [Catalog evidence](CATALOG_FULLSCREEN.md#kolourpaint-and-kgeography)

## Published milestones

The [changelog](../CHANGELOG.md) carries the detailed release history. The
checked items below record shipped work and accepted evidence.

### v0.4.1 — Project polish

- [x] Rebuild the project landing page and screenshot workflow, document the
  branch model, and improve installer and website-tile editor behavior.

### v0.5.0 — Solid Core

- [x] Split the frontend and server, migrate versioned configs, add private
  diagnostics and backups, and supervise launcher/app lifecycle.
- [x] Add browser and desktop smoke coverage and the sectioned Parent editor
  with search, bulk actions, accessibility options, and reusable controls.

### v0.6.0 — Family Edition & Delight

- [x] Ship separate child profiles, guided setup, app and weekly schedules,
  local opt-in activity, and browser navigation boundaries.
- [x] Ship the local cover library with favorites and per-profile resume,
  illustrated themes, optional feedback, and accessibility presets.

### v0.8.0 — Platform & Living Room

- [x] Ship the searchable Parent app store, native PackageKit routes including
  Zorin APTcc, the reviewed user Flathub route for Tux Paint, and restart
  recovery that preserves consent boundaries.
- [x] Ship German, English, Spanish, French, and Italian with a shared locale
  registry and generated-resource checks. Publish the website in the same five
  languages. [Translation guide](LOCALIZATION.md) · [Website](https://cozykids.org/)
- [x] Ship daily per-child budgets, customizable extra time, child profile
  duplication, folders, and optional controller/remote navigation.
- [x] Ship RetroGameCorner with approved local cartridge games, adjacent Miyoo
  covers, opt-in Libretro artwork, console grouping, and private save controls.
- [x] Ship the optional PS1 preview with reviewed PCSX ReARMed, parent-supplied
  firmware, CHD, CUE/BIN and M3U support, local hardware preflight, and a scoped
  PS1 workload test. [Device scope](RETRO_DEVICE.md)
- [x] Produce a reproducible DEB build and test the Ubuntu package lifecycle.
  Ship stable/preview archive updates and verify the published candidate
  upgrade from v0.6.0. [Package evidence](DESKTOP_TESTING.md#system-package-lifecycle-and-desktop-pilot-2026-11-05)
- [x] Accept the release candidate on the three desktop VMs and the physical
  Linux laptop. [VM evidence](DESKTOP_TESTING.md#v08-desktop-vm-acceptance) ·
  [Laptop evidence](DESKTOP_TESTING.md#v08-laptop-acceptance)

## Release standard

### Fullscreen product contract

The installer defaults to chrome-free kiosk mode. Check that mode in graphical
acceptance. A catalog app or emulator passes when it reaches fullscreen,
accepts meaningful input, offers a reachable close control, and returns to the
launcher. The explicit window mode remains available for families who prefer it.
[Display behavior](DISPLAY_BEHAVIOR.md)

A checked task records the implemented scope and its automated or manual
evidence. Verify affected languages, migrations, and privacy-safe diagnostics.
Update relevant docs and screenshots. Record broader distribution and device
acceptance as separate tasks with their own evidence.

Release candidates follow [RELEASING.md](RELEASING.md) and the required
[desktop matrix](DESKTOP_TESTING.md#required-environments)
of GNOME Wayland, KDE Plasma Wayland, and XFCE X11. Use the physical Linux
laptop for affected controller, audio, storage, and display behavior.
Record the exact candidate and tested environment. Preserve family data and
the stable-`main` updater contract.
