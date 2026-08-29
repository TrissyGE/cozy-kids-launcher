#!/usr/bin/env python3
"""Small synchronous Chrome DevTools driver shared by local browser tests."""

import base64
import json
import os
import signal
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket


BROWSER_CANDIDATES = (
    "google-chrome",
    "google-chrome-stable",
    "chromium",
    "chromium-browser",
)
KEY_DEFINITIONS = {
    "Tab": ("Tab", 9, ""),
    "Enter": ("Enter", 13, "\r"),
    "Escape": ("Escape", 27, ""),
    " ": ("Space", 32, " "),
    "ArrowLeft": ("ArrowLeft", 37, ""),
    "ArrowUp": ("ArrowUp", 38, ""),
    "ArrowRight": ("ArrowRight", 39, ""),
    "ArrowDown": ("ArrowDown", 40, ""),
}


def find_browser(preferred=None):
    candidates = (preferred,) if preferred else BROWSER_CANDIDATES
    for candidate in candidates:
        if candidate and shutil.which(candidate):
            return shutil.which(candidate)
    requested = preferred or ", ".join(BROWSER_CANDIDATES)
    raise RuntimeError(f"Supported Chromium browser not found: {requested}")


def wait_for_debug_port(profile, process, timeout):
    port_file = profile / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Chrome exited before DevTools was ready ({process.returncode})"
            )
        if port_file.is_file():
            lines = port_file.read_text(encoding="utf-8").splitlines()
            if lines:
                return int(lines[0])
        time.sleep(0.1)
    raise TimeoutError("Chrome DevTools port did not become ready")


def page_websocket_url(port, timeout):
    deadline = time.monotonic() + timeout
    endpoint = f"http://127.0.0.1:{port}/json/list"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=2) as response:
                targets = json.load(response)
            pages = [target for target in targets if target.get("type") == "page"]
            if pages:
                return pages[0]["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError("Chrome page target did not become ready")


def stop_process(process, process_group=False):
    if process.poll() is not None and not process_group:
        return
    if process_group and os.name == "posix":
        try:
            os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if process_group and os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        else:
            process.kill()
        process.wait(timeout=5)

    if process_group and os.name == "posix":
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                os.killpg(process.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


class DevTools:
    def __init__(self, url, timeout=25):
        self.socket = websocket.create_connection(
            url,
            timeout=timeout,
            origin="http://127.0.0.1",
            http_proxy_host=None,
        )
        self.next_id = 1

    def close(self):
        self.socket.close()

    def call(self, method, params=None):
        message_id = self.next_id
        self.next_id += 1
        self.socket.send(json.dumps({
            "id": message_id,
            "method": method,
            "params": params or {},
        }))
        while True:
            response = json.loads(self.socket.recv())
            if response.get("id") != message_id:
                continue
            if "error" in response:
                raise RuntimeError(f"DevTools {method} failed: {response['error']}")
            return response.get("result", {})


class BrowserSession:
    """Own a headless browser and expose deterministic DOM helpers."""

    def __init__(
        self,
        browser,
        url,
        profile,
        log_path,
        timeout=25,
        width=1280,
        height=800,
    ):
        self.browser = find_browser(browser)
        self.profile = Path(profile)
        self.log_path = Path(log_path)
        self.timeout = timeout
        self.width = width
        self.height = height
        self.process = None
        self.devtools = None
        self._log_handle = None
        try:
            self._start(url)
        except Exception:
            self.close()
            raise

    def _start(self, url):
        self.profile.mkdir(parents=True, exist_ok=True)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._log_handle = self.log_path.open("w", encoding="utf-8")
        environment = dict(os.environ)
        environment["NO_PROXY"] = "127.0.0.1,localhost"
        environment["no_proxy"] = "127.0.0.1,localhost"
        command = [
            self.browser,
            "--headless=new",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--disable-session-crashed-bubble",
            "--no-first-run",
            "--remote-allow-origins=http://127.0.0.1",
            "--remote-debugging-address=127.0.0.1",
            "--remote-debugging-port=0",
            f"--user-data-dir={self.profile}",
            f"--window-size={self.width},{self.height}",
        ]
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            command.append("--no-sandbox")
        command.append(url)
        self.process = subprocess.Popen(
            command,
            env=environment,
            stdout=self._log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=(os.name == "posix"),
        )
        port = wait_for_debug_port(self.profile, self.process, self.timeout)
        socket_url = page_websocket_url(port, self.timeout)
        self.devtools = DevTools(socket_url, timeout=self.timeout)
        self.devtools.call("Page.enable")
        self.devtools.call("Runtime.enable")
        self.set_device_metrics(self.width, self.height)

    def close(self):
        if self.devtools:
            try:
                self.devtools.call("Browser.close")
            except Exception:
                pass
            try:
                self.devtools.close()
            except Exception:
                pass
            self.devtools = None
        if self.process:
            stop_process(self.process, process_group=True)
            self.process = None
        if self._log_handle:
            self._log_handle.close()
            self._log_handle = None

    def evaluate(self, expression, await_promise=False):
        result = self.devtools.call("Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True,
            "awaitPromise": await_promise,
        })
        if "exceptionDetails" in result:
            details = result["exceptionDetails"]
            description = (
                details.get("exception", {}).get("description")
                or details.get("text")
                or "unknown JavaScript error"
            )
            raise RuntimeError(f"Browser JavaScript failed: {description}")
        return result.get("result", {}).get("value")

    def wait_for(self, expression, timeout=None, message=None):
        deadline = time.monotonic() + (self.timeout if timeout is None else timeout)
        while time.monotonic() < deadline:
            if self.evaluate(expression) is True:
                return
            time.sleep(0.1)
        raise TimeoutError(message or f"Browser condition stayed false: {expression}")

    def click(self, selector):
        encoded = json.dumps(selector)
        clicked = self.evaluate(
            "(() => { const element=document.querySelector(" + encoded + ");"
            " if(!element) return false; element.click(); return true; })()"
        )
        if clicked is not True:
            raise AssertionError(f"Browser element not found: {selector}")

    def set_value(self, selector, value):
        encoded_selector = json.dumps(selector)
        encoded_value = json.dumps(value)
        changed = self.evaluate(
            "(() => { const element=document.querySelector(" + encoded_selector + ");"
            " if(!element) return false; element.value=" + encoded_value + ";"
            " element.dispatchEvent(new Event('input',{bubbles:true}));"
            " element.dispatchEvent(new Event('change',{bubbles:true}));"
            " return true; })()"
        )
        if changed is not True:
            raise AssertionError(f"Browser element not found: {selector}")

    def set_device_metrics(self, width, height, mobile=False, device_scale_factor=1):
        self.width = int(width)
        self.height = int(height)
        self.devtools.call("Emulation.setDeviceMetricsOverride", {
            "width": self.width,
            "height": self.height,
            "deviceScaleFactor": device_scale_factor,
            "mobile": bool(mobile),
        })

    def set_emulated_media(self, features=None):
        self.devtools.call("Emulation.setEmulatedMedia", {
            "media": "",
            "features": [
                {"name": name, "value": value}
                for name, value in (features or [])
            ],
        })

    def key_press(self, key):
        try:
            code, virtual_key, text = KEY_DEFINITIONS[key]
        except KeyError as exc:
            raise ValueError(f"Unsupported test key: {key}") from exc
        event = {
            "key": key,
            "code": code,
            "windowsVirtualKeyCode": virtual_key,
            "nativeVirtualKeyCode": virtual_key,
        }
        if text:
            event["text"] = text
            event["unmodifiedText"] = text
        self.devtools.call("Input.dispatchKeyEvent", {"type": "keyDown", **event})
        self.devtools.call("Input.dispatchKeyEvent", {"type": "keyUp", **event})

    def insert_text(self, value):
        self.devtools.call("Input.insertText", {"text": str(value)})

    def touch_swipe(self, start_x, start_y, end_x, end_y):
        self.devtools.call("Emulation.setTouchEmulationEnabled", {
            "enabled": True,
            "maxTouchPoints": 1,
        })
        self.devtools.call("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": start_x, "y": start_y}],
        })
        self.devtools.call("Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [{"x": end_x, "y": end_y}],
        })
        self.devtools.call("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [],
        })

    def disable_touch_emulation(self):
        self.devtools.call("Emulation.setTouchEmulationEnabled", {"enabled": False})

    def screenshot(self, output):
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        result = self.devtools.call("Page.captureScreenshot", {
            "format": "png",
            "fromSurface": True,
            "captureBeyondViewport": False,
        })
        output.write_bytes(base64.b64decode(result["data"]))
        if output.stat().st_size < 1000:
            raise RuntimeError("Captured screenshot is unexpectedly small")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
