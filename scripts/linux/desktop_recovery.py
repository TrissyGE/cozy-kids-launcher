"""Opt-in fault injection for disposable desktop VMs, using installed code."""

import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

import desktop_smoke as smoke


def recover_fullscreen(supervisor_pid):
    from app_display import X11Fullscreen
    from process_state import process_start_time
    window = smoke.wait_until(lambda: smoke.owned_fullscreen_window(supervisor_pid))
    display = X11Fullscreen()
    identity = process_start_time(supervisor_pid)
    try:
        if identity is None:
            raise RuntimeError("Fixture supervisor exited before fault injection")
        def fullscreen():
            return display.atom("_NET_WM_STATE_FULLSCREEN") in display.values(window, "_NET_WM_STATE", "ATOM")
        # Pause only the verified fixture's supervisor, not the app or WM, so
        # fast recovery cannot hide the deliberately injected state loss.
        os.kill(supervisor_pid, signal.SIGSTOP)
        try:
            subprocess.run(["wmctrl", "-i", "-r", str(window), "-b", "remove,fullscreen"], check=True, timeout=5)
            smoke.wait_until(lambda: not fullscreen(), timeout=5, interval=0.02, message="Did not observe injected fullscreen loss")
        finally:
            if identity is not None and process_start_time(supervisor_pid) == identity:
                os.kill(supervisor_pid, signal.SIGCONT)
        smoke.wait_until(fullscreen, timeout=8, interval=0.05, message="Owned window did not recover fullscreen")
        assert smoke.owned_fullscreen_window(supervisor_pid) == window
    finally:
        display.close()
    return "same owned application window regains fullscreen after observed EWMH state loss"


def window_geometry(window):
    text = subprocess.check_output(["xdotool", "getwindowgeometry", "--shell", str(window)], text=True, timeout=5)
    return {key: int(value) for key, value in re.findall(r"^(X|Y|WIDTH|HEIGHT)=(-?\d+)$", text, re.MULTILINE)}


def resize_x11(overlay_window, artifacts):
    """Shrink a virtual output with a displaced control, then restore it."""
    from overlay import X11WindowRaiser
    text = subprocess.check_output(["xrandr", "--query"], text=True, timeout=5)
    active = re.findall(r"^(\S+) connected (primary )?(\d+)x(\d+)\+(\d+)\+(\d+)", text, re.MULTILINE)
    if len(active) != 1:
        raise RuntimeError("Resize injection requires exactly one active output in a disposable XFCE VM")
    output, primary, width, height, x, y = active[0]
    screen = re.search(r"current (\d+) x (\d+)", text)
    if not screen or not re.search(r"^\s+800x600\s", text, re.MULTILINE):
        raise RuntimeError("Expected a virtual output supporting 800x600")
    restore = ["xrandr", "--fb", "x".join(screen.groups()), "--output", output,
               "--mode", f"{width}x{height}", "--pos", f"{x}x{y}", "--primary" if primary else "--noprimary"]
    reader = X11WindowRaiser()
    evidence = {"original": text}
    try:
        subprocess.run(["xdotool", "windowmove", str(overlay_window), "1100", "700"], check=True, timeout=5)
        evidence["displacedOverlay"] = window_geometry(overlay_window)
        assert evidence["displacedOverlay"]["X"] >= 800, "Did not observe displaced control"
        subprocess.run(["xrandr", "--fb", "800x600", "--output", output,
                        "--mode", "800x600", "--pos", "0x0", "--primary"], check=True, timeout=10)
        smoke.wait_until(lambda: any(item[:4] == (0, 0, 800, 600) for item in reader.monitors()), timeout=10)
        def relocated():
            geometry = window_geometry(overlay_window)
            return geometry if geometry["X"] == 24 and geometry["Y"] == 24 else None
        evidence["recoveredOverlay"] = smoke.wait_until(relocated, timeout=8, message="Close control did not return to the active output")
        evidence["resizedMonitors"] = reader.monitors()
    finally:
        subprocess.run(restore, check=True, timeout=10)
        reader.close()
        (artifacts / "display-recovery.json").write_text(json.dumps(evidence, indent=2) + "\n")
    smoke.wait_until(lambda: window_geometry(overlay_window)["X"] == int(x) + 24, timeout=8)
    return "displaced close control recovers inside resized XFCE output and restored layout"


def close_with_stalled_status(cache, runtime, artifacts):
    from process_state import terminate_owned_process
    marker = str(runtime / "overlay.py")
    terminate_owned_process(cache / "overlay.pid", "overlay", marker)
    entered = artifacts / "status-worker-entered"
    entered.unlink(missing_ok=True)
    fixture_started = time.monotonic()
    with (artifacts / "stalled-overlay.log").open("w") as log:
        process = subprocess.Popen([sys.executable, __file__, "--stalled-overlay", marker, str(entered)],
                                   env={**os.environ, "HOME": str(cache.parent.parent)}, stdout=log, stderr=log)
    try:
        smoke.wait_until(lambda: entered.exists(), timeout=15, message="Stalled status fixture did not start")
        smoke.wait_until(lambda: value if (value := smoke.live_process_record(cache / "overlay.pid", "overlay")) and value.get("ready") is True else None,
                         timeout=5, message="Overlay blocked on its stalled status request")
        windows = smoke.wait_until(lambda: smoke.x11_window_ids("App Overlay"), timeout=5)
        started = time.monotonic()
        smoke.x11_click_overlay_close(windows[-1])
        process.wait(timeout=8)
        assert process.returncode == 0
        assert not smoke.live_process_record(cache / "tile-process.pid", "tile-process")
        return {"check": "real Tk close button works while status worker is stalled for 15 seconds",
                "fixtureStartSeconds": round(started - fixture_started, 3),
                "closeSeconds": round(time.monotonic() - started, 3)}
    finally:
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


def stalled_overlay(marker, entered):
    """Replace only the API transport in this disposable, real Tk process."""
    sys.path.insert(0, str(Path(marker).parent))
    import overlay
    def unavailable(_path, data=None):
        Path(entered).touch(mode=0o600)
        time.sleep(15)
        return {}
    overlay.api = unavailable
    sys.argv = [marker, "--mode", "local", "--tile-id", "desktop-smoke"]
    overlay.main()


if __name__ == "__main__":
    if len(sys.argv) != 4 or sys.argv[1] != "--stalled-overlay":
        raise SystemExit("Use system_package_smoke.py --recovery in a disposable desktop VM")
    stalled_overlay(sys.argv[2], sys.argv[3])
