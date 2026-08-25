#!/usr/bin/env python3
"""Probe configured web recommendations and report iframe-relevant headers."""

import argparse
import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path


USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0 Safari/537.36"
)


def web_target(recommendation):
    command = recommendation.get("cmd", [])
    if len(command) != 1:
        return None
    value = command[0]
    for prefix, mode in (
        ("special:browser:", "embedded"),
        ("special:external-browser:", "external"),
    ):
        if value.startswith(prefix):
            return mode, value[len(prefix):]
    return None


def probe(identifier, configured_mode, url, timeout):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    context = ssl.create_default_context()
    try:
        response = urllib.request.urlopen(request, timeout=timeout, context=context)
    except urllib.error.HTTPError as error:
        response = error
    except Exception as error:
        return {
            "id": identifier,
            "configuredMode": configured_mode,
            "url": url,
            "reachable": False,
            "error": f"{type(error).__name__}: {error}",
        }

    with response:
        headers = response.headers
        x_frame_options = headers.get("X-Frame-Options", "")
        content_security_policy = headers.get("Content-Security-Policy", "")
        frame_ancestors = ""
        for directive in content_security_policy.split(";"):
            if directive.strip().lower().startswith("frame-ancestors"):
                frame_ancestors = directive.strip()
                break
        return {
            "id": identifier,
            "configuredMode": configured_mode,
            "url": url,
            "reachable": 200 <= response.status < 400,
            "status": response.status,
            "finalUrl": response.geturl(),
            "xFrameOptions": x_frame_options,
            "frameAncestors": frame_ancestors,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--recommendations",
        type=Path,
        default=Path(__file__).resolve().parents[2] / "src" / "recommendations.json",
    )
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    recommendations = json.loads(args.recommendations.read_text(encoding="utf-8"))
    results = []
    for recommendation in recommendations:
        target = web_target(recommendation)
        if target:
            results.append(probe(recommendation["id"], *target, args.timeout))

    if args.json:
        json.dump(results, sys.stdout, ensure_ascii=False, indent=2)
        print()
        return

    print(f"{'ID':18} {'MODE':9} {'HTTP':5} {'IFRAME POLICY'}")
    print("-" * 88)
    for result in results:
        status = str(result.get("status", "ERR"))
        policy = result.get("xFrameOptions") or result.get("frameAncestors") or "not declared"
        print(f"{result['id']:18} {result['configuredMode']:9} {status:5} {policy[:52]}")
        if result.get("error"):
            print(f"  {result['error']}")


if __name__ == "__main__":
    main()

