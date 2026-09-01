#!/usr/bin/env python3
"""Exercise core launcher journeys in a real Chromium browser."""

import argparse
import getpass
import http.server
import json
import os
import socket
import subprocess
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

from browser_driver import BrowserSession, find_browser, stop_process


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PIN = "2468"


class ReleaseFixtureHandler(http.server.BaseHTTPRequestHandler):
    latest_version = "0.0.0"
    mode = "ok"

    def do_GET(self):
        if self.mode != "ok":
            self.send_error(503, "synthetic update service failure")
            return
        if self.path == "/releases/latest":
            payload = json.dumps({
                "tag_name": f"v{self.latest_version}",
                "draft": False,
                "prerelease": False,
                "assets": [
                    {"name": f"cozy-kids-launcher-{self.latest_version}.tar.gz"},
                    {"name": "SHA256SUMS"},
                ],
            }).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        elif self.path == "/VERSION":
            payload = f"{self.latest_version}\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
        else:
            self.send_error(404)
            return
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format_string, *args):
        pass


def available_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def wait_for_server(url, process, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"Launcher server exited before becoming ready ({process.returncode})"
            )
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.load(response)
                if response.status == 200 and isinstance(payload, dict):
                    return
        except Exception:
            pass
        time.sleep(0.1)
    raise TimeoutError("Launcher server did not become ready")


def write_demo_config(config_path, browser_name):
    with config_path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    config.update({
        "language": "en",
        "setupCompleted": False,
        "parentLabel": "Parent",
        "exitLabel": "Exit kids mode",
        "pinHash": "",
        "autoScanDone": True,
        "browser": browser_name,
    })
    config["profiles"][0].update({
        "title": "E2E Home",
        "theme": "rosa",
        "layoutMode": "gross",
        "currentPage": 0,
        "timerMinutes": 0,
        "timerWarningMinutes": 5,
        "tiles": [
            {
                "id": "paint",
                "label": "Paint",
                "emoji": "🎨",
                "cmd": ["true"],
                "visible": True,
            },
            {
                "id": "music",
                "label": "Music",
                "emoji": "🎵",
                "cmd": ["true"],
                "visible": True,
            },
        ],
    })
    with config_path.open("w", encoding="utf-8") as handle:
        json.dump(config, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def assert_js(browser, expression, message):
    value = browser.evaluate(expression)
    if value is not True:
        raise AssertionError(f"{message} (expression returned {value!r})")


def log_scenario(name):
    print(f"  ✓ {name}", flush=True)


def enter_parent_settings(browser):
    browser.click("#parentBtn")
    browser.wait_for(
        "!document.getElementById('pin').classList.contains('hidden')",
        message="PIN dialog did not open",
    )
    browser.set_value("#pinInput", PIN)
    browser.click("#pin .save")
    browser.wait_for(
        "!document.getElementById('admin').classList.contains('hidden')",
        message="Correct PIN did not open Parent settings",
    )


def run_scenarios(browser, release_fixture, installed_version, artifacts):
    browser.wait_for(
        "typeof cfg !== 'undefined' && cfg !== null && "
        "bootstrapPromise===null && "
        "document.querySelectorAll('#grid .tile:not(.placeholder)').length === 2",
        message="Home screen did not finish rendering",
    )
    browser.wait_for(
        "!document.getElementById('firstRunOverlay').classList.contains('hidden') && "
        "document.documentElement.lang==='en' && "
        "document.activeElement.matches('.first-run-choice[aria-pressed=\"true\"]')",
        message="A fresh installation did not open the guided setup",
    )
    browser.set_device_metrics(800, 600)
    assert_js(
        browser,
        "window.innerWidth===800 && window.innerHeight===600 && "
        "document.documentElement.scrollWidth<=window.innerWidth && "
        "document.querySelector('.first-run-box').scrollWidth<="
        "document.querySelector('.first-run-box').clientWidth+1 && "
        "Array.from(document.querySelectorAll('#firstRunOverlay button:not([disabled])'))"
        ".every(button=>button.getBoundingClientRect().height>=44)",
        "Guided setup overflows or exposes undersized controls at 800x600",
    )
    browser.screenshot(artifacts / "first-run-800x600.png")
    browser.set_device_metrics(1440, 900)
    browser.click('.first-run-choice[data-language="de"]')
    browser.wait_for(
        "cfg.language==='de' && document.documentElement.lang==='de' && "
        "document.getElementById('firstRunTitle').textContent==='Willkommen bei Cozy Kids' && "
        "uiText.adminTitle==='Eltern-Einstellungen'",
        message="The setup language choice did not load the German interface locale",
    )
    browser.click('.first-run-choice[data-language="en"]')
    browser.wait_for(
        "cfg.language==='en' && document.documentElement.lang==='en' && "
        "document.getElementById('firstRunTitle').textContent==='Welcome to Cozy Kids' && "
        "uiText.adminTitle==='Parent settings'",
        message="The setup language choice did not restore the English interface locale",
    )
    browser.click("#firstRunNextBtn")
    browser.wait_for("document.getElementById('firstRunChildName')!==null")
    browser.set_value("#firstRunChildName", "Kiddo")
    browser.set_value("#firstRunChildAvatar", "🌈")
    browser.set_value("#firstRunHomeTitle", "E2E Home")
    browser.click("#firstRunNextBtn")
    browser.wait_for("document.querySelectorAll('#firstRunContent input[data-tile-id]').length===2")
    browser.click("#firstRunNextBtn")
    browser.wait_for("document.getElementById('firstRunTimerMinutes')!==null")
    browser.set_value("#firstRunTimerMinutes", "0")
    browser.click("#firstRunNextBtn")
    browser.wait_for("document.querySelector('#firstRunContent [data-theme=\"rosa\"]')!==null")
    browser.click('#firstRunContent [data-theme="rosa"]')
    browser.click('#firstRunContent [data-layout="gross"]')
    browser.screenshot(artifacts / "first-run-setup.png")
    browser.click("#firstRunNextBtn")
    browser.wait_for(
        "cfg.setupCompleted===true && "
        "document.getElementById('firstRunOverlay').classList.contains('hidden') && "
        "document.getElementById('title').textContent==='E2E Home'",
        message="Finishing guided setup did not persist and reveal the launcher",
    )
    saved_setup = browser.evaluate(
        "fetch('/api/config',{cache:'no-store'}).then(response=>response.json())",
        await_promise=True,
    )
    if saved_setup.get("setupCompleted") is not True:
        raise AssertionError(f"Guided setup was not persisted: {saved_setup!r}")
    log_scenario("guided first run covers language, child, apps, time, and appearance")
    assert_js(
        browser,
        "document.getElementById('title').textContent === 'E2E Home' && "
        "document.getElementById('kids').classList.contains('hidden') === false && "
        "Array.from(document.querySelectorAll('#grid .tile:not(.placeholder)'))"
        ".map(tile => tile.textContent.trim()).join('|').includes('Paint')",
        "Home title or tiles are incorrect",
    )
    log_scenario("home renders title and app tiles")

    icon_metrics = browser.evaluate(
        "({tiles:document.querySelectorAll('#grid .tile:not(.placeholder) .local-tile-icon').length,"
        "paths:document.querySelectorAll('#grid .tile:not(.placeholder) .local-tile-icon path').length,"
        "clock:document.querySelector('#clockBadge .ui-icon')!==null})"
    )
    if icon_metrics != {"tiles": 2, "paths": 7, "clock": True}:
        raise AssertionError(
            "Built-in tiles or launcher chrome did not use the local icon registry "
            f"({icon_metrics!r})"
        )
    browser.evaluate(
        "cfg.tiles.push({id:'custom-emoji',label:'Unicorn',emoji:'🦄',"
        "cmd:['true'],visible:true}); renderAll()"
    )
    assert_js(
        browser,
        "Array.from(document.querySelectorAll('#grid .tile')).some(tile => "
        "tile.textContent.includes('Unicorn') && "
        "tile.querySelector('.emoji').tagName==='SPAN' && "
        "tile.querySelector('.emoji').textContent==='🦄' && "
        "tile.querySelector('.local-tile-icon')===null)",
        "A custom emoji tile was replaced by the local icon registry",
    )
    browser.evaluate(
        "cfg.tiles=cfg.tiles.filter(tile=>tile.id!=='custom-emoji'); renderAll()"
    )
    log_scenario("local icons render built-ins while custom emoji remain text")

    browser.evaluate(
        "window.__cozyOriginalFetch=window.fetch.bind(window);"
        "window.__failConfigOnce=true;"
        "window.fetch=(input,options)=>{"
        " if(String(input)==='/api/config'&&window.__failConfigOnce){"
        "  window.__failConfigOnce=false;"
        "  return Promise.resolve(new Response('{}',{status:503,"
        "headers:{'Content-Type':'application/json'}}));"
        " }"
        " return window.__cozyOriginalFetch(input,options);"
        "};"
        "bootstrapLauncher()"
    )
    browser.wait_for(
        "document.getElementById('startupState') && "
        "document.getElementById('startupState').classList.contains('ui-state-error')",
        message="Failed config load did not render a recoverable startup error",
    )
    assert_js(
        browser,
        "cfg===null && document.getElementById('startupState').getAttribute('role')==='alert' && "
        "document.querySelector('.cornerbar').classList.contains('hidden') && "
        "document.querySelector('#startupState .ui-state-retry')!==null",
        "Startup error did not preserve a safe, actionable state",
    )
    browser.screenshot(artifacts / "startup-error.png")
    browser.click("#startupState .ui-state-retry")
    browser.wait_for(
        "cfg!==null && document.getElementById('startupState')===null && "
        "document.querySelectorAll('#grid .tile:not(.placeholder)').length===2 && "
        "!document.querySelector('.cornerbar').classList.contains('hidden')",
        message="Startup retry did not restore the launcher",
    )
    browser.evaluate(
        "window.fetch=window.__cozyOriginalFetch;"
        "delete window.__cozyOriginalFetch; delete window.__failConfigOnce"
    )
    log_scenario("startup failure renders an error and recovers in place")

    browser.click("#parentBtn")
    browser.wait_for("!document.getElementById('admin').classList.contains('hidden')")
    browser.click("[data-admin-section='system']")
    browser.set_value("#cfgPin", PIN)
    browser.set_value("#cfgPinConfirm", PIN)
    browser.click("#setPinBtn")
    browser.wait_for("cfg.pinConfigured === true")
    browser.click("#backBtn")

    browser.click("#parentBtn")
    browser.wait_for("!document.getElementById('pin').classList.contains('hidden')")
    browser.set_value("#pinInput", "0000")
    browser.click("#pin .save")
    browser.wait_for("document.getElementById('pinErr').textContent.length > 0")
    assert_js(
        browser,
        "document.getElementById('admin').classList.contains('hidden')",
        "Wrong PIN unexpectedly opened Parent settings",
    )
    browser.set_value("#pinInput", PIN)
    browser.click("#pin .save")
    browser.wait_for(
        "!document.getElementById('admin').classList.contains('hidden') && "
        "document.querySelectorAll('[data-admin-section]').length===6 && "
        "document.querySelectorAll('#adminNav .ui-icon').length===6 && "
        "document.querySelector('[data-admin-section=\"overview\"]')"
        ".getAttribute('aria-current')==='page'"
    )
    log_scenario("PIN setup rejects a wrong PIN and accepts the correct PIN")

    browser.click("[data-admin-section='appearance']")
    saved_theme = browser.evaluate("cfg.theme")
    saved_layout = browser.evaluate("cfg.layoutMode")
    browser.click("#openThemeBtn")
    browser.wait_for("!document.getElementById('themeOverlay').classList.contains('hidden')")
    chosen = browser.evaluate(
        "(() => { const index=ALL_THEMES.findIndex(theme => theme.id==='weltraum');"
        " const tiles=document.querySelectorAll('#themeChooser .theme-thumb');"
        " if(index < 0 || !tiles[index]) return false; tiles[index].click(); return true; })()"
    )
    if chosen is not True:
        raise AssertionError("Space theme could not be selected")
    assert_js(
        browser,
        "document.getElementById('appearancePreview').classList.contains('theme-weltraum') && "
        "document.getElementById('appearancePreview').style.background.includes('space.jpg') && "
        f"cfg.theme==={json.dumps(saved_theme)} && "
        f"document.body.classList.contains('theme-{saved_theme}')",
        "Theme preview changed the saved or active launcher theme",
    )
    browser.set_value("#cfgLayoutMode", "klein")
    assert_js(
        browser,
        "document.getElementById('appearancePreviewGrid').classList.contains('klein') && "
        "document.querySelectorAll('#appearancePreviewGrid .preview-tile').length===2 && "
        f"cfg.layoutMode==={json.dumps(saved_layout)}",
        "Layout preview changed the saved launcher layout",
    )
    browser.click("[data-admin-section='children']")
    browser.set_value("#cfgTitle", "Polished E2E Home")
    browser.set_value("#cfgParentLabel", "Family controls")
    assert_js(
        browser,
        "document.getElementById('appearancePreviewTitle').textContent==='Polished E2E Home'",
        "Title input did not update the isolated launcher preview",
    )
    browser.click("#saveBtn")
    browser.wait_for(
        "document.getElementById('admin').classList.contains('hidden') && "
        "document.body.classList.contains('theme-weltraum')",
        message="Saved settings were not applied to the home screen",
    )
    assert_js(
        browser,
        "document.getElementById('title').textContent === 'Polished E2E Home' && "
        "document.getElementById('grid').classList.contains('klein') && "
        "document.getElementById('parentBtn').textContent === 'Family controls'",
        "Title, layout, or parent label did not update",
    )
    saved_config = browser.evaluate(
        "fetch('/api/config',{cache:'no-store'}).then(response => response.json())",
        await_promise=True,
    )
    expected = {
        "title": "Polished E2E Home",
        "layoutMode": "klein",
        "theme": "weltraum",
        "parentLabel": "Family controls",
    }
    if any(saved_config.get(key) != value for key, value in expected.items()):
        raise AssertionError(f"Saved config does not match the UI: {saved_config!r}")
    log_scenario("settings and theme selection persist and re-render")

    enter_parent_settings(browser)
    browser.click("[data-admin-section='children']")
    browser.set_value("#newProfileName", "Alex")
    browser.set_value("#newProfileAvatar", "🚀")
    browser.click("#createProfileBtn")
    browser.wait_for(
        "cfg.activeProfileId!=='default' && cfg.name==='Alex' && "
        "cfg.profiles.length===2 && "
        "document.querySelectorAll('#profileList .profile-card').length===2",
        message="Creating a child profile did not activate and render it",
    )
    browser.screenshot(artifacts / "profile-management.png")
    alex_profile_id = browser.evaluate("cfg.activeProfileId")
    browser.set_value("#cfgProfileName", "Alex E2E")
    browser.set_value("#cfgProfileAvatar", "🪐")
    browser.set_value("#cfgTitle", "Alex's Space")
    browser.click("#saveBtn")
    browser.wait_for(
        "document.getElementById('admin').classList.contains('hidden') && "
        "cfg.name==='Alex E2E' && cfg.avatar==='🪐' && "
        "document.getElementById('title').textContent===\"Alex's Space\"",
        message="Profile edits were not persisted on the active home screen",
    )
    browser.click("#profileBtn")
    browser.wait_for(
        "!document.getElementById('profileOverlay').classList.contains('hidden') && "
        "document.querySelectorAll('#profilePickerGrid .profile-choice').length===2 && "
        "document.activeElement.matches('.profile-choice[aria-pressed=\"true\"]')",
        message="The child-facing profile picker did not open accessibly",
    )
    browser.screenshot(artifacts / "profile-picker.png")
    browser.click('.profile-choice[data-profile-id="default"]')
    browser.wait_for(
        "!document.getElementById('pin').classList.contains('hidden') && "
        "document.activeElement.id==='pinInput'",
        message="A child-facing profile switch bypassed Parent PIN confirmation",
    )
    browser.set_value("#pinInput", PIN)
    browser.click("#pin .save")
    browser.wait_for(
        "cfg.activeProfileId==='default' && "
        "document.getElementById('profileOverlay').classList.contains('hidden') && "
        "document.getElementById('title').textContent==='Polished E2E Home'",
        message="The confirmed profile switch did not restore the separate profile",
    )
    enter_parent_settings(browser)
    browser.click("[data-admin-section='children']")
    delete_selector = (
        f'.profile-card[data-profile-id={json.dumps(alex_profile_id)}] .danger'
    )
    browser.click(delete_selector)
    browser.wait_for(
        "!document.getElementById('confirmOverlay').classList.contains('hidden')",
        message="Profile deletion did not use the shared confirmation dialog",
    )
    browser.click("#confirmActionBtn")
    browser.wait_for(
        "cfg.profiles.length===1 && "
        "document.querySelectorAll('#profileList .profile-card').length===1",
        message="The inactive child profile was not deleted",
    )
    browser.click("#backBtn")
    log_scenario("profile creation, editing, PIN-gated selection, and deletion work end to end")

    enter_parent_settings(browser)
    browser.click("[data-admin-section='apps']")
    browser.evaluate(
        "cfg.layoutMode='gross'; cfg.tiles=cfg.tiles.concat(["
        "{id:'reading-filter',label:'Reading',emoji:'📚',cmd:['true'],visible:true},"
        "{id:'puzzles-filter',label:'Puzzles',emoji:'🧩',cmd:['true'],visible:true},"
        "{id:'drawing-filter',label:'Drawing',emoji:'✏️',cmd:['true'],visible:true}"
        "]); renderAdmin()"
    )
    browser.wait_for(
        "document.getElementById('adminPageNav').children.length===3",
        message="Unfiltered app editor did not paginate its five tiles",
    )
    browser.set_value("#tileSearch", "Paint")
    browser.wait_for(
        "Array.from(document.querySelectorAll('#forms .tileform'))"
        ".filter(row => getComputedStyle(row).display!=='none').length===1 && "
        "document.getElementById('adminTileResultCount').textContent.includes('1') && "
        "document.getElementById('adminPageNav').children.length===0",
        message="App search did not narrow the editor list",
    )
    browser.click("#bulkSelectFiltered")
    assert_js(
        browser,
        "adminSelectedTileIds.size===1 && "
        "document.getElementById('bulkHideTilesBtn').disabled===false",
        "Selecting filtered app results did not enable bulk actions",
    )
    browser.click("#bulkHideTilesBtn")
    browser.wait_for(
        "cfg.tiles[0].visible===false && adminSelectedTileIds.size===0",
        message="Bulk hide did not update the selected tile",
    )
    browser.set_value("#tileVisibilityFilter", "hidden")
    browser.wait_for(
        "filteredAdminTileIndexes().length===1 && "
        "document.querySelector('#forms .tileform input:nth-of-type(2)').value==='Paint'",
        message="Visibility filter did not isolate the bulk-hidden tile",
    )
    browser.click(
        "#forms .tileform[style*='display: grid'] .tile-select-toggle input"
    )
    browser.click("#bulkShowTilesBtn")
    browser.wait_for(
        "cfg.tiles[0].visible===true && "
        "!document.getElementById('adminTileEmptyState').hidden",
        message="Bulk show did not refresh the active hidden filter",
    )
    browser.set_value("#tileVisibilityFilter", "all")
    browser.set_value("#tileSearch", "no matching tile")
    browser.wait_for(
        "!document.getElementById('adminTileEmptyState').hidden && "
        "Array.from(document.querySelectorAll('#forms .tileform'))"
        ".every(row => getComputedStyle(row).display==='none')",
        message="Empty search results did not expose their status",
    )
    browser.set_value("#tileSearch", "Drawing")
    browser.wait_for(
        "filteredAdminTileIndexes().length===1",
        message="Synthetic tile was not available for bulk deletion",
    )
    browser.click(
        "#forms .tileform[style*='display: grid'] .tile-select-toggle input"
    )
    browser.evaluate("document.getElementById('bulkDeleteTilesBtn').focus()")
    browser.click("#bulkDeleteTilesBtn")
    browser.wait_for(
        "!document.getElementById('confirmOverlay').classList.contains('hidden') && "
        "document.activeElement.id==='confirmCancelBtn' && cfg.tiles.length===5",
        message="Bulk delete did not open the shared confirmation dialog safely",
    )
    browser.key_press("Escape")
    browser.wait_for(
        "document.getElementById('confirmOverlay').classList.contains('hidden') && "
        "document.activeElement.id==='bulkDeleteTilesBtn' && cfg.tiles.length===5",
        message="Confirmation cancellation did not restore focus and preserve tiles",
    )
    browser.click("#bulkDeleteTilesBtn")
    browser.wait_for("document.activeElement.id==='confirmCancelBtn'")
    browser.screenshot(artifacts / "confirmation-dialog.png")
    browser.key_press("Tab")
    assert_js(
        browser,
        "document.activeElement.id==='confirmActionBtn'",
        "Confirmation tab order did not reach its action",
    )
    browser.key_press("Tab")
    assert_js(
        browser,
        "document.activeElement.id==='confirmCancelBtn'",
        "Confirmation dialog did not keep keyboard focus contained",
    )
    browser.click("#confirmActionBtn")
    browser.wait_for(
        "cfg.tiles.length===4 && !cfg.tiles.some(tile => tile.id==='drawing-filter') && "
        "!document.getElementById('adminTileEmptyState').hidden && "
        "filteredAdminTileIndexes().length===0",
        message="Bulk delete did not remove the selected tile or refresh results",
    )
    browser.evaluate(
        "cfg.tiles=cfg.tiles.slice(0,2); cfg.layoutMode='klein'; "
        "adminTileQuery=''; adminTileVisibility='all'; adminPage=0; renderAdmin()"
    )
    log_scenario("app search, filtering, bulk actions, and empty results stay local")

    browser.evaluate(
        "window.__cozyOriginalFetch=window.fetch.bind(window);"
        "window.fetch=(input,options)=>{"
        " if(String(input)==='/api/recommendations') return new Promise((resolve,reject)=>{"
        "  window.__rejectRecommendations=reject;"
        " });"
        " return window.__cozyOriginalFetch(input,options);"
        "};"
        "loadRecommendations()"
    )
    browser.wait_for(
        "recommendationState==='loading' && "
        "document.getElementById('recommendationState').getAttribute('aria-busy')==='true'",
        message="Recommendation refresh did not expose its loading state",
    )
    browser.evaluate("window.__rejectRecommendations(new Error('synthetic failure'))")
    browser.wait_for(
        "recommendationState==='error' && "
        "document.getElementById('recommendationState').classList.contains('ui-state-error') && "
        "document.querySelector('#recommendationState .ui-state-retry')!==null",
        message="Recommendation failure did not expose an actionable error state",
    )
    browser.screenshot(artifacts / "recommendations-error.png")
    browser.evaluate(
        "window.fetch=(input,options)=>String(input)==='/api/recommendations'"
        " ? Promise.resolve(new Response('[]',{status:200,"
        "headers:{'Content-Type':'application/json'}}))"
        " : window.__cozyOriginalFetch(input,options)"
    )
    browser.click("#recommendationState .ui-state-retry")
    browser.wait_for(
        "recommendationState==='empty' && "
        "document.getElementById('recommendationState').classList.contains('ui-state-empty')",
        message="Empty recommendations did not render a clear empty state",
    )
    browser.evaluate(
        "window.fetch=window.__cozyOriginalFetch;"
        "delete window.__cozyOriginalFetch; delete window.__rejectRecommendations;"
        "loadRecommendations()"
    )
    browser.wait_for(
        "recommendationState==='ready' && document.getElementById('recommendationState')===null",
        message="Recommendation retry did not restore the populated state",
    )
    log_scenario("recommendations expose loading, error, empty, and recovery states")

    browser.click("[data-admin-section='screen-time']")
    browser.click("#appScheduleEnabled")
    browser.wait_for(
        "cfg.appAvailability[selectedAppScheduleId].enabled===true && "
        "document.querySelectorAll('#appScheduleDays .schedule-window').length===7",
        message="Enabling a per-app schedule did not create editable weekly defaults",
    )
    assert_js(
        browser,
        "document.querySelector('[data-admin-panel=\"screen-time\"]')"
        ".scrollWidth<=document.querySelector('[data-admin-panel=\"screen-time\"]')"
        ".clientWidth+1 && "
        "document.querySelector('.schedule-settings-grid').scrollWidth<="
        "document.querySelector('.schedule-settings-grid').clientWidth+1",
        "Schedule controls require horizontal scrolling",
    )
    browser.screenshot(artifacts / "schedule-editor.png")
    browser.evaluate(
        "cfg.appAvailability[selectedAppScheduleId]={enabled:true,days:{}};"
        "renderScheduleControls()"
    )
    browser.click("#saveBtn")
    browser.wait_for(
        "document.getElementById('admin').classList.contains('hidden') && "
        "availabilityStatus.profileAllowed===true && "
        "availabilityStatus.blockedTileIds.includes(cfg.tiles[0].id) && "
        "document.querySelector('#grid .tile.unavailable')!==null",
        message="The saved app schedule did not mark its tile unavailable",
    )
    browser.click("#grid .tile.unavailable")
    browser.wait_for(
        "!document.getElementById('availabilityBlock').classList.contains('hidden') && "
        "document.getElementById('availabilityBlock').dataset.reason==='app_schedule' && "
        "document.activeElement.id==='availabilityBlockClose'",
        message="An unavailable app did not explain its blocked state accessibly",
    )
    browser.screenshot(artifacts / "app-schedule-blocked.png")
    browser.click("#availabilityBlockClose")

    enter_parent_settings(browser)
    browser.click("[data-admin-section='screen-time']")
    browser.click("#clearAppScheduleBtn")
    browser.click("#weeklyScheduleEnabled")
    browser.wait_for(
        "cfg.weeklySchedule.enabled===true && "
        "document.querySelectorAll('#weeklyScheduleDays .schedule-window').length===7",
        message="Enabling the weekly schedule did not create editable daily defaults",
    )
    browser.evaluate("cfg.weeklySchedule={enabled:true,days:{}};renderScheduleControls()")
    browser.click("#saveBtn")
    browser.wait_for(
        "document.getElementById('admin').classList.contains('hidden') && "
        "availabilityStatus.profileAllowed===false && "
        "!document.getElementById('availabilityBlock').classList.contains('hidden') && "
        "document.getElementById('availabilityBlock').dataset.reason==='profile_schedule' && "
        "document.getElementById('availabilityBlockClose').hidden===true",
        message="The profile-wide schedule did not block the launcher",
    )
    browser.screenshot(artifacts / "weekly-schedule-blocked.png")
    browser.click("#availabilityParentsBtn")
    browser.wait_for("!document.getElementById('pin').classList.contains('hidden')")
    browser.set_value("#pinInput", PIN)
    browser.click("#pin .save")
    browser.wait_for("!document.getElementById('admin').classList.contains('hidden')")
    browser.click("[data-admin-section='screen-time']")
    browser.click("#weeklyScheduleEnabled")
    browser.click("#saveBtn")
    browser.wait_for(
        "availabilityStatus.profileAllowed===true && "
        "document.getElementById('availabilityBlock').classList.contains('hidden')",
        message="Disabling the weekly schedule did not restore launcher availability",
    )
    log_scenario("weekly and per-app schedules persist and explain blocked states")

    enter_parent_settings(browser)
    browser.click("[data-admin-section='screen-time']")
    browser.set_value("#cfgTimerMinutes", "15")
    browser.click("#timerToggleBtn")
    browser.wait_for(
        "lastTimerStatus.active === true && lastTimerStatus.expired === false && "
        "document.getElementById('timerBadge').style.display === 'block'",
        message="Timer did not become active",
    )
    assert_js(
        browser,
        "document.getElementById('timerBadge').textContent.includes('15') || "
        "document.getElementById('timerBadge').textContent.includes('14')",
        "Timer badge does not show the remaining time",
    )
    browser.click("#timerToggleBtn")
    browser.wait_for(
        "lastTimerStatus.active === false && "
        "document.getElementById('timerBadge').style.display === 'none'",
        message="Timer did not stop cleanly",
    )
    log_scenario("screen timer starts, renders its badge, and stops")

    release_fixture.latest_version = installed_version
    release_fixture.mode = "ok"
    browser.click("[data-admin-section='system']")
    browser.click("#checkUpdateBtn")
    browser.wait_for(
        "document.getElementById('checkUpdateBtn').disabled === false && "
        "document.querySelector('#updateMsg .ui-state-message').textContent === uiText.updateUpToDate",
        message="Up-to-date check did not finish",
    )
    assert_js(
        browser,
        "document.querySelector('#updateMsg .ui-state-message').textContent === uiText.updateUpToDate && "
        "document.getElementById('updateRow').style.display === 'none'",
        "Up-to-date state was not rendered",
    )

    installed_major = int(installed_version.split(".", maxsplit=1)[0])
    available_version = f"{installed_major + 1}.0.0"
    release_fixture.latest_version = available_version
    browser.click("#checkUpdateBtn")
    encoded_available = json.dumps(available_version)
    browser.wait_for(
        "document.getElementById('checkUpdateBtn').disabled === false && "
        f"document.getElementById('updateMsg').textContent.includes({encoded_available})",
        message="Available-update check did not finish",
    )
    update_message = browser.evaluate("document.getElementById('updateMsg').textContent")
    update_visible = browser.evaluate(
        "document.getElementById('updateRow').style.display === 'grid'"
    )
    if available_version not in update_message or update_visible is not True:
        raise AssertionError("Available-update state was not rendered")

    release_fixture.mode = "error"
    browser.click("#checkUpdateBtn")
    browser.wait_for(
        "document.getElementById('checkUpdateBtn').disabled === false && "
        "document.querySelector('#updateMsg .ui-state-message').textContent === uiText.updateError",
        message="Failed update check did not finish",
    )
    assert_js(
        browser,
        "document.querySelector('#updateMsg .ui-state-message').textContent === uiText.updateError && "
        "document.getElementById('updateRow').style.display === 'none' && "
        "document.getElementById('checkUpdateBtn').disabled === false && "
        "document.querySelector('#updateMsg .ui-state-retry')!==null",
        "Update error state was not rendered or did not recover",
    )
    log_scenario("update check renders current, available, and error states")


def run_accessibility_scenarios(browser, artifacts):
    prepared = browser.evaluate(
        "(() => {"
        " if(!document.getElementById('admin').classList.contains('hidden')) closeAdmin();"
        " cfg.layoutMode='gross'; cfg.currentPage=0;"
        " cfg.tiles=cfg.tiles.slice(0,2).concat(["
        "  {id:'reading',label:'Reading',emoji:'📚',cmd:['true'],visible:true},"
        "  {id:'puzzles',label:'Puzzles',emoji:'🧩',cmd:['true'],visible:true},"
        "  {id:'drawing',label:'Drawing',emoji:'✏️',cmd:['true'],visible:true}"
        " ]); focusedTileIndex=0; renderAll();"
        " return visibleTiles().length===5 && pageCount()===2 && "
        "document.querySelectorAll('#grid .tile:not(.placeholder)').length===4;"
        "})()"
    )
    if prepared is not True:
        raise AssertionError("Accessibility fixture did not create a second page")

    assert_js(
        browser,
        "document.activeElement===document.querySelector('#grid .tile:not(.placeholder)')",
        "Home keyboard focus did not start on the first tile",
    )
    browser.key_press("ArrowRight")
    assert_js(
        browser,
        "document.activeElement===document.querySelectorAll('#grid .tile:not(.placeholder)')[1] && "
        "document.activeElement.classList.contains('focused')",
        "Arrow navigation did not move real focus to the next tile",
    )
    browser.key_press("ArrowLeft")
    browser.key_press("Tab")
    assert_js(
        browser,
        "document.activeElement===document.querySelectorAll('#grid .tile:not(.placeholder)')[1] && "
        "document.activeElement.classList.contains('focused') && focusedTileIndex===1",
        "Tab navigation did not synchronize real and visual tile focus",
    )
    browser.key_press("Enter")
    browser.wait_for(
        "!document.getElementById('startOverlay').classList.contains('hidden') && "
        "document.getElementById('startText').textContent.includes(tilesForPage(cfg.currentPage)[1].label)",
        message="Keyboard activation did not launch the focused tile",
    )
    browser.wait_for(
        "document.getElementById('startOverlay').classList.contains('hidden')",
        timeout=3,
    )
    for _ in range(10):
        if browser.evaluate("document.activeElement.id==='parentBtn'") is True:
            break
        browser.key_press("Tab")
    else:
        raise AssertionError("Tab navigation did not reach Parent settings")
    browser.key_press("Enter")
    browser.wait_for(
        "!document.getElementById('pin').classList.contains('hidden') && "
        "document.activeElement.id==='pinInput'",
        message="Keyboard activation did not focus the PIN dialog",
    )
    browser.insert_text(PIN)
    browser.key_press("Enter")
    browser.wait_for(
        "!document.getElementById('admin').classList.contains('hidden') && "
        "document.activeElement.id==='adminNavOverview' && "
        "document.querySelector('[data-admin-panel=\"overview\"]')"
        ".hidden===false",
        message="Keyboard PIN submission did not focus the Parent overview",
    )
    for _ in range(4):
        browser.key_press("ArrowRight")
    assert_js(
        browser,
        "document.activeElement.id==='adminNavAppearance' && "
        "document.querySelector('[data-admin-panel=\"appearance\"]')"
        ".hidden===false",
        "Arrow navigation did not activate the Appearance section",
    )
    browser.key_press("Tab")
    assert_js(
        browser,
        "document.activeElement.id==='openThemeBtn'",
        "Appearance tab order did not reach the theme picker",
    )
    browser.key_press("Enter")
    browser.wait_for(
        "!document.getElementById('themeOverlay').classList.contains('hidden') && "
        "document.activeElement.matches('#themeChooser .theme-thumb')",
        message="Theme picker did not focus its first semantic button",
    )
    assert_js(
        browser,
        "Array.from(document.querySelectorAll('#themeChooser .theme-thumb')).every(button => "
        "button.tagName==='BUTTON' && button.type==='button' && button.getAttribute('aria-label'))",
        "Theme choices are not exposed as labelled buttons",
    )
    browser.key_press("Tab")
    browser.key_press("Enter")
    browser.wait_for(
        "document.getElementById('themeOverlay').classList.contains('hidden') && "
        "document.getElementById('cfgTheme').value==='lila' && "
        "document.activeElement.id==='openThemeBtn'",
        message="Keyboard theme selection did not return focus to its trigger",
    )
    browser.key_press("Escape")
    browser.wait_for(
        "document.getElementById('admin').classList.contains('hidden') && "
        "document.activeElement.matches('#grid .tile:not(.placeholder)')",
        message="Escape did not return from Parent settings to the tile grid",
    )
    log_scenario("keyboard-only flow keeps real focus and operates Parent settings")

    browser.evaluate("cfg.currentPage=0; focusedTileIndex=0; renderAll()")
    browser.touch_swipe(700, 400, 100, 400)
    browser.wait_for("cfg.currentPage===1", message="Left swipe did not advance the page")
    browser.touch_swipe(100, 400, 700, 400)
    browser.wait_for("cfg.currentPage===0", message="Right swipe did not return the page")
    browser.evaluate("showPin()")
    browser.touch_swipe(700, 400, 100, 400)
    assert_js(
        browser,
        "cfg.currentPage===0",
        "Touch navigation changed the hidden home page behind a modal",
    )
    browser.key_press("Escape")
    browser.disable_touch_emulation()
    assert_js(
        browser,
        "document.getElementById('pin').classList.contains('hidden') && "
        "document.activeElement.matches('#grid .tile:not(.placeholder)')",
        "Closing the PIN dialog did not restore home focus",
    )
    log_scenario("touch swipes navigate pages and stop at modal boundaries")

    browser.set_emulated_media([("prefers-reduced-motion", "reduce")])
    assert_js(
        browser,
        "matchMedia('(prefers-reduced-motion: reduce)').matches && "
        "parseFloat(getComputedStyle(document.querySelector('.tile')).transitionDuration)<=0.001 && "
        "parseFloat(getComputedStyle(document.querySelector('.startbox .emoji')).animationDuration)<=0.001",
        "Reduced-motion preference did not suppress launcher movement",
    )
    log_scenario("reduced-motion preference suppresses transitions and animations")

    browser.set_emulated_media([("forced-colors", "active")])
    assert_js(
        browser,
        "matchMedia('(forced-colors: active)').matches && "
        "getComputedStyle(document.querySelector('.tile')).borderTopStyle==='solid' && "
        "parseFloat(getComputedStyle(document.querySelector('.tile')).borderTopWidth)>=2 && "
        "getComputedStyle(document.querySelector('.tile')).boxShadow==='none'",
        "Forced-colors mode did not expose bounded high-contrast controls",
    )
    browser.screenshot(artifacts / "forced-colors.png")
    log_scenario("forced-colors mode keeps controls bounded and visible")

    browser.set_emulated_media()
    browser.set_device_metrics(800, 600)
    browser.evaluate("cfg.currentPage=0; focusedTileIndex=0; renderAll()")
    assert_js(
        browser,
        "window.innerWidth===800 && window.innerHeight===600 && "
        "document.documentElement.scrollWidth<=window.innerWidth && "
        "Array.from(document.querySelectorAll('#kids .tile:not(.placeholder),.cornerbar button,.nav:not(.hidden)'))"
        ".every(element => { const r=element.getBoundingClientRect(); return r.width>=44 && "
        "r.height>=44 && r.left>=0 && r.right<=window.innerWidth && r.top>=0 && r.bottom<=window.innerHeight; })",
        "The 800x600 home layout clipped content or touch targets",
    )
    browser.screenshot(artifacts / "low-resolution-home.png")
    browser.evaluate("enterAdmin()")
    assert_js(
        browser,
        "document.documentElement.scrollWidth<=window.innerWidth && "
        "document.querySelector('#admin .wrap').scrollWidth<=document.querySelector('#admin .wrap').clientWidth+1 && "
        "getComputedStyle(document.querySelector('#admin .wrap')).overflowY==='auto' && "
        "document.getElementById('adminTitle').getBoundingClientRect().top>=64 && "
        "document.querySelectorAll('[data-admin-section]').length===6 && "
        "Array.from(document.querySelectorAll('[data-admin-section]')).every(button => "
        "button.getBoundingClientRect().height>=44) && "
        "document.querySelector('.cornerbar').classList.contains('hidden') && "
        "document.getElementById('navLeft').classList.contains('hidden') && "
        "document.getElementById('navRight').classList.contains('hidden')",
        "The 800x600 Parent layout requires horizontal scrolling",
    )
    for section in (
        "overview",
        "children",
        "apps",
        "screen-time",
        "appearance",
        "system",
    ):
        panel_selector = json.dumps(f'[data-admin-panel="{section}"]')
        metrics = browser.evaluate(
            "(() => { activateAdminSection(" + json.dumps(section) + "); "
            "const panel=document.querySelector(" + panel_selector + "); "
            "const wrap=document.querySelector('#admin .wrap'); "
            "return {hidden:panel.hidden,panelScroll:panel.scrollWidth,"
            "panelClient:panel.clientWidth,wrapScroll:wrap.scrollWidth,"
            "wrapClient:wrap.clientWidth}; })()"
        )
        if (
            metrics["hidden"]
            or metrics["panelScroll"] > metrics["panelClient"] + 1
            or metrics["wrapScroll"] > metrics["wrapClient"] + 1
        ):
            raise AssertionError(
                f"Parent section {section!r} overflows at 800x600: {metrics!r}"
            )
    browser.evaluate(
        "activateAdminSection('appearance'); document.querySelector('#admin .wrap').scrollTop=0"
    )
    browser.screenshot(artifacts / "low-resolution-appearance.png")
    browser.evaluate(
        "activateAdminSection('apps'); document.querySelector('#admin .wrap').scrollTop=0"
    )
    browser.screenshot(artifacts / "low-resolution-apps.png")
    browser.evaluate("activateAdminSection('overview')")
    browser.screenshot(artifacts / "low-resolution-parent.png")
    browser.key_press("Escape")
    assert_js(
        browser,
        "!document.querySelector('.cornerbar').classList.contains('hidden')",
        "Closing Parent settings did not restore the home controls",
    )
    browser.set_device_metrics(1440, 900)
    log_scenario("800x600 home and Parent flows avoid clipping and horizontal scroll")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--browser", help="Chromium-family executable name")
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=REPOSITORY_ROOT / ".test-artifacts" / "browser-e2e",
    )
    parser.add_argument("--timeout", type=float, default=25)
    args = parser.parse_args()

    browser_path = find_browser(args.browser)
    browser_name = Path(browser_path).name
    args.artifacts.mkdir(parents=True, exist_ok=True)
    print(f"Browser E2E: {browser_path}", flush=True)

    release_server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        ReleaseFixtureHandler,
    )
    release_thread = threading.Thread(target=release_server.serve_forever, daemon=True)
    release_thread.start()
    release_port = release_server.server_address[1]

    server_process = None
    server_log = None
    try:
        with tempfile.TemporaryDirectory(prefix="cozy-kids-browser-e2e-") as temp_dir:
            test_home = Path(temp_dir)
            install_log_path = args.artifacts / "install.log"
            with install_log_path.open("w", encoding="utf-8") as install_log:
                subprocess.run(
                    [
                        "bash",
                        "scripts/install.sh",
                        "--user",
                        getpass.getuser(),
                        "--home",
                        str(test_home),
                        "--lang",
                        "en",
                        "--browser",
                        browser_name,
                        "--launch-mode",
                        "window",
                        "--skip-browser-check",
                        "--force",
                    ],
                    cwd=REPOSITORY_ROOT,
                    stdout=install_log,
                    stderr=subprocess.STDOUT,
                    check=True,
                )

            app_root = test_home / ".local" / "share" / "cozy-kids-launcher"
            config_path = test_home / ".config" / "cozy-kids-launcher" / "config.json"
            write_demo_config(config_path, browser_name)
            installed_version = (app_root / "version").read_text(encoding="utf-8").strip()
            ReleaseFixtureHandler.latest_version = installed_version

            app_port = available_port()
            environment = dict(os.environ)
            environment.update({
                "HOME": str(test_home),
                "COZY_KIDS_PORT": str(app_port),
                "COZY_KIDS_RELEASE_API_URL": (
                    f"http://127.0.0.1:{release_port}/releases/latest"
                ),
                "COZY_KIDS_RAW_URL": f"http://127.0.0.1:{release_port}",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
            })
            server_log = (args.artifacts / "server.log").open("w", encoding="utf-8")
            server_process = subprocess.Popen(
                ["python3", str(app_root / "server.py")],
                cwd=app_root,
                env=environment,
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )
            base_url = f"http://127.0.0.1:{app_port}"
            wait_for_server(f"{base_url}/api/config", server_process)

            with BrowserSession(
                browser_name,
                f"{base_url}/index.html",
                test_home / "browser-profile",
                args.artifacts / "browser.log",
                timeout=args.timeout,
                width=1440,
                height=900,
            ) as browser:
                try:
                    run_scenarios(
                        browser,
                        ReleaseFixtureHandler,
                        installed_version,
                        args.artifacts,
                    )
                    run_accessibility_scenarios(browser, args.artifacts)
                    browser.screenshot(args.artifacts / "final-state.png")
                except Exception:
                    browser.screenshot(args.artifacts / "failure.png")
                    raise
    finally:
        if server_process:
            stop_process(server_process)
        if server_log:
            server_log.close()
        release_server.shutdown()
        release_server.server_close()
        release_thread.join(timeout=5)

    print("Browser E2E passed: 17 core and accessibility journeys", flush=True)
    print(f"Artifacts: {args.artifacts}", flush=True)


if __name__ == "__main__":
    main()
