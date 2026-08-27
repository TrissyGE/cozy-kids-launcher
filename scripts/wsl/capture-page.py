#!/usr/bin/env python3
"""Capture a page through Chrome DevTools after a DOM readiness condition."""

import argparse
import time
from pathlib import Path

from browser_driver import BrowserSession


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

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.unlink(missing_ok=True)
    log_path = args.output.with_suffix(".chrome.log")
    with BrowserSession(
        args.browser,
        args.url,
        args.profile,
        log_path,
        timeout=args.timeout,
        width=args.width,
        height=args.height,
    ) as browser:
        browser.wait_for(
            args.ready_expression,
            message=f"Readiness expression was false: {args.ready_expression}",
        )
        if args.prepare_expression:
            browser.evaluate(args.prepare_expression, await_promise=True)
        time.sleep(0.5)
        browser.screenshot(args.output)
        print(f"Captured {args.output} ({args.output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
