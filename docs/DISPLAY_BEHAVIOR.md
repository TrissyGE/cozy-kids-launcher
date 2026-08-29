# X11 and Wayland display behavior

Cozy Kids Launcher supports complete desktop sessions without replacing their
window manager or compositor. X11 and Wayland expose different control
boundaries, so the launcher deliberately makes different guarantees on each.

## Browser launch modes

The installer persists one of three launch modes. The desktop smoke harness
reads the owned browser process directly from `/proc` and verifies that its
argument vector matches the selected mode.

| Mode | Chromium family | Firefox family | Intended behavior |
| --- | --- | --- | --- |
| `window` | no kiosk/fullscreen switch | no kiosk/fullscreen switch | ordinary desktop window |
| `fullscreen` | `--start-fullscreen` | compatibility passthrough; no upstream-supported switch | fullscreen UI that still follows normal browser policies |
| `kiosk` | `--kiosk` | `--kiosk` | strict browser chrome suppression |

These checks prove that the requested mode reached the owned browser process.
They cannot prove compositor placement, screen coverage, or the absence of a
black frame; those remain visual checks in the VM matrix.

Firefox's upstream
[command-line reference](https://firefox-source-docs.mozilla.org/browser/CommandLineParameters.html)
documents `--kiosk`, but not a separate fullscreen command-line mode. Its
retained `--fullscreen` argument is a compatibility passthrough and is not used
for a primary release-matrix row. Use Firefox kiosk when browser chrome must be
suppressed, and use a Chromium-family browser for the primary fullscreen row.

When Chromium starts in `fullscreen` or `kiosk`, the launcher removes only its
cached `browser.window_placement` preference before applying the mode switch.
This prevents geometry saved by an earlier windowed session from overriding an
explicit display-mode change. Ordinary `window` launches retain their saved
geometry.

The generated desktop autostart entry uses a short compositor-settling delay
after acquiring the single-instance lock. This keeps early GNOME session startup
from downgrading a valid fullscreen request to an ordinary maximized window;
manual and desktop-shortcut launches remain immediate.

## X11 contract

X11 allows the smoke harness and overlay to use standard window-management
interfaces:

- `wmctrl` checks ordinary EWMH windows and raises the launcher by its title;
- `xdotool` detects override-redirect windows such as the small Tk overlay;
- the overlay uses the `dock` window type plus the topmost hint;
- the harness clicks the overlay's fixed close control, verifies that the owned
  tile process ends, and verifies that focus returns to a known launcher window;
- the fallback activation path is scoped to the browser PID from the verified
  ownership record. It never searches for or terminates a browser by name.

The automated focus assertion is enabled only for a real X11 session. XFCE/X11
is the primary release-matrix target for this contract.

## Wayland contract

Wayland intentionally prevents clients from enumerating and activating all
windows globally. The launcher therefore does not claim an automation escape
hatch around compositor security:

- browser startup, selected launch-mode switch, server readiness, process
  ownership, tile shutdown, overlay process startup, and final cleanup are
  automated;
- the Tk overlay runs through XWayland and requests `dock` and topmost hints;
- GNOME and KDE decide final stacking, focus, and fullscreen placement;
- overlay reachability above a fullscreen child and focus after closing that
  child require a visual observation in the exact compositor session.

This is why a Wayland report contains `manual-required` entries even when every
automatable process and API check passes. A pending manual entry is not a test
failure, but it is not release evidence for the visual behavior either.

## Running the contract

Run each command from a terminal inside the matching graphical VM session:

```bash
python3 scripts/linux/desktop_smoke.py \
  --desktop gnome --session wayland --launch-mode kiosk
python3 scripts/linux/desktop_smoke.py \
  --desktop kde --session wayland --launch-mode fullscreen
python3 scripts/linux/desktop_smoke.py \
  --desktop xfce --session x11 --launch-mode kiosk
```

Repeat a session with `--launch-mode window` when ordinary window placement is
part of the change under test. Add `--interactive` only after performing all six
manual observations listed in [DESKTOP_TESTING.md](DESKTOP_TESTING.md).

The default report directory includes desktop, session, and launch mode:

```text
.test-artifacts/desktop-matrix/<desktop>-<session>-<launch-mode>/
```

## Session troubleshooting

Run the harness from inside the graphical session whenever possible. An SSH
shell usually lacks the live display authorization data. If automation must be
started remotely, obtain `DISPLAY`, `WAYLAND_DISPLAY`, `XAUTHORITY`,
`XDG_RUNTIME_DIR`, and `DBUS_SESSION_BUS_ADDRESS` from a process in the current
desktop session. Do not reuse an `XAUTHORITY` path captured before a logout or
desktop switch; GNOME creates a new XWayland cookie file for each session.
