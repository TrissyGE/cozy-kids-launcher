#!/usr/bin/env python3
"""Generate browser locale JSON from the installer's canonical translations."""

import argparse
import json
import re
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = REPOSITORY_ROOT / "scripts" / "install.sh"
STATE_TEMPLATE = REPOSITORY_ROOT / "src" / "frontend" / "state.js"
LOCALE_ROOT = REPOSITORY_ROOT / "src" / "frontend" / "locales"

TEXT_CASE = re.compile(
    r'^\s+(de|en):([a-z0-9_]+)\) echo "(.*)" ;;$',
    re.MULTILINE,
)
TEXT_ASSIGNMENT = re.compile(
    r'^([A-Z0-9_]+)="\$\(text ([a-z0-9_]+)\)"$',
    re.MULTILINE,
)
JSON_ASSIGNMENT = re.compile(
    r'^JSON_([A-Z0-9_]+)="\$\(json_text "\$([A-Z0-9_]+)"\)"$',
    re.MULTILINE,
)
STATE_ENTRY = re.compile(
    r'^\s*([A-Za-z][A-Za-z0-9]*):\s*\{\{(JSON_[A-Z0-9_]+)\}\},?$',
    re.MULTILINE,
)

EXTRA_UI_KEYS = {
    "defaultTitle": "config_title",
    "defaultParentLabel": "parent_label",
    "defaultExitLabel": "exit_label",
    "defaultShutdownLabel": "shutdown_label",
    "layoutLarge": "layout_large",
    "layoutSmall": "layout_small",
    "timerExpiredTitle": "timer_expired_title",
    "timerExpiredBody": "timer_expired_body",
    "tilePaint": "tile_paint",
    "tileGames": "tile_games",
    "tileMusic": "tile_music",
    "tileBrowser": "tile_browser",
    "exportDiagnostics": "export_diagnostics",
    "mediaLibraryTitle": "media_library_title",
    "mediaLibraryHint": "media_library_hint",
    "mediaLibraryBack": "media_library_back",
    "mediaLibraryLoading": "media_library_loading",
    "mediaLibraryEmpty": "media_library_empty",
    "mediaLibraryError": "media_library_error",
    "mediaLibraryRetry": "media_library_retry",
    "mediaLibraryVideo": "media_library_video",
    "mediaLibraryAudio": "media_library_audio",
    "mediaLibraryPlay": "media_library_play",
    "mediaLibraryStarting": "media_library_starting",
    "mediaLibraryPlayError": "media_library_play_error",
    "mediaLibraryUnavailable": "media_library_unavailable",
    "mediaLibraryTruncated": "media_library_truncated",
}


def locale_payloads():
    installer = INSTALLER.read_text(encoding="utf-8")
    state = STATE_TEMPLATE.read_text(encoding="utf-8")
    translations = {"de": {}, "en": {}}
    for language, key, value in TEXT_CASE.findall(installer):
        translations[language][key] = value

    variable_to_text = dict(TEXT_ASSIGNMENT.findall(installer))
    json_to_variable = dict(JSON_ASSIGNMENT.findall(installer))
    ui_to_text = {}
    for ui_key, placeholder in STATE_ENTRY.findall(state):
        json_key = placeholder.removeprefix("JSON_")
        variable = json_to_variable.get(json_key)
        text_key = variable_to_text.get(variable, "")
        if not text_key:
            raise ValueError(f"Cannot map {placeholder} to an installer translation")
        ui_to_text[ui_key] = text_key
    ui_to_text.update(EXTRA_UI_KEYS)

    payloads = {}
    for language in ("de", "en"):
        missing = sorted(set(ui_to_text.values()) - set(translations[language]))
        if missing:
            raise ValueError(f"Missing {language} translations: {', '.join(missing)}")
        payloads[language] = {
            ui_key: translations[language][text_key]
            for ui_key, text_key in ui_to_text.items()
        }
    if payloads["de"].keys() != payloads["en"].keys():
        raise ValueError("German and English locale keys differ")
    return payloads


def serialized(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail if committed locale files do not match their sources",
    )
    args = parser.parse_args()
    payloads = locale_payloads()
    if args.check:
        stale = []
        for language, payload in payloads.items():
            path = LOCALE_ROOT / f"{language}.json"
            if not path.is_file() or path.read_text(encoding="utf-8") != serialized(payload):
                stale.append(str(path.relative_to(REPOSITORY_ROOT)))
        if stale:
            raise SystemExit("Stale locale files: " + ", ".join(stale))
        return

    LOCALE_ROOT.mkdir(parents=True, exist_ok=True)
    for language, payload in payloads.items():
        (LOCALE_ROOT / f"{language}.json").write_text(
            serialized(payload),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
