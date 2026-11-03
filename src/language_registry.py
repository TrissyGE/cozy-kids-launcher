"""Shared list of enabled interface languages."""

import json
import re
import sys
from pathlib import Path


REGISTRY = json.loads(Path(__file__).with_suffix(".json").read_text(encoding="utf-8"))
DEFAULT_LANGUAGE = REGISTRY["default"]
LANGUAGE_CODES = tuple(entry["code"] for entry in REGISTRY["languages"])
if (
    DEFAULT_LANGUAGE not in LANGUAGE_CODES
    or len(set(LANGUAGE_CODES)) != len(LANGUAGE_CODES)
    or any(entry.get("direction", "ltr") not in ("ltr", "rtl") for entry in REGISTRY["languages"])
    or any(code == "auto" or not re.fullmatch(r"[a-z]{2,3}", code) for code in LANGUAGE_CODES)
):
    raise ValueError("Invalid interface language registry")


def language_direction(language):
    return next((entry.get("direction", "ltr") for entry in REGISTRY["languages"]
                 if entry["code"] == language), "ltr")


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--direction":
        print(language_direction(sys.argv[2]))
    else:
        print(DEFAULT_LANGUAGE)
        for entry in REGISTRY["languages"]:
            print(f'{entry["code"]}\t{entry["name"]}')
