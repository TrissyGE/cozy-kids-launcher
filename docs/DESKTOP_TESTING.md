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
- Reconnect the gamepad and removable game storage and check that the launcher recovers without restarting.

## Release evidence

Attach the three primary `report.json` files to the release-candidate test notes or CI run. Record the exact commit, distribution version, desktop version, session type, browser version, display topology, and any compositor-specific workaround beside the reports.

Do not mark the roadmap item complete from WSLg results or from a report whose final `outcome` is not `passed`. Wayland reports retain `manual-required` annotations for compositor observations, but those are accepted only after the corresponding manual checks pass. Fix defects on a topic branch, restore the clean VM snapshot, and repeat the affected row.
