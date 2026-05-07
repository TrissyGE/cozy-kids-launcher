#!/usr/bin/env python3
"""Fullscreen timer watchdog: blocks the screen when time is up.
Runs outside the browser so it also covers native apps and games."""
import argparse
import json
import os
import subprocess
import sys
import time
import tkinter as tk
from tkinter import font as tkfont
import urllib.request

HOME = os.path.expanduser("~")
APP_ID = "{{APP_ID}}"
APP_NAME = "{{APP_NAME}}"
PORT = int("{{DEFAULT_PORT}}")
BASE_URL = f"http://127.0.0.1:{PORT}"
CACHE_DIR = os.path.join(HOME, ".cache", APP_ID)
BROWSER_PIDFILE = os.path.join(CACHE_DIR, "browser.pid")

# Theme colours matching the launcher
THEME = {
    "bg1": "#ffd6e8",
    "bg2": "#ffeef6",
    "card": "#ffffff",
    "text": "#5f2148",
    "btn": "#e85a9c",
    "btn_text": "#ffffff",
    "accent": "#c2185b",
    "warning": "#ff9800",
    "input_border": "#e8bfd2",
    "smallbtn_bg": "#fff7fb",
}


def api(path, data=None):
    url = BASE_URL + path
    try:
        if data is not None:
            payload = json.dumps(data).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
        else:
            req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return {}


def kill_browser():
    try:
        if os.path.isfile(BROWSER_PIDFILE):
            with open(BROWSER_PIDFILE, "r", encoding="utf-8") as f:
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


def exit_kids():
    try:
        api("/exit-kids", {})
    except Exception:
        pass
    kill_browser()
    sys.exit(0)


class WatchdogApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title(APP_NAME + " Timer")
        self.warn_window = None
        self.block_window = None
        self.polling = True
        self.poll_interval = 5000  # ms
        self.status = {}

    def show_warning(self, remaining):
        if self.warn_window is not None:
            try:
                self.warn_window.lift()
                return
            except tk.TclError:
                self.warn_window = None
        if self.block_window is not None:
            return

        w = tk.Toplevel(self.root)
        self.warn_window = w
        w.overrideredirect(True)
        w.attributes("-topmost", True)
        w.lift()
        w.configure(bg=THEME["warning"])

        sw = w.winfo_screenwidth()
        sh = w.winfo_screenheight()
        ww, wh = 380, 120
        x = (sw - ww) // 2
        y = int(sh * 0.15)
        w.geometry(f"{ww}x{wh}+{x}+{y}")

        frame = tk.Frame(w, bg=THEME["card"], bd=0)
        frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        lbl = tk.Label(
            frame,
            text=f"⏰ {remaining} {{TIMER_MINUTES}}!",
            font=("system-ui", 22, "bold"),
            bg=THEME["card"],
            fg=THEME["text"],
        )
        lbl.pack(expand=True, pady=18)

        w.after(6000, lambda: self._destroy_warn())

    def _destroy_warn(self):
        if self.warn_window is not None:
            try:
                self.warn_window.destroy()
            except tk.TclError:
                pass
            self.warn_window = None

    def show_block(self):
        if self.block_window is not None:
            try:
                self.block_window.lift()
                self.block_window.attributes("-topmost", True)
                return
            except tk.TclError:
                self.block_window = None

        self._destroy_warn()

        b = tk.Toplevel(self.root)
        self.block_window = b
        b.overrideredirect(True)
        b.attributes("-topmost", True)
        b.lift()
        b.focus_force()

        sw = b.winfo_screenwidth()
        sh = b.winfo_screenheight()
        b.geometry(f"{sw}x{sh}+0+0")
        b.configure(bg=THEME["bg1"])

        # Main card
        card = tk.Frame(b, bg=THEME["card"], bd=0)
        card.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Responsive sizing
        base_size = min(sw, sh)
        pad = max(24, int(base_size * 0.03))
        card.configure(padx=pad, pady=pad)

        emoji = tk.Label(
            card,
            text="⏰",
            font=("system-ui", int(base_size * 0.08)),
            bg=THEME["card"],
            fg=THEME["text"],
        )
        emoji.pack(pady=(0, 8))

        title = tk.Label(
            card,
            text="{{TIMER_EXPIRED_TITLE}}",
            font=("system-ui", int(base_size * 0.045), "bold"),
            bg=THEME["card"],
            fg=THEME["text"],
        )
        title.pack()

        body = tk.Label(
            card,
            text="{{TIMER_EXPIRED_BODY}}",
            font=("system-ui", int(base_size * 0.025)),
            bg=THEME["card"],
            fg=THEME["text"],
            wraplength=int(sw * 0.5),
        )
        body.pack(pady=(8, 16))

        # PIN section
        pin_frame = tk.Frame(card, bg=THEME["card"])
        pin_frame.pack(pady=(0, 12))

        pin_lbl = tk.Label(
            pin_frame,
            text="{{TIMER_ENTER_PIN}}",
            font=("system-ui", int(base_size * 0.022)),
            bg=THEME["card"],
            fg=THEME["text"],
        )
        pin_lbl.pack()

        pin_entry = tk.Entry(
            pin_frame,
            show="●",
            font=("system-ui", int(base_size * 0.035)),
            justify="center",
            width=8,
            bg="white",
            fg=THEME["text"],
            highlightthickness=2,
            highlightcolor=THEME["btn"],
            highlightbackground=THEME["input_border"],
        )
        pin_entry.pack(pady=6)
        pin_entry.focus_set()

        err_lbl = tk.Label(
            card,
            text="",
            font=("system-ui", int(base_size * 0.02)),
            bg=THEME["card"],
            fg="#c00",
        )
        err_lbl.pack()

        # Extend buttons
        btn_frame = tk.Frame(card, bg=THEME["card"])
        btn_frame.pack(pady=(12, 0))

        def do_extend(minutes):
            pin = pin_entry.get()
            res = api("/api/timer/extend", {"pin": pin, "minutes": minutes})
            if res.get("valid"):
                err_lbl.config(text="{{TIMER_EXTENDED}}", fg="#27ae60")
                b.after(800, lambda: self._destroy_block())
            else:
                err_lbl.config(text="{{TIMER_WRONG_PIN}}", fg="#c00")
                pin_entry.delete(0, tk.END)
                pin_entry.focus_set()

        for mins, label in [(15, "+15"), (30, "+30"), (60, "+60")]:
            btn = tk.Button(
                btn_frame,
                text=label,
                font=("system-ui", int(base_size * 0.022), "bold"),
                bg=THEME["btn"],
                fg=THEME["btn_text"],
                activebackground=THEME["accent"],
                activeforeground=THEME["btn_text"],
                bd=0,
                padx=16,
                pady=8,
                cursor="hand2",
                command=lambda m=mins: do_extend(m),
            )
            btn.pack(side=tk.LEFT, padx=6)

        # Custom extend
        custom_frame = tk.Frame(card, bg=THEME["card"])
        custom_frame.pack(pady=(12, 0))

        custom_spin = tk.Spinbox(
            custom_frame,
            from_=1,
            to=180,
            width=5,
            font=("system-ui", int(base_size * 0.022)),
            bg="white",
            fg=THEME["text"],
        )
        custom_spin.pack(side=tk.LEFT, padx=(0, 6))
        custom_spin.delete(0, tk.END)
        custom_spin.insert(0, "15")

        custom_btn = tk.Button(
            custom_frame,
            text="{{TIMER_EXTEND}}",
            font=("system-ui", int(base_size * 0.022), "bold"),
            bg=THEME["btn"],
            fg=THEME["btn_text"],
            activebackground=THEME["accent"],
            activeforeground=THEME["btn_text"],
            bd=0,
            padx=14,
            pady=6,
            cursor="hand2",
            command=lambda: do_extend(int(custom_spin.get())),
        )
        custom_btn.pack(side=tk.LEFT)

        # Exit button
        exit_btn = tk.Button(
            card,
            text="{{TIMER_EXIT}}",
            font=("system-ui", int(base_size * 0.022), "bold"),
            bg=THEME["smallbtn_bg"],
            fg=THEME["text"],
            activebackground=THEME["input_border"],
            activeforeground=THEME["text"],
            bd=0,
            padx=20,
            pady=8,
            cursor="hand2",
            command=exit_kids,
        )
        exit_btn.pack(pady=(16, 0))

        # Trap Escape to prevent closing
        b.bind("<Escape>", lambda e: None)
        b.bind("<Alt-F4>", lambda e: None)
        b.bind("<Button-3>", lambda e: None)

        # Keep trying to stay on top
        def stay_top():
            try:
                b.lift()
                b.attributes("-topmost", True)
                b.focus_force()
            except tk.TclError:
                return
            b.after(500, stay_top)

        stay_top()

    def _destroy_block(self):
        if self.block_window is not None:
            try:
                self.block_window.destroy()
            except tk.TclError:
                pass
            self.block_window = None

    def tick(self):
        if not self.polling:
            return
        data = api("/api/timer/status")
        self.status = data
        active = data.get("active", False)
        expired = data.get("expired", False)
        warning = data.get("warning", False)
        remaining = data.get("remainingSeconds", 0)

        if expired:
            self.show_block()
        elif warning and not self.warn_window:
            mins = max(1, remaining // 60)
            self.show_warning(mins)
        elif not warning and not expired:
            self._destroy_warn()

        self.root.after(self.poll_interval, self.tick)

    def run(self):
        self.tick()
        self.root.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=PORT)
    args = parser.parse_args()
    global BASE_URL
    BASE_URL = f"http://127.0.0.1:{args.port}"
    app = WatchdogApp()
    app.run()


if __name__ == "__main__":
    main()
