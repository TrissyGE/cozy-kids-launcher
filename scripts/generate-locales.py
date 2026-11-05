#!/usr/bin/env python3
"""Generate browser locale JSON from the canonical translation data."""

import argparse
import json
import re
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))
from language_registry import DEFAULT_LANGUAGE, LANGUAGE_CODES
from translation_data import PLACEHOLDER, load_translations, read_table, validate_translation

INSTALLER = REPOSITORY_ROOT / "scripts" / "install.sh"
STATE_TEMPLATE = REPOSITORY_ROOT / "src" / "frontend" / "state.js"
LOCALE_ROOT = REPOSITORY_ROOT / "src" / "frontend" / "locales"

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
    "retroBenchmarkTitle": "retro_benchmark_title",
    "retroBenchmarkGuide": "retro_benchmark_guide",
    "retroBenchmarkStart": "retro_benchmark_start",
    "retroBenchmarkCancel": "retro_benchmark_cancel",
    "retroBenchmarkClear": "retro_benchmark_clear",
    "retroBenchmarkRunning": "retro_benchmark_running",
    "retroBenchmarkMeasured": "retro_benchmark_measured",
    "retroBenchmarkPass": "retro_benchmark_pass",
    "retroBenchmarkLimited": "retro_benchmark_limited",
    "retroBenchmarkEmpty": "retro_benchmark_empty",
    "retroBenchmarkMissing": "retro_benchmark_missing",
    "retroBenchmarkBusy": "retro_benchmark_busy",
    "retroBenchmarkCanceled": "retro_benchmark_canceled",
    "retroBenchmarkInterrupted": "retro_benchmark_interrupted",
    "retroBenchmarkTimeout": "retro_benchmark_timeout",
    "retroBenchmarkFailed": "retro_benchmark_failed",
    "retroBenchmarkThroughput": "retro_benchmark_throughput",
    "retroBenchmarkLatency": "retro_benchmark_latency",
    "retroBenchmarkScopeCurrent": "retro_benchmark_scope_current",
    "retroBenchmarkScopeUnknown": "retro_benchmark_scope_unknown",
    "retroBenchmarkScopeStale": "retro_benchmark_scope_stale",
    "retroDeviceArchitecture": "retro_device_architecture",
    "retroDeviceDetails": "retro_device_details",
    "retroDeviceMeets": "retro_device_meets",
    "retroDeviceUnknown": "retro_device_unknown",
    "retroDeviceBelow": "retro_device_below",
    "retroDeviceMinimum": "retro_device_minimum",
    "retroDeviceObserved": "retro_device_observed",
    "retroDeviceVersion": "retro_device_version",
    "retroDeviceScope": "retro_device_scope",
    "folderSettingsTitle": "folder_settings_title",
    "folderSettingsHint": "folder_settings_hint",
    "folderNew": "folder_new",
    "folderAdd": "folder_add",
    "folderName": "folder_name",
    "folderIcon": "folder_icon",
    "folderAssign": "folder_assign",
    "folderHome": "folder_home",
    "folderOpen": "folder_open",
    "folderRemoveConfirm": "folder_remove_confirm",
    "updatePackageManaged": "update_package_managed",
    "adminRetro": "admin_retro",
    "retroEnabled": "retro_enabled",
    "retroCovers": "retro_covers",
    "retroLibraryEmpty": "retro_library_empty",
    "retroGuide": "retro_guide",
    "retroRoots": "retro_roots",
    "retroRefresh": "retro_refresh",
    "retroGame": "retro_game",
    "retroApprove": "retro_approve",
    "retroEmpty": "retro_empty",
    "retroSavesTitle": "retro_saves_title",
    "retroSavesEmpty": "retro_saves_empty",
    "retroSaveDownload": "retro_save_download",
    "retroSaveRemove": "retro_save_remove",
    "retroSaveConfirm": "retro_save_confirm",
    "retroSaveRemoved": "retro_save_removed",
    "retroSaveBusy": "retro_save_busy",
    "retroSaveError": "retro_save_error",
    "retroDeviceTitle": "retro_device_title",
    "retroDeviceGuide": "retro_device_guide",
    "retroDeviceRun": "retro_device_run",
    "retroDeviceChecking": "retro_device_checking",
    "retroDeviceFailed": "retro_device_failed",
    "retroDeviceUntested": "retro_device_untested",
    "retroDeviceLimited": "retro_device_limited",
    "retroDeviceIncompatible": "retro_device_incompatible",
    "retroDeviceCpu": "retro_device_cpu",
    "retroDeviceMemory": "retro_device_memory",
    "retroDeviceGraphics": "retro_device_graphics",
    "retroDeviceRouteAvailable": "retro_device_route_available",
    "retroDeviceRouteUnavailable": "retro_device_route_unavailable",
    "retroLimit": "retro_limit",
    "retroUnavailable": "retro_unavailable",
    "ps1BiosTitle": "ps1_bios_title",
    "ps1BiosGuide": "ps1_bios_guide",
    "ps1BiosLabel": "ps1_bios_label",
    "ps1BiosReady": "ps1_bios_ready",
    "ps1BiosMissing": "ps1_bios_missing",
    "ps1BiosInvalid": "ps1_bios_invalid",
    "ps1BiosRejected": "ps1_bios_rejected",
    "ps1BiosImported": "ps1_bios_imported",
    "ps1BiosImportError": "ps1_bios_import_error",
    "ps1CoreDownload": "ps1_core_download",
    "ps1CoreLabel": "ps1_core_label",
    "ps1CoreUnsupported": "ps1_core_unsupported",
    "ps1CoreRejected": "ps1_core_rejected",
    "ps1CoreError": "ps1_core_error",
    "controllerNavigationLabel": "controller_navigation_label",
    "controllerNavigationHint": "controller_navigation_hint",
    "browserHint": "browser_hint",
    "browserLabel": "cli_browser",
    "languageLabel": "cli_language",
    "paletteBgStart": "palette_bg_start",
    "paletteBgEnd": "palette_bg_end",
    "paletteText": "palette_text",
    "paletteButton": "palette_button",
    "paletteCard": "palette_card",
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
    "mediaLibraryViews": "media_library_views",
    "mediaLibraryAll": "media_library_all",
    "mediaLibraryFavorites": "media_library_favorites",
    "mediaLibraryRecents": "media_library_recents",
    "mediaLibraryFavoritesEmpty": "media_library_favorites_empty",
    "mediaLibraryRecentsEmpty": "media_library_recents_empty",
    "mediaLibraryFavoriteAdd": "media_library_favorite_add",
    "mediaLibraryFavoriteRemove": "media_library_favorite_remove",
    "mediaLibraryFavoriteError": "media_library_favorite_error",
    "mediaLibraryRefresh": "media_library_refresh",
    "mediaLibrarySourcesMissing": "media_library_sources_missing",
    "mediaRootsLabel": "media_roots_label",
    "mediaRootsHint": "media_roots_hint",
    "mediaRootsSave": "media_roots_save",
    "mediaRootsSaved": "media_roots_saved",
    "mediaRootsInvalid": "media_roots_invalid",
    "mediaRootsLoadError": "media_roots_load_error",
    "worldThemeOptions": "world_theme_options",
    "themeMotion": "theme_motion",
    "themeTimeOfDay": "theme_time_of_day",
    "worldThemeHint": "world_theme_hint",
}

UI_GROUPS = {
    "updateTrack": ("update_track", "label stable preview hint".split()),
    "budget": ("budget", (
        "label hint remaining nextAllowed exhausted unavailable request extraMinutes extend extendError "
        "newProfile copySource copy copyConfirm"
    ).split()),
    "packageMaintenance": ("package_maintenance", (
        "checkUpdate remove checking auth denied changes changed failed notInstalled noUpdate "
        "interrupted reconnecting unsupported updating removing keepOpen updateReview removeReview version versions "
        "consent removeConsent removeNow updateNow removed updated"
    ).split()),
    "themes": ("theme_name", (
        "rosa lila blau gruen regenbogen wald weltraum ocean dinosaurier "
        "baustelle prinzessin bauernhof katzen hunde custom"
    ).split()),
    "firstRun": ("first_run", (
        "progress languageTitle languageBody childTitle childBody childName childAvatar "
        "homeTitle appsTitle appsBody timeTitle timeBody appearanceTitle appearanceBody "
        "skip back next finish saving error nameRequired noApps large small languageError"
    ).split()),
    "profiles": ("profile", (
        "manageHint listTitle editorTitle name avatar launcherTitle createTitle create "
        "select active remove removeConfirm pickerTitle pickerHint close error "
        "nameRequired namePlaceholder avatarPlaceholder"
    ).split()),
}

COUNT_KEYS = {"catalogCount": "catalog_count", "packageCount": "package_count"}


def locale_payloads():
    installer = INSTALLER.read_text(encoding="utf-8")
    state = STATE_TEMPLATE.read_text(encoding="utf-8")
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
    required_keys = set(re.findall(r'\$\(text ([a-z0-9_]+)\)', installer))
    required_keys.update(ui_to_text.values())
    required_keys.update(key + "_one" for key in COUNT_KEYS.values())
    group_keys = {
        group: {
            field: prefix + "_" + re.sub(r"[A-Z]", lambda match: "_" + match[0].lower(), field)
            for field in fields
        }
        for group, (prefix, fields) in UI_GROUPS.items()
    }
    for fields in group_keys.values():
        required_keys.update(fields.values())
    baseline_keys = read_table(DEFAULT_LANGUAGE).keys()
    for language in LANGUAGE_CODES:
        untranslated = sorted(baseline_keys - read_table(language).keys())
        if untranslated:
            raise ValueError(f"Untranslated {language} keys: {', '.join(untranslated)}")
        translations = load_translations(language)
        missing = sorted(required_keys - translations.keys())
        if missing:
            raise ValueError(f"Missing {language} translations: {', '.join(missing)}")
        payloads[language] = {
            ui_key: translations[text_key]
            for ui_key, text_key in ui_to_text.items()
        }
        payloads[language].update({
            group: {field: translations[key] for field, key in fields.items()}
            for group, fields in group_keys.items()
        })
        payloads[language]["counts"] = {}
        for field, key in COUNT_KEYS.items():
            singular = translations[key + "_one"]
            if sorted(PLACEHOLDER.findall(singular)) != sorted(PLACEHOLDER.findall(translations[key])):
                raise ValueError(f"{language}: count placeholders differ for {key}")
            payloads[language]["counts"][field] = {"one": singular}
    return payloads


def serialized(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def main():
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--report", metavar="LANG",
        help="report missing source keys in an enabled language or an unregistered draft",
    )
    mode.add_argument(
        "--check",
        action="store_true",
        help="fail if committed locale files do not match their sources",
    )
    args = parser.parse_args()
    if args.report:
        language = args.report
        if not re.fullmatch(r"[a-z]{2,3}", language):
            parser.error("expected a two- or three-letter language code")
        baseline = read_table(DEFAULT_LANGUAGE)
        translated = read_table(language)
        validate_translation(language, baseline, translated)
        missing = sorted(baseline.keys() - translated.keys())
        state = "enabled" if language in LANGUAGE_CODES else "draft"
        print(f"{language} ({state}): {len(baseline) - len(missing)}/{len(baseline)} source keys")
        for key in missing:
            print(key)
        return
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
