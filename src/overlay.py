#!/usr/bin/env python3
"""App overlay: always-on-top close button + timer for external browser and local apps."""
import argparse
import json
import os
import subprocess
import sys
import tkinter as tk
from urllib.request import Request, urlopen

from process_state import (
    owned_process,
    owned_process_alive,
    remove_process_record,
    terminate_owned_process,
    write_process_record,
)

HOME = os.path.expanduser("~")
APP_ID = "{{APP_ID}}"
APP_NAME = "{{APP_NAME}}"
CACHE_DIR = os.path.join(HOME, ".cache", APP_ID)
BROWSER_PIDFILE = os.path.join(CACHE_DIR, "browser.pid")
TILE_PROCESS_PIDFILE = os.path.join(CACHE_DIR, "tile-process.pid")
OVERLAY_PIDFILE = os.path.join(CACHE_DIR, "overlay.pid")
TILE_PROCESS_MARKER = os.path.join(
    HOME,
    ".local",
    "share",
    APP_ID,
    "process_supervisor.py",
)
OVERLAY_MARKER = os.path.abspath(__file__)

THEME = {
    "bg": "#ffffff",
    "text": "#333333",
    "close_bg": "#ffebee",
    "close_fg": "#c00",
    "timer_text": "#333333",
}


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
    try:
        result = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, timeout=3)
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Cozy Kids Launcher" in line or APP_NAME in line:
                    wid = line.split()[0]
                    subprocess.run(["wmctrl", "-i", "-r", wid, "-b", "add,above"], check=False)
                    subprocess.run(["wmctrl", "-i", "-a", wid], check=False)
                    return
    except Exception:
        pass
    try:
        record = owned_process(BROWSER_PIDFILE, "browser")
        if not record:
            return
        subprocess.run(
            ["xdotool", "search", "--pid", str(record["pid"]), "windowactivate"],
            capture_output=True, timeout=3, check=False,
        )
    except Exception:
        pass


class AppOverlay:
    def __init__(self, mode, url, label):
        self.mode = mode
        self.url = url
        self.label = label
        self.hide_after_ms = 2000

        self.root = tk.Tk()
        self.root.title("App Overlay")
        self.root.overrideredirect(True)
        self.root.geometry("220x70+24+24")
        self.root.resizable(False, False)
        configure_overlay_window(self.root)
        self.root.focus_force()

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

    def stay_on_top(self):
        """Periodically force this window to the front so it stays visible over kiosk apps."""
        try:
            self.root.lift()
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.root.after(500, self.stay_on_top)

    def reset_hide_timer(self):
        if self.hide_timer:
            self.root.after_cancel(self.hide_timer)
        self.show_full()
        self.hide_timer = self.root.after(self.hide_after_ms, self.show_minimal)

    def show_full(self):
        self.timer_lbl.pack(side=tk.LEFT, padx=4, pady=8)
        self.root.geometry("220x70+24+24")

    def show_minimal(self):
        # Hide timer label but keep close button visible and fully opaque
        self.timer_lbl.pack_forget()
        self.root.geometry("60x60+24+24")

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
        data = api("/api/timer/status")
        if data.get("active"):
            remaining = data.get("remainingSeconds", 0)
            mins = max(0, remaining // 60)
            if data.get("expired"):
                self.timer_lbl.config(text="⏰ {{TIMER_EXPIRED}}", fg="#c00")
            elif data.get("warning"):
                self.timer_lbl.config(text=f"⏱️ {mins} {{TIMER_MINUTES}}", fg="#e65100")
            else:
                self.timer_lbl.config(text=f"⏱️ {mins} {{TIMER_MINUTES}}", fg=THEME["timer_text"])
        else:
            self.timer_lbl.config(text="")
        self.root.after(10000, self.poll_timer)

    def run(self):
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="external", choices=["external", "local"])
    parser.add_argument("--url", default="")
    parser.add_argument("--label", default="Home")
    args = parser.parse_args()

    overlay = AppOverlay(args.mode, args.url, args.label)
    write_process_record(
        OVERLAY_PIDFILE,
        os.getpid(),
        "overlay",
        marker=OVERLAY_MARKER,
    )
    try:
        overlay.run()
    finally:
        remove_process_record(OVERLAY_PIDFILE, expected_pid=os.getpid())


if __name__ == "__main__":
    main()
