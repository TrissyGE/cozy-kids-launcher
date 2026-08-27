# Linux desktop smoke matrix

The release desktop matrix must be run in complete Linux desktop sessions. WSLg, a container, Xvfb, or a headless CI runner can validate parts of the launcher, but cannot prove login autostart, compositor focus, overlay stacking, shortcuts, or kiosk behavior.

## Required environments

Use disposable virtual machines or dedicated test devices. The minimum v0.5.0 evidence is one passing report from each primary row:

| Desktop | Primary session | Additional coverage |
| --- | --- | --- |
| Ubuntu GNOME | Wayland | Repeat on X11 before claiming full X11 support |
| KDE Plasma | Wayland | Repeat on X11 before claiming full X11 support |
| XFCE | X11 | Wayland is not part of the current XFCE release target |

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

The script uses a temporary home directory and does not modify the VM user's normal launcher profile. It checks:

1. an isolated install of the current checkout;
2. syntax and presence of autostart, application-menu, and desktop entries;
3. startup of the local server and its owned browser;
4. rejection of a duplicate launcher instance;
5. X11 launcher-window visibility where the window manager exposes it;
6. launch of an owned child process and the Tk overlay;
7. a clean Parent exit, final lifecycle state, and complete process cleanup.

Logs, lifecycle evidence, and the privacy-safe report are written below:

```text
.test-artifacts/desktop-matrix/<desktop>-<session>/
```

An automated run ends with `automation-passed-manual-pending`. That is useful diagnostic evidence, but it is not a completed desktop result.

## Manual desktop checks

Restore the VM snapshot and install normally into the disposable user's actual home:

```bash
bash scripts/install.sh --lang en --launch-mode kiosk --force
```

Reinstall with `--launch-mode fullscreen` for the fullscreen observation. Enable `--install-shutdown-helper` only in a disposable VM snapshot where a real poweroff is safe. Verify all six observations:

1. a fresh login starts exactly one launcher;
2. kiosk and fullscreen modes fit the display without a black screen;
3. the close overlay remains reachable above a launched child app;
4. closing the child app returns focus to the launcher;
5. the desktop shortcut reopens the launcher without creating a duplicate instance;
6. the optional shutdown helper performs a clean VM poweroff through the desktop's expected authorization path.

Then repeat the isolated harness with `--interactive` and record the observations when prompted:

```bash
python3 scripts/linux/desktop_smoke.py \
  --desktop gnome \
  --session wayland \
  --interactive
```

Answer `y` only for an observation performed on the exact VM, session, and commit under test. Answer `n` for a failure and `s` to leave it pending. The final report outcome becomes `passed` only when automation and all six observations pass.

## Release evidence

Attach the three primary `report.json` files to the release-candidate test notes or CI run. Record the exact commit, distribution version, desktop version, session type, browser version, display topology, and any compositor-specific workaround beside the reports.

Do not mark the roadmap item complete from WSLg results or from a report whose final `outcome` is not `passed`. Wayland reports retain `manual-required` annotations for compositor observations, but those are accepted only after the corresponding manual checks pass. Fix defects on a topic branch, restore the clean VM snapshot, and repeat the affected row.
