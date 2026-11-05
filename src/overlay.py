#!/usr/bin/env python3
"""App overlay: always-on-top close button + timer for external browser and local apps."""
import argparse
import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
from urllib.request import Request, urlopen

from process_state import (
    owned_process,
    owned_process_alive,
    remove_process_record,
    terminate_owned_process,
    write_process_record,
)

from runtime_locale import saved_locale

HOME = os.path.expanduser("~")
APP_ID = "{{APP_ID}}"
CONFIG = os.path.join(HOME, ".config", APP_ID, "config.json")
APP_NAME = "{{APP_NAME}}"
CACHE_DIR = os.path.join(HOME, ".cache", APP_ID)
BROWSER_PIDFILE = os.path.join(CACHE_DIR, "browser.pid")
TILE_PROCESS_PIDFILE = os.path.join(CACHE_DIR, "tile-process.pid")
OVERLAY_PIDFILE = os.path.join(CACHE_DIR, "overlay.pid")
TILE_PROCESS_MARKER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "process_supervisor.py")
OVERLAY_MARKER = os.path.abspath(__file__)

THEME = {
    "bg": "#ffffff",
    "text": "#333333",
    "close_bg": "#ffebee",
    "close_fg": "#c00",
    "timer_text": "#333333",
}


class MonitorInfo(ctypes.Structure):
    # Xrandr.h XRRMonitorInfo (RandR 1.5); Atom/RROutput are native longs.
    _fields_ = [("name", ctypes.c_ulong), ("primary", ctypes.c_int),
                ("automatic", ctypes.c_int), ("noutput", ctypes.c_int),
                ("x", ctypes.c_int), ("y", ctypes.c_int),
                ("width", ctypes.c_int), ("height", ctypes.c_int),
                ("mwidth", ctypes.c_int), ("mheight", ctypes.c_int),
                ("outputs", ctypes.POINTER(ctypes.c_ulong))]


def overlay_geometry(monitors, screen_size, expanded):
    """Anchor the control inside an active monitor, including offset layouts."""
    usable = [item for item in monitors if item[2] > 0 and item[3] > 0]
    bounds = next((item for item in usable if item[4]), None)
    bounds = bounds or next(iter(usable), (0, 0, *screen_size, True))
    x, y, width, height = bounds[:4]
    control_width = min(220 if expanded else 60, max(1, width))
    control_height = min(70 if expanded else 60, max(1, height))
    return (control_width, control_height,
            x + min(24, max(0, width - control_width)),
            y + min(24, max(0, height - control_height)))


class X11WindowRaiser:
    """Raise one owned X11/XWayland window without a command dependency."""

    def __init__(self, loader=ctypes.CDLL):
        self.library = None
        self.display = None
        self.randr = None
        if not os.environ.get("DISPLAY"):
            return
        try:
            library = loader("libX11.so.6")
            library.XOpenDisplay.argtypes = [ctypes.c_char_p]
            library.XOpenDisplay.restype = ctypes.c_void_p
            library.XRaiseWindow.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
            library.XFlush.argtypes = [ctypes.c_void_p]
            library.XCloseDisplay.argtypes = [ctypes.c_void_p]
            display = library.XOpenDisplay(None)
        except (AttributeError, OSError):
            return
        if display:
            self.library = library
            self.display = display
            try:
                library.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
                library.XDefaultRootWindow.restype = ctypes.c_ulong
                randr = loader("libXrandr.so.2")
                randr.XRRQueryVersion.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)]
                randr.XRRQueryVersion.restype = ctypes.c_int
                randr.XRRGetMonitors.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int, ctypes.POINTER(ctypes.c_int)]
                randr.XRRGetMonitors.restype = ctypes.POINTER(MonitorInfo)
                randr.XRRFreeMonitors.argtypes = [ctypes.POINTER(MonitorInfo)]
                randr.XRRFreeMonitors.restype = None
                major, minor = ctypes.c_int(), ctypes.c_int()
                if randr.XRRQueryVersion(display, ctypes.byref(major), ctypes.byref(minor)) and (major.value, minor.value) >= (1, 5):
                    self.randr = randr
            except (AttributeError, OSError):
                pass  # Older desktops retain the Tk screen-size fallback.

    def monitors(self):
        if not self.randr or not self.display:
            return []
        count = ctypes.c_int()
        monitors = self.randr.XRRGetMonitors(
            self.display, self.library.XDefaultRootWindow(self.display), 1, ctypes.byref(count))
        try:
            if not monitors or not 0 < count.value <= 64:
                return []
            return [(item.x, item.y, item.width, item.height, bool(item.primary))
                    for item in monitors[:count.value]]
        finally:
            if monitors:
                self.randr.XRRFreeMonitors(monitors)

    def raise_window(self, window_id):
        if not self.library or not self.display:
            return False
        self.library.XRaiseWindow(self.display, ctypes.c_ulong(int(window_id)))
        self.library.XFlush(self.display)
        return True

    def close(self):
        if self.library and self.display:
            self.library.XCloseDisplay(self.display)
            self.display = None


def configure_overlay_window(window):
    """Apply compositor hints that keep the control above fullscreen apps."""
    try:
        # Tk runs through XWayland in the supported Wayland sessions. KWin can
        # place a plain topmost XWayland window behind an app after that app
        # enters fullscreen. The EWMH dock type keeps this small control on the
        # panel layer without reserving screen space.
        window.attributes("-type", "dock")
    except tk.TclError:
        pass
    try:
        window.attributes("-topmost", True)
    except tk.TclError:
        pass
    window.lift()


def x11_toplevel_id(window):
    """Return the outer X11 frame that the compositor actually stacks."""
    try:
        frame = window.tk.call("wm", "frame", window._w)
        return int(str(frame), 0)
    except (AttributeError, tk.TclError, TypeError, ValueError):
        return int(window.winfo_id())


def api(path, data=None):
    port = os.environ.get("COZY_KIDS_PORT", "{{DEFAULT_PORT}}")
    url = f"http://127.0.0.1:{port}{path}"
    try:
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            req = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")
        else:
            req = Request(url)
        with urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def focus_launcher():
    record = owned_process(BROWSER_PIDFILE, "browser")
    if not record:
        return
    try:
        result = subprocess.run(["wmctrl", "-lp"], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                fields = line.split(None, 4)
                if len(fields) >= 4 and fields[2] == str(record["pid"]):
                    # Window titles are not ownership evidence. Revalidate the
                    # recorded browser before activating its enumerated XID.
                    if owned_process(BROWSER_PIDFILE, "browser") != record:
                        return
                    subprocess.run(["wmctrl", "-i", "-a", fields[0]], timeout=3, check=False)
                    return
    except Exception:
        pass
    try:
        if owned_process(BROWSER_PIDFILE, "browser") != record:
            return
        subprocess.run(
            ["xdotool", "search", "--pid", str(record["pid"]), "windowactivate"],
            capture_output=True, timeout=3, check=False,
        )
    except Exception:
        pass


def tile_is_blocked(status, tile_id):
    if not tile_id or not isinstance(status, dict):
        return False
    blocked = status.get("blockedTileIds", [])
    if not isinstance(blocked, list):
        blocked = []
    return status.get("profileAllowed") is False or tile_id in blocked


class AppOverlay:
    def __init__(self, mode, url, label, tile_id=""):
        self.mode = mode
        self.url = url
        self.label = label
        self.tile_id = tile_id
        self.hide_after_ms = 2000
        self.expanded = True
        self.geometry = None
        self.ready = False
        self.timer_results = queue.Queue(maxsize=1)
        self.timer_polling = False
        self.next_timer_poll = 0

        self.root = tk.Tk()
        self.root.title("App Overlay")
        self.root.overrideredirect(True)
        self.root.resizable(False, False)
        configure_overlay_window(self.root)
        self.x11_raiser = X11WindowRaiser()

        self.frame = tk.Frame(self.root, bg=THEME["bg"], bd=0)
        self.frame.pack(fill=tk.BOTH, expand=True)

        self.close_btn = tk.Button(
            self.frame, text="❌", font=("system-ui", 16, "bold"),
            bg=THEME["close_bg"], fg=THEME["close_fg"], bd=0,
            width=2, height=1, cursor="hand2", command=self.on_close,
        )
        self.close_btn.pack(side=tk.LEFT, padx=8, pady=8)

        self.timer_lbl = tk.Label(
            self.frame, text="", font=("system-ui", 14, "bold"),
            bg=THEME["bg"], fg=THEME["timer_text"],
        )
        self.timer_lbl.pack(side=tk.LEFT, padx=4, pady=8)

        # Bind motion/enter on root, frame, and button for robustness
        for widget in (self.root, self.frame, self.close_btn):
            widget.bind("<Motion>", self.on_motion)
            widget.bind("<Enter>", self.on_motion)

        self.hide_timer = None
        self.reset_hide_timer()

        self.root.after(0, self.poll_process)
        self.root.after(0, self.poll_timer)
        self.root.after(0, self.stay_on_top)
        self.root.after_idle(self.report_ready)

    def place_control(self):
        geometry = overlay_geometry(
            self.x11_raiser.monitors(),
            (self.root.winfo_screenwidth(), self.root.winfo_screenheight()), self.expanded)
        width, height, x, y = geometry
        actual_position = (self.root.winfo_rootx(), self.root.winfo_rooty())
        if geometry != self.geometry or actual_position != (x, y):
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.geometry = geometry

    def report_ready(self):
        # A PID (or even a title) can exist before Tk maps and lays out the
        # close button. Do not acknowledge a usable control until both map.
        if self.root.winfo_viewable() and self.close_btn.winfo_viewable() and self.close_btn.winfo_width() > 1:
            write_process_record(OVERLAY_PIDFILE, os.getpid(), "overlay", marker=OVERLAY_MARKER, ready=True)
            self.ready = True
            return
        self.root.after(50, self.report_ready)

    def stay_on_top(self):
        """Periodically force this window to the front so it stays visible over kiosk apps."""
        try:
            self.place_control()
            self.root.lift()
            self.root.attributes("-topmost", True)
            # Mutter can restack a fullscreen XWayland app above Tk even though
            # Tk still reports the topmost attribute. Raise only this overlay's
            # own XID directly; no global window lookup or extra tool is needed.
            self.x11_raiser.raise_window(x11_toplevel_id(self.root))
        except tk.TclError:
            pass
        self.root.after(500, self.stay_on_top)

    def reset_hide_timer(self):
        if self.hide_timer:
            self.root.after_cancel(self.hide_timer)
        self.show_full()
        self.hide_timer = self.root.after(self.hide_after_ms, self.show_minimal)

    def show_full(self):
        self.expanded = True
        self.timer_lbl.pack(side=tk.LEFT, padx=4, pady=8)
        self.place_control()

    def show_minimal(self):
        # Hide timer label but keep close button visible and fully opaque
        self.timer_lbl.pack_forget()
        self.expanded = False
        self.place_control()

    def on_motion(self, event=None):
        self.reset_hide_timer()

    def on_close(self):
        try:
            terminate_owned_process(
                TILE_PROCESS_PIDFILE,
                "tile-process",
                TILE_PROCESS_MARKER,
            )
        except Exception:
            pass
        focus_launcher()
        self.root.destroy()
        sys.exit(0)

    def poll_process(self):
        if not owned_process_alive(
            TILE_PROCESS_PIDFILE,
            "tile-process",
            TILE_PROCESS_MARKER,
        ):
            self.on_close()
            return
        self.root.after(1000, self.poll_process)

    def poll_timer(self):
        # HTTP timeouts must not freeze the only close control. The worker
        # touches no Tk objects; at most one bounded request pair is in flight.
        try:
            availability, data = self.timer_results.get_nowait()
        except queue.Empty:
            pass
        else:
            self.timer_polling = False
            self.next_timer_poll = time.monotonic() + 10
            if self.apply_timer_status(availability, data):
                return
        if not self.timer_polling and time.monotonic() >= self.next_timer_poll:
            self.timer_polling = True
            threading.Thread(target=self.fetch_timer_status, daemon=True).start()
        self.root.after(250, self.poll_timer)

    def fetch_timer_status(self):
        self.timer_results.put((api("/api/availability/status"), api("/api/timer/status")))

    def apply_timer_status(self, availability, data):
        if tile_is_blocked(availability, self.tile_id):
            self.on_close()
            return True
        if data.get("active"):
            text = saved_locale(CONFIG)
            remaining = data.get("remainingSeconds", 0)
            mins = max(0, remaining // 60)
            if data.get("expired"):
                self.timer_lbl.config(text="⏰ " + text["timer_expired"], fg="#c00")
            elif data.get("warning"):
                self.timer_lbl.config(text=f"⏱️ {mins} {text['timer_minutes']}", fg="#e65100")
            else:
                self.timer_lbl.config(text=f"⏱️ {mins} {text['timer_minutes']}", fg=THEME["timer_text"])
        else:
            self.timer_lbl.config(text="")
        return False

    def run(self):
        try:
            self.root.mainloop()
        finally:
            self.x11_raiser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="external", choices=["external", "local"])
    parser.add_argument("--url", default="")
    parser.add_argument("--label", default="Home")
    parser.add_argument("--tile-id", default="")
    args = parser.parse_args()

    overlay = AppOverlay(args.mode, args.url, args.label, tile_id=args.tile_id)
    write_process_record(
        OVERLAY_PIDFILE,
        os.getpid(),
        "overlay",
        marker=OVERLAY_MARKER,
        ready=False,
    )
    try:
        overlay.run()
    finally:
        remove_process_record(OVERLAY_PIDFILE, expected_pid=os.getpid())


if __name__ == "__main__":
    main()
