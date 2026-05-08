#!/usr/bin/env python3
"""App overlay: always-on-top close button + timer for external browser and local apps."""
import argparse
import json
import os
import subprocess
import sys
import time
import tkinter as tk
from urllib.request import Request, urlopen

HOME = os.path.expanduser("~")
APP_ID = "{{APP_ID}}"
APP_NAME = "{{APP_NAME}}"
CACHE_DIR = os.path.join(HOME, ".cache", APP_ID)
BROWSER_PIDFILE = os.path.join(CACHE_DIR, "browser.pid")
EXTERNAL_BROWSER_PIDFILE = os.path.join(CACHE_DIR, "external-browser.pid")

THEME = {
    "bg": "#ffffff",
    "text": "#333333",
    "close_bg": "#ffebee",
    "close_fg": "#c00",
    "timer_text": "#333333",
}


def api(path, data=None):
    url = f"http://127.0.0.1:{{DEFAULT_PORT}}{path}"
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
        with open(BROWSER_PIDFILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
        subprocess.run(
            ["xdotool", "search", "--pid", str(pid), "windowactivate"],
            capture_output=True, timeout=3, check=False,
        )
    except Exception:
        pass


def kill_browser_by_pidfile():
    try:
        if os.path.isfile(EXTERNAL_BROWSER_PIDFILE):
            with open(EXTERNAL_BROWSER_PIDFILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            os.kill(pid, 15)
            for _ in range(10):
                try:
                    os.kill(pid, 0)
                    time.sleep(0.2)
                except ProcessLookupError:
                    break
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass
    except Exception:
        pass
    try:
        os.remove(EXTERNAL_BROWSER_PIDFILE)
    except Exception:
        pass


def kill_local_app(app_cmd):
    """Kill a local app by command name or active window."""
    killed = False
    try:
        result = subprocess.run(["pgrep", "-f", app_cmd], capture_output=True, text=True)
        my_pid = os.getpid()
        for pid_str in result.stdout.strip().split("\n"):
            if pid_str:
                try:
                    pid = int(pid_str)
                    if pid != my_pid:
                        os.kill(pid, 15)
                        killed = True
                except Exception:
                    pass
    except Exception:
        pass
    if not killed:
        try:
            result = subprocess.run(["xdotool", "getactivewindow"], capture_output=True, text=True, timeout=2)
            wid = result.stdout.strip()
            if wid:
                subprocess.run(["wmctrl", "-ic", wid], check=False)
        except Exception:
            pass


class AppOverlay:
    def __init__(self, mode, url, label, browser_pid, app_cmd):
        self.mode = mode
        self.url = url
        self.label = label
        self.browser_pid = browser_pid
        self.app_cmd = app_cmd
        self.hide_after_ms = 2000

        self.root = tk.Tk()
        self.root.title("App Overlay")
        self.root.overrideredirect(True)
        self.root.geometry("220x70+24+24")
        self.root.resizable(False, False)
        try:
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        self.root.lift()
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

        self.poll_browser()
        self.poll_timer()
        self.stay_on_top()

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
        if self.browser_pid:
            try:
                os.kill(self.browser_pid, 15)
                for _ in range(10):
                    try:
                        os.kill(self.browser_pid, 0)
                        time.sleep(0.2)
                    except ProcessLookupError:
                        break
                try:
                    os.kill(self.browser_pid, 9)
                except ProcessLookupError:
                    pass
            except Exception:
                pass
        kill_browser_by_pidfile()
        if self.mode == "local" and self.app_cmd:
            kill_local_app(self.app_cmd)
        focus_launcher()
        self.root.destroy()
        sys.exit(0)

    def poll_browser(self):
        if self.browser_pid:
            try:
                os.kill(self.browser_pid, 0)
            except ProcessLookupError:
                self.on_close()
                return
        if not self.browser_pid and os.path.isfile(EXTERNAL_BROWSER_PIDFILE):
            try:
                with open(EXTERNAL_BROWSER_PIDFILE, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
            except (ProcessLookupError, ValueError, FileNotFoundError):
                self.on_close()
                return
        self.root.after(1000, self.poll_browser)

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
    parser.add_argument("--browser-pid", type=int, default=None)
    parser.add_argument("--app-cmd", default="")
    args = parser.parse_args()

    overlay = AppOverlay(args.mode, args.url, args.label, args.browser_pid, args.app_cmd)
    overlay.run()


if __name__ == "__main__":
    main()
