#!/usr/bin/env python3
"""Tiny always-on-top overlay button to return from external browser to launcher."""
import argparse
import os
import subprocess
import sys
import time
import tkinter as tk

HOME = os.path.expanduser("~")
APP_ID = "{{APP_ID}}"
CACHE_DIR = os.path.join(HOME, ".cache", APP_ID)
BROWSER_PIDFILE = os.path.join(CACHE_DIR, "browser.pid")
EXTERNAL_BROWSER_PIDFILE = os.path.join(CACHE_DIR, "external-browser.pid")


def kill_browser_by_pidfile():
    """Kill the external browser process tracked in the pidfile."""
    pid_path = EXTERNAL_BROWSER_PIDFILE
    try:
        if os.path.isfile(pid_path):
            with open(pid_path, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            os.kill(pid, 15)
            # Wait a moment then SIGKILL if still alive
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
        os.remove(pid_path)
    except Exception:
        pass


def focus_launcher():
    """Try to bring the launcher browser window to the front."""
    try:
        result = subprocess.run(
            ["wmctrl", "-l"],
            capture_output=True, text=True, timeout=3
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if "Cozy Kids Launcher" in line or "{{APP_NAME}}" in line:
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
            capture_output=True, timeout=3, check=False
        )
    except Exception:
        pass


def build_overlay(url, label, browser_pid=None):
    root = tk.Tk()
    root.title("Home")
    root.overrideredirect(True)
    root.geometry("110x80+24+24")
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except tk.TclError:
        pass
    root.lift()
    root.focus_force()

    def on_click(event=None):
        if browser_pid:
            try:
                os.kill(browser_pid, 15)
                for _ in range(10):
                    try:
                        os.kill(browser_pid, 0)
                        time.sleep(0.2)
                    except ProcessLookupError:
                        break
                try:
                    os.kill(browser_pid, 9)
                except ProcessLookupError:
                    pass
            except Exception:
                pass
        kill_browser_by_pidfile()
        focus_launcher()
        root.destroy()
        sys.exit(0)

    # Also close automatically if the browser dies
    def poll_browser():
        if browser_pid:
            try:
                os.kill(browser_pid, 0)
            except ProcessLookupError:
                root.destroy()
                sys.exit(0)
        # Also check pidfile if no direct pid was given
        if not browser_pid and os.path.isfile(EXTERNAL_BROWSER_PIDFILE):
            try:
                with open(EXTERNAL_BROWSER_PIDFILE, "r", encoding="utf-8") as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
            except (ProcessLookupError, ValueError, FileNotFoundError):
                root.destroy()
                sys.exit(0)
        root.after(1000, poll_browser)

    btn = tk.Button(
        root, text="🏠\n" + (label or "Home"),
        font=("system-ui", 10, "bold"),
        bg="#f5f5f5",
        fg="#333",
        bd=0,
        padx=4, pady=4,
        command=on_click,
        cursor="hand2",
    )
    btn.pack(fill=tk.BOTH, expand=True)

    root.bind("<Button-3>", lambda e: on_click())
    root.bind("<Escape>", lambda e: on_click())

    poll_browser()
    root.mainloop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--label", default="Home")
    parser.add_argument("--browser-pid", type=int, default=None)
    args = parser.parse_args()
    build_overlay(args.url, args.label, args.browser_pid)


if __name__ == "__main__":
    main()
