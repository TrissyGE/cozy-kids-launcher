#!/usr/bin/env python3
"""The shared, non-publishing development/CI validation entry point."""

import argparse
import json
from pathlib import Path
import subprocess
import sys


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def source_files(root, suffix):
    return sorted(
        path
        for directory in ("src", "scripts", "tests", "examples")
        for path in (root / directory).rglob("*" + suffix)
    )


def validate_sources(root):
    """Discover new files automatically; do not execute Python templates."""
    for path in source_files(root, ".py"):
        compile(path.read_bytes(), str(path), "exec")
    for path in source_files(root, ".json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except ValueError as error:
            raise ValueError(f"{path}: {error}") from error
    # bash -n takes ONE script; subsequent filenames would be script arguments.
    for path in source_files(root, ".sh"):
        subprocess.run(["bash", "-n", str(path)], check=True, cwd=root)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only", choices=("static", "unit", "browser"),
        help="Run one group; by default run all three, failing on the first error.",
    )
    args = parser.parse_args()
    groups = (args.only,) if args.only else ("static", "unit", "browser")
    for group in groups:
        print(f"Checking {group}", flush=True)
        if group == "static":
            validate_sources(REPOSITORY_ROOT)
            command = [sys.executable, "scripts/generate-locales.py", "--check"]
        elif group == "unit":
            command = [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"]
        else:
            command = [sys.executable, "scripts/wsl/browser-e2e.py"]
        subprocess.run(command, cwd=REPOSITORY_ROOT, check=True)
    print("Checks passed", flush=True)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, SyntaxError, subprocess.CalledProcessError) as error:
        print(f"Checks failed: {error}", file=sys.stderr)
        sys.exit(1)
