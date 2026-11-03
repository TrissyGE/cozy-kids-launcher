# Catalog fullscreen acceptance

Legacy KDE recommendations store commands such as
`["kstart", "--fullscreen", "kturtle"]`. The HTTP launch path previously removed
the wrapper before supervision, losing the fullscreen request. The owned tile
supervisor now consumes that request itself: it starts the actual app directly,
addresses only a normal window belonging to its own process tree, and waits for
the window manager to confirm `_NET_WM_STATE_FULLSCREEN`.

The default Qt platform for this path is `xcb`, including on a Wayland desktop
with XWayland. Explicit incompatible Qt platform overrides are rejected before
starting the app. Missing X11 support or failed fullscreen confirmation fails
the launch and cleans up its owned processes. No detached `kstart`, title-based
fullscreen targeting, root helper or extra runtime dependency is introduced.

Bare/custom app commands keep their arguments and existing display behavior.
The TuxMath SDL adaptation remains separate: it uses ungrabbed rendering inside
confirmed compositor fullscreen. A launcher restart never converts a Parent's
windowed setting into a catalog default.

## Repeatable real-app checks

In an unlocked, disposable complete desktop with the selected app installed:

```bash
python3 scripts/linux/desktop_smoke.py \
  --desktop kde --session wayland --browser google-chrome \
  --launch-mode kiosk --catalog-app kturtle

python3 scripts/linux/desktop_smoke.py \
  --desktop kde --session wayland --browser google-chrome \
  --launch-mode kiosk --catalog-app kbruch
```

`--catalog-app` currently accepts existing KDE-wrapper recommendations only.
It does not install system packages. The harness installs the checkout into a
temporary home and uses the catalog's actual command. It independently observes
the owned app's fullscreen property without requesting fullscreen itself,
records geometry, clicks the real Home overlay, checks tile termination and
then checks clean launcher exit and owned-process cleanup.

On X11 the existing focus-return assertion remains mandatory. XWayland can
expose the app/overlay on a Wayland desktop, but cannot establish a native
Wayland launcher's focus. That observation remains explicitly manual, along
with meaningful lesson/game input, physical keyboard/touch, fresh-login and
poweroff observations. An `automation-passed-manual-pending` report is not a
completed release matrix row.

Reports are written beneath `.test-artifacts/desktop-matrix/` with the app ID in
the directory name. Record the source revision, app version, desktop/session,
browser mode and display geometry with any published evidence.

## Scope

KTurtle and KBruch are the first real-app probes for this correction. Other
legacy entries and native GNOME/X11 sessions still need individual checks.
No catalog entry, package mapping or new emulator is added by this work.

The implementation follows the
[EWMH fullscreen and window-identity contract](https://specifications.freedesktop.org/wm/latest/ar01s05.html)
and Qt's documented [platform selection](https://doc.qt.io/qt-5/qguiapplication.html#QGuiApplication).

## KolourPaint and KGeography

The catalog uses the same owned fullscreen path for KolourPaint and
KGeography. Ubuntu 24.04 supplies both packages. Repeat the desktop smoke
commands above with `--catalog-app kolourpaint` or `--catalog-app kgeography`
and the primary browser and mode in [DESKTOP_TESTING.md](DESKTOP_TESTING.md).

In KolourPaint, draw a line on a new canvas and undo it. In KGeography, select
a map if the first-run chooser opens, then use **Open Map** to load another
map and verify that the displayed regions change. Use the launcher’s Home
overlay to close each app and return to the child view. KGeography can open
Wikipedia in the default browser through its information buttons.

KStars and Stellarium remain candidates. The Ubuntu packages were available.
The probe observed launcher start failures on KDE Wayland and inconsistent
launch or input on GNOME Wayland. The astronomy candidates need separate
qualification.
