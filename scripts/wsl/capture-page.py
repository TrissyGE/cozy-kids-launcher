#!/usr/bin/env python3
"""Capture a page through Chrome DevTools after a DOM readiness condition."""

import argparse
import base64
import json
import os
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path

import websocket


def wait_for_debug_port(profile, process, timeout):
    port_file = profile / "DevToolsActivePort"
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Chrome exited before DevTools was ready ({process.returncode})")
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


class DevTools:
    def __init__(self, url):
        self.socket = websocket.create_connection(
            url,
            timeout=5,
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


def stop_process(process):
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", required=True)
    parser.add_argument("--url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--ready-expression", default="document.readyState === 'complete'")
    parser.add_argument("--prepare-expression", default="")
    parser.add_argument("--timeout", type=float, default=25)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=800)
    args = parser.parse_args()

    browser = shutil.which(args.browser)
    if not browser:
        raise SystemExit(f"Browser not found: {args.browser}")
    args.profile.mkdir(parents=True, exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.unlink(missing_ok=True)

    environment = dict(os.environ)
    environment["NO_PROXY"] = "127.0.0.1,localhost"
    environment["no_proxy"] = "127.0.0.1,localhost"
    process = subprocess.Popen([
        browser,
        "--headless=new",
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--disable-session-crashed-bubble",
        "--no-first-run",
        "--remote-allow-origins=http://127.0.0.1",
        "--remote-debugging-address=127.0.0.1",
        "--remote-debugging-port=0",
        f"--user-data-dir={args.profile}",
        f"--window-size={args.width},{args.height}",
        args.url,
    ], env=environment)

    devtools = None
    try:
        port = wait_for_debug_port(args.profile, process, args.timeout)
        socket_url = page_websocket_url(port, args.timeout)
        devtools = DevTools(socket_url)
        devtools.call("Page.enable")
        devtools.call("Runtime.enable")
        devtools.call("Emulation.setDeviceMetricsOverride", {
            "width": args.width,
            "height": args.height,
            "deviceScaleFactor": 1,
            "mobile": False,
        })

        deadline = time.monotonic() + args.timeout
        ready = False
        while time.monotonic() < deadline:
            result = devtools.call("Runtime.evaluate", {
                "expression": args.ready_expression,
                "returnByValue": True,
            })
            ready = result.get("result", {}).get("value") is True
            if ready:
                break
            time.sleep(0.2)
        if not ready:
            raise TimeoutError(f"Readiness expression was false: {args.ready_expression}")

        if args.prepare_expression:
            prepared = devtools.call("Runtime.evaluate", {
                "expression": args.prepare_expression,
                "returnByValue": True,
                "awaitPromise": True,
            })
            if "exceptionDetails" in prepared:
                raise RuntimeError(
                    f"Preparation expression failed: {prepared['exceptionDetails']}"
                )

        time.sleep(0.5)
        screenshot = devtools.call("Page.captureScreenshot", {
            "format": "png",
            "fromSurface": True,
            "captureBeyondViewport": False,
        })
        args.output.write_bytes(base64.b64decode(screenshot["data"]))
        if args.output.stat().st_size < 1000:
            raise RuntimeError("Captured screenshot is unexpectedly small")
        print(f"Captured {args.output} ({args.output.stat().st_size} bytes)")
    finally:
        if devtools:
            devtools.close()
        stop_process(process)


if __name__ == "__main__":
    main()
