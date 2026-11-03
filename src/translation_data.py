"""Load and validate the canonical installer and launcher translations."""

from collections import Counter
import json
from pathlib import Path
import re
import sys

from language_registry import DEFAULT_LANGUAGE, LANGUAGE_CODES


TRANSLATION_ROOT = Path(__file__).with_name("translations")
PLACEHOLDER = re.compile(r"\{[a-zA-Z_][a-zA-Z0-9_]*\}")


def unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate translation key: {key}")
        result[key] = value
    return result


def read_table(language):
    path = TRANSLATION_ROOT / f"{language}.json"
    table = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_keys)
    if not isinstance(table, dict) or not table:
        raise ValueError(f"{path.name}: expected a nonempty translation object")
    for key, value in table.items():
        if not re.fullmatch(r"[a-z0-9_]+", key):
            raise ValueError(f"{path.name}: invalid key {key!r}")
        if not isinstance(value, str) or not value.strip() or any(c in value for c in "\r\n\0"):
            raise ValueError(f"{path.name}: {key} must contain single-line text")
    return table


def load_translations(language):
    if language not in LANGUAGE_CODES:
        raise ValueError(f"Unsupported language: {language}")
    baseline = read_table(DEFAULT_LANGUAGE)
    if language == DEFAULT_LANGUAGE:
        return baseline
    translated = read_table(language)
    for key, value in translated.items():
        if key not in baseline:
            raise ValueError(f"{language}: unknown translation key {key}")
        if Counter(PLACEHOLDER.findall(value)) != Counter(PLACEHOLDER.findall(baseline[key])):
            raise ValueError(f"{language}: placeholders differ for {key}")
    return {**baseline, **translated}


if __name__ == "__main__":
    try:
        for key, value in load_translations(sys.argv[1]).items():
            print(f"{key}\t{value}")
    except (OSError, ValueError) as error:
        sys.exit(str(error))
