"""Shared locale lookup for the installed browser wrapper and native helpers."""

from functools import lru_cache
from html import escape
import json
from pathlib import Path
import re

from language_registry import DEFAULT_LANGUAGE, LANGUAGE_CODES, language_direction
from translation_data import load_translations


@lru_cache(maxsize=len(LANGUAGE_CODES))
def _locale(language):
    return load_translations(language)


def runtime_locale(language):
    if language in LANGUAGE_CODES:
        try:
            return language, _locale(language)
        except (OSError, ValueError):
            pass
    return DEFAULT_LANGUAGE, _locale(DEFAULT_LANGUAGE)


def saved_locale(config_path):
    try:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        language = config.get("language") if isinstance(config, dict) else None
    except (OSError, ValueError):
        language = None
    return runtime_locale(language)[1]


_WRAPPER_TOKEN = re.compile(r"\{\{(html|js)_([a-z_]+)\}\}")


def render_browser_wrapper(template, language):
    language, translations = runtime_locale(language)
    values = {**translations, "language": language, "direction": language_direction(language)}

    def replace(match):
        context, key = match.groups()
        value = values[key]
        if context == "html":
            return escape(value)
        return json.dumps(value, ensure_ascii=True).replace("<", "\\u003c")

    return _WRAPPER_TOKEN.sub(replace, template)
