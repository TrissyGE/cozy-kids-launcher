# Linux desktop smoke matrix

The release desktop matrix must be run in complete Linux desktop sessions. WSLg, a container, Xvfb, or a headless CI runner can validate parts of the launcher, but cannot prove login autostart, compositor focus, overlay stacking, shortcuts, or kiosk behavior.

## Required environments

Use disposable virtual machines or dedicated test devices. The minimum release evidence is one passing report from each primary row:

| Desktop | Primary session | Browser and launch mode | Additional coverage |
| --- | --- | --- | --- |
| Ubuntu GNOME | Wayland | Firefox snap, `kiosk` | Repeat on X11 before claiming full X11 support |
| KDE Plasma | Wayland | Chromium family, `fullscreen` | Repeat on X11 before claiming full X11 support |
| XFCE | X11 | Chromium family, `kiosk` | Wayland is not part of the current XFCE release target |

The desktop and session must match the values passed to the harness. The script deliberately refuses WSL and mismatched `XDG_CURRENT_DESKTOP` or `XDG_SESSION_TYPE` values.

## VM preparation

Take a clean VM snapshot and use a disposable, non-administrator desktop user. Install the project runtime dependencies plus:

- a supported Firefox- or Chromium-family browser;
- `python3-tk` for the app overlay;
- `desktop-file-utils` for shortcut validation;
- `wmctrl` and `xdotool` for X11 window checks.

Clone the repository and check out the exact release candidate commit. Do not test a moving branch after recording the commit ID.

## Automated in-session run

Run the matching command from a terminal opened inside the graphical session:

```bash
python3 scripts/linux/desktop_smoke.py --desktop gnome --session wayland
python3 scripts/linux/desktop_smoke.py --desktop kde --session wayland
python3 scripts/linux/desktop_smoke.py --desktop xfce --session x11
```

Pass `--launch-mode window`, `--launch-mode fullscreen`, or
`--launch-mode kiosk` to install and verify that exact browser mode. The default
is `window`. See [DISPLAY_BEHAVIOR.md](DISPLAY_BEHAVIOR.md) for the assertions
that are automated on X11 and the compositor observations that remain manual on
Wayland.

The script uses a temporary home directory and does not modify the VM user's normal launcher profile. It checks:

For a Firefox snap, that temporary directory lives under the test user's
`~/snap/firefox/common/` so confinement permits access. It is removed after the
run, including its isolated launcher/browser profiles.

1. an isolated install of the current checkout;
2. syntax and presence of autostart, application-menu, and desktop entries;
3. startup of the local server and its owned browser;
4. rejection of a duplicate launcher instance;
5. the owned browser command uses exactly the selected window, fullscreen, or
   kiosk switch;
6. X11 launcher-window visibility where the window manager exposes it;
7. launch of an owned child process and the Tk overlay;
8. on X11, overlay-close termination and focus recovery to the known launcher
   window;
9. a clean Parent exit, final lifecycle state, and complete process cleanup.

Logs, lifecycle evidence, and the privacy-safe report are written below:

```text
.test-artifacts/desktop-matrix/<desktop>-<session>-<launch-mode>/
```

An automated run ends with `automation-passed-manual-pending`. That is useful diagnostic evidence, but it is not a completed desktop result.

Use `--catalog-app kturtle` or another existing KDE fullscreen recommendation
to exercise a real installed app instead of the sleeping fixture. See
[CATALOG_FULLSCREEN.md](CATALOG_FULLSCREEN.md) for the separate X11/XWayland
assertions and additional lesson/input acceptance requirement.

## Manual desktop checks

Restore the VM snapshot and install normally into the disposable user's actual
home with the browser and launch mode assigned to that primary row:

```bash
bash scripts/install.sh --lang en --browser firefox --launch-mode kiosk --force
```

The three primary rows collectively cover both kiosk and fullscreen behavior.
An individual report verifies only its recorded `launchMode`; it is not evidence
for a second mode that was not used during that run. Enable
`--install-shutdown-helper` only in a disposable VM snapshot where a real
poweroff is safe. Verify all six observations:

1. a fresh login starts exactly one launcher;
2. the selected browser mode fits the display without a black screen;
3. the close overlay remains reachable above a launched child app;
4. closing the child app returns focus to the launcher;
5. the desktop shortcut reopens the launcher without creating a duplicate instance;
6. the optional shutdown helper performs a clean VM poweroff through the desktop's expected authorization path.

Then repeat the isolated harness with `--interactive` and record the observations when prompted:

```bash
python3 scripts/linux/desktop_smoke.py \
  --desktop gnome \
  --session wayland \
  --launch-mode kiosk \
  --interactive
```

Answer `y` only for an observation performed on the exact VM, session, and commit under test. Answer `n` for a failure and `s` to leave it pending. The final report outcome becomes `passed` only when automation and all six observations pass.

### RetroGameCorner

For each supported emulator, approve a test game in Parent settings and open it
from the child's RetroGameCorner library on each primary desktop. Record the
following separately:

- The emulator window enters fullscreen and the visible game image scales to the display while preserving its aspect ratio.
- A gameplay action responds to the keyboard and a physical gamepad.
- The close overlay can be clicked and the launcher regains focus after the emulator exits.
- For PS1 CUE/BIN, include a disc with a separate audio BIN. Check gameplay audio and confirm that replacing any track makes the old approval unavailable.
- For a PS1 multi-disc set, reach a disc change in the game. Open the virtual tray with F9, select the next disc with F10 and close the tray with F9. Verify play continues and the same memory card is available after exiting and relaunching the set.

Use a redistributable test ROM for shared screenshots. When verifying ZIP
support, repeat a failing ZIP launch with the same ROM as a loose file.
With a disposable child profile, verify that the Parent save ZIP contains the
emulator's saved files and that confirmed deletion clears only that game's
local saves. Check keyboard and gamepad focus when filtering the library by
console. Record the device check's reported graphics APIs separately from
emulator performance, especially when the VM uses software graphics.

#### PS1 CUE/BIN validation, 2026-11-03

Candidate `2b96af8` ran on an Ubuntu 24.04.4 LTS VirtualBox guest with
RetroArch 1.18.0 and the reviewed PCSX ReARMed r26 core. Each row confirmed
local core import, CUE/BIN approval, fullscreen, the keyboard screenshot
shortcut, overlay close, a memory-card write, and reuse of the card on
relaunch. Modifying the BIN made the old approval unavailable.

| Desktop session | Browser | Result |
| --- | --- | --- |
| GNOME 46 Wayland | Firefox Snap 154.0.1, kiosk | Passed after waiting for the previous overlay to close before relaunch |
| Plasma 5.27.12 Wayland | Chrome 152.0.7977.64, fullscreen | Passed |
| XFCE 4.18.3 X11 | Chrome 152.0.7977.64, kiosk | Passed with LightDM after the guest's GDM X11 session repeatedly exited |

The candidate keeps RetroArch audio writes nonblocking. A stalled PulseAudio
sink reproduced a black screen and blocked shutdown before this change.
Actual gameplay controls, audible output, and an in-game request for another
disc still require separate validation.

## System package lifecycle and desktop pilot, 2026-11-05

The package candidate uses the same Ubuntu 24.04.4 disposable guest as the
RetroGameCorner matrix. The package runtime is read-only to the family user.
The final native probes used the runtime from `fc2949f`, packaged as
`0.6.0+package4-1`. The `.deb` SHA-256 was
`bcdf0a1c1d7b1f1e880f65d8c3540137c7b46c9e3c5b7b6512ed645de57ada27`.
The lifecycle rows below refer to that package candidate. The later
RetroGameCorner preflight increment has separate evidence below.
Actual dpkg install, upgrade and downgrade between two candidate package
revisions passed. A real script installation was migrated with its exact
configuration retained. The installed server restored a configuration
through the Parent backup API. Purge retained the profile and a private
save fixture; reinstall resumed that state. Reverse migration restored the
original local launcher and update ownership. These checks exercise the
current schema; they do not establish rollback across a future schema change.

The installed-package probe is `scripts/linux/system_package_smoke.py`.
It initializes a disposable home, uses the package's actual server and browser
launcher, checks package update ownership, starts KTurtle from the catalog,
observes its owned fullscreen window, clicks the overlay and checks cleanup.
The package's installed-runtime API probe also runs without a display in CI.

| Session and browser | Automated installed-package checks |
| --- | --- |
| Plasma 5.27.12 Wayland, Chrome 152 fullscreen | Passed |
| GNOME 46 Wayland, Firefox Snap 154 kiosk | Complete probe passed in a fresh user session; earlier probes after desktop switches intermittently returned HTTP 503 during KTurtle fullscreen startup |
| XFCE 4.18.3 X11, Chrome 152 kiosk | Passed with LightDM |

These reports retain `automation-passed-manual-pending`. The GNOME failure
recurred after desktop switches while sessions from the previous desktop
were still present. Restoring the clean snapshot and starting a fresh GNOME
user session passed. A diagnostic supervisor also passed; its timing changed,
so it does not establish the cause of the failure. Keep this startup issue
open until it is explained. The XFCE probe now waits for the owned Tk overlay
record and its first window placement before clicking; the settled probe
passed. Meaningful physical input, visible native Wayland focus and
stacking, fresh-login autostart, Linux Mint and Zorin lifecycle acceptance
remain open. [Package building and migration](PACKAGING.md) describe the
commands and update/uninstall boundaries.

The package's opt-in systemd user service was also exercised in the actual
unused GNOME account. Enable, graphical start with an owned kiosk browser,
live status, manual stop, owned-process cleanup and disable passed. The
`--user-service` flag requires an unused disposable account because systemd
uses that account's actual home. It is separate from the temporary-home
standalone probe. Fresh-login autostart remains a manual gate.

Child folder browser checks cover real save/reload, hidden tiles, folder
deletion without deleting apps, keyboard back/focus recovery, a synthetic
standard gamepad, media-return state, and the five enabled languages at
800×600. The physical gamepad gate below still applies.

### Sourced RetroGameCorner preflight, 2026-11-05

The `f7c6879` runtime, packaged as `0.6.0+package5-1`, produced complete
eight-system capability reports in Plasma Wayland, a fresh GNOME Wayland
user session, and XFCE X11 with LightDM. The `.deb` SHA-256 was
`7b95a58680e3b19f3f9cba173cb87c213bf2c52b956cbaac05f17e3c5edee6c2`.
The guest reported x86-64 and 5.8 GiB of usable RAM. Accelerated graphics
capabilities stayed unknown; the report did not turn software rendering
into a hardware-performance pass. PS2 was limited by memory guidance and
unqualified candidate installation routes stayed unavailable.

The real installed-package API probe also checked the requirements resource
and all eight report rows. Browser tests exercised each enabled language at
800×600, source/detail expansion, a fresh check before emulator installation,
confirmed incompatibility, unknown performance with a reviewed route, and
discarding a late result after Parent settings closed. Requirement/parser
tests cover alternative renderers, missing extensions, package/core/rule
version changes and unknown probe results. These are preflight checks and
do not measure gameplay, frame pacing or candidate driver correctness.

## Generated PS1 workload pilot — 2026-11-05

The installed `0.6.0+benchmark2` test package (based on `develop` `4163cc2`
plus the local benchmark increment) has SHA-256
`2d5c1d69304491695ea31528636fae87328748bd7dadaae3da677855868a066e`.
On the disposable Ubuntu 24.04.4 VM with one vCPU and 5907 MiB RAM,
`retro_benchmark_smoke.py` passed in each actual desktop session. Reports
record runtime file hashes, workload/core hashes and exact settings.

| Session | Real HTTP/core/lifecycle probe | Unpaced workload FPS | 95th-percentile call time | Workload result |
| --- | --- | ---: | ---: | --- |
| GNOME Wayland | Passed | 294.90 | 6.4315 ms | Within provisional budget |
| KDE Plasma Wayland | Passed | 138.97 | 22.1226 ms | Limited by call-time percentile |
| XFCE X11 | Passed | 252.82 | 7.1712 ms | Within provisional budget |

All three validated 240 frames after warmup, RAM progress and changing images,
then checked private scope attachment, restart, removal and real-worker cancel.
No game or BIOS was supplied. The package's ordinary-user runtime/API smoke
also passed, including the missing-core refusal and new static assets.
These single observations were collected with varying host load and must not
be used to rank desktops or predict games. A successful probe can correctly
produce a `limited` workload result, as the KDE sample shows.

The Parent browser fixture separately covers lost replies, cancel, removal,
stale scope, late acknowledgements and five languages at 800×600. This pilot
does not test visible desktop pacing, audio or physical input. See
[RETRO_BENCHMARK.md](RETRO_BENCHMARK.md) for the complete measurement boundary.

## Physical Linux test laptop

Run the exact release candidate on the test laptop before publishing v0.8.
Record the laptop model, Linux distribution, desktop session, browser mode,
controller model and candidate commit. Use a disposable user or test profile.

### First-launch and idle-memory budgets

Run the desktop smoke with `--performance-only` three times per candidate on the
same low-powered device. Each run creates a fresh browser profile. Keep the
same desktop and browser versions, connect AC power, and close unrelated
applications. A fresh profile measures first launch with the current OS
caches. For cold-boot evidence, repeat after reboot and label that sample
separately.

Record median server-ready time, browser process startup time, and X11 window
visibility time where observable. Browser startup on Wayland measures the
browser executable, so record the visible launcher separately. Idle memory
uses three samples of the launcher, server, and owned browser process trees
from Linux proportional set size (PSS) after a 15-second settling period.
Missing process readings mark the
sample incomplete. Initial investigation budgets for a 4 GiB device are
5 s for server readiness, 15 s for browser startup, and 450 MiB idle PSS.
These are provisional thresholds for comparing candidates on the test laptop.

The first pilot on Ubuntu 24.04.4 in VirtualBox used one logical CPU,
5907 MiB of guest memory, Plasma Wayland and Chrome 152 fullscreen.
It measured 932 ms for server readiness, 1589 ms for the browser
executable, and 514 MiB median idle PSS across three complete samples.
The memory result exceeded the provisional budget. This run used the
`53c99ea` launcher and a fresh browser profile. It provides an initial
comparison point for the physical device.

- Verify first setup, normal relaunch, Parent PIN, time limits and profile isolation.
- Run a Parent-authorized app installation and exercise the updater with the candidate release channel.
- With a physical gamepad, navigate Home and the RetroGameCorner library. Confirm that Parent controls stay behind the PIN.
- For each supported emulator, confirm visible fullscreen, gameplay input from the keyboard and controller, save persistence, the close overlay and return to the launcher.
- Repeat the local PS1 short test with other programs closed; retain the device/core/settings scope and compare only repeated runs under comparable power and thermal conditions. Confirm real game performance separately.
- Reconnect the gamepad and removable game storage and check that the launcher recovers without restarting.

## Release evidence

Attach the three primary `report.json` files to the release-candidate test notes or CI run. Record the exact commit, distribution version, desktop version, session type, browser version, display topology, and any compositor-specific workaround beside the reports.

Do not mark the roadmap item complete from WSLg results or from a report whose final `outcome` is not `passed`. Wayland reports retain `manual-required` annotations for compositor observations, but those are accepted only after the corresponding manual checks pass. Fix defects on a topic branch, restore the clean VM snapshot, and repeat the affected row.
