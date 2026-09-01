#!/usr/bin/env bash
set -euo pipefail
if [[ -d /snap/bin ]] && [[ ":$PATH:" != *":/snap/bin:"* ]]; then
  export PATH="$PATH:/snap/bin"
fi

# Self-bootstrap: if run standalone (e.g. curl | bash) and src/ is missing,
# download the repo and re-execute from the extracted copy.
if [[ -n "${BASH_SOURCE[0]:-}" ]]; then
  REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
else
  REPO_DIR="."
fi
SRC_DIR="$REPO_DIR/src"

if [[ ! -d "$SRC_DIR" ]] || [[ ! -f "$SRC_DIR/server.py" ]]; then
  REPO="TrissyGE/cozy-kids-launcher"
  TMP_DIR="$(mktemp -d)"
  trap 'rm -rf "$TMP_DIR"' EXIT

  echo "Downloading Cozy Kids Launcher..."
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL -o "$TMP_DIR/repo.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$TMP_DIR/repo.zip" "https://github.com/$REPO/archive/refs/heads/main.zip"
  else
    echo "Error: curl or wget is required."
    exit 1
  fi

  echo "Extracting..."
  if command -v unzip >/dev/null 2>&1; then
    unzip -q "$TMP_DIR/repo.zip" -d "$TMP_DIR/"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -m zipfile -e "$TMP_DIR/repo.zip" "$TMP_DIR/"
  else
    echo "Error: unzip or Python 3 is required to extract the download."
    exit 1
  fi

  # Re-execute with all original arguments
  exec bash "$TMP_DIR/cozy-kids-launcher-main/scripts/install.sh" "$@"
fi

DEFAULT_LANG="en"
APP_ID="cozy-kids-launcher"
APP_DIR_NAME="$APP_ID"
APP_BIN_NAME="cozy-kids-launcher"
DESKTOP_FILE_ID="cozy-kids-launcher.desktop"
AUTOSTART_FILE_ID="cozy-kids-launcher-autostart.desktop"
DESKTOP_SHORTCUT_ID="Cozy Kids Launcher.desktop"
DEFAULT_PORT="38431"
DEFAULT_BROWSER="auto"
DEFAULT_TITLE=""
DEFAULT_THEME="rosa"
DEFAULT_LAYOUT="gross"
DEFAULT_PARENT_LABEL=""
DEFAULT_EXIT_LABEL=""
DEFAULT_LAUNCH_MODE="kiosk"
TARGET_USER="${SUDO_USER:-${USER:-$(id -un 2>/dev/null || true)}}"
TARGET_HOME=""
INSTALL_SHUTDOWN_HELPER="0"
LANG_MODE="auto"
FORCE="0"
SKIP_BROWSER_CHECK="0"
RECOMMENDED="0"
EXPLICIT_LANG=0
EXPLICIT_BROWSER=0
EXPLICIT_TITLE=0
EXPLICIT_THEME=0
EXPLICIT_LAYOUT=0
EXPLICIT_LAUNCH_MODE=0
EXPLICIT_PARENT_LABEL=0
EXPLICIT_EXIT_LABEL=0
EXPLICIT_SHUTDOWN=0
EXPLICIT_RECOMMENDED=0

usage() {
  cat <<'EOF'
Usage: scripts/install.sh [options]

Options:
  --user <name>              Install for this Linux user
  --home <path>              Override user home directory
  --lang <auto|de|en>        Installer and default UI language
  --browser <auto|firefox|chromium|chromium-browser|google-chrome|google-chrome-stable|brave|opera|opera-stable|vivaldi|vivaldi-stable|microsoft-edge|microsoft-edge-stable|cachy-browser|librewolf>
                             Preferred kiosk browser
  --title <text>             Default launcher title
  --theme <rosa|lila|blau|gruen|regenbogen>
  --layout <gross|klein>
  --launch-mode <window|fullscreen|kiosk>
                             Browser launch mode
  --parent-label <text>      Default parent/settings button label
  --exit-label <text>        Default exit button label
  --install-shutdown-helper  Install optional local shutdown helper
  --recommended              Add tiles for installed recommended apps
  --skip-browser-check       Generate files without requiring a local browser
  --force                    Overwrite existing generated files
  -h, --help                 Show this help
EOF
}

die() {
  echo "Error: $*" >&2
  exit 1
}

is_interactive() {
  [[ -t 0 ]]
}

prompt_read() {
  local prompt_text="$1"
  local var_name="$2"
  if [[ -t 0 ]]; then
    IFS= read -r -p "$prompt_text" "$var_name"
  elif [[ -r /dev/tty ]] && command -v tty >/dev/null 2>&1 && tty >/dev/null 2>&1; then
    IFS= read -r -p "$prompt_text" "$var_name" < /dev/tty
  fi
}

trim() {
  local value="$1"
  value="${value#${value%%[![:space:]]*}}"
  value="${value%${value##*[![:space:]]}}"
  printf '%s' "$value"
}

lang_base() {
  local raw="$1"
  raw="${raw%%.*}"
  raw="${raw%%@*}"
  raw="${raw%%_*}"
  printf '%s' "${raw,,}"
}

auto_detect_lang() {
  local candidate="${LC_ALL:-${LC_MESSAGES:-${LANG:-}}}"
  candidate="$(lang_base "$candidate")"
  case "$candidate" in
    de) printf 'de' ;;
    en) printf 'en' ;;
    *) printf '%s' "$DEFAULT_LANG" ;;
  esac
}

text() {
  local key="$1"
  case "$ACTIVE_LANG:$key" in
    de:app_name) echo "Cozy Kids Launcher" ;;
    de:shortcut_name) echo "Kinder-Modus" ;;
    de:autostart_name) echo "Cozy Kids Launcher beim Login" ;;
    de:config_title) echo "Hallo Kiddo 🌈" ;;
    de:parent_label) echo "Papa" ;;
    de:exit_label) echo "Kindermodus beenden" ;;
    de:shutdown_label) echo "Ausschalten" ;;
    de:no_media_title) echo "Keine Medien gefunden" ;;
    de:no_media_body) echo "Hier wurden noch keine Musik- oder Videodateien gefunden." ;;
    de:no_media_back) echo "Zurück zur Startseite" ;;
    de:admin_title) echo "Eltern-Einstellungen" ;;
    de:admin_nav_label) echo "Bereiche der Eltern-Einstellungen" ;;
    de:admin_overview) echo "Übersicht" ;;
    de:admin_children) echo "Kinder" ;;
    de:admin_apps_media) echo "Apps & Medien" ;;
    de:admin_screen_time) echo "Bildschirmzeit" ;;
    de:admin_appearance) echo "Darstellung" ;;
    de:admin_system) echo "System" ;;
    de:app_search_label) echo "Apps und Medien durchsuchen" ;;
    de:app_filter_label) echo "Nach Sichtbarkeit filtern" ;;
    de:app_filter_all) echo "Alle Kacheln" ;;
    de:app_filter_visible) echo "Sichtbar" ;;
    de:app_filter_hidden) echo "Ausgeblendet" ;;
    de:app_filter_empty) echo "Keine Kacheln passen zu Suche und Filter." ;;
    de:app_filter_count) echo "{shown} von {total} Kacheln" ;;
    de:app_bulk_actions) echo "Mehrfachaktionen" ;;
    de:app_bulk_select_all) echo "Treffer auswählen" ;;
    de:app_bulk_selected) echo "{count} ausgewählt" ;;
    de:app_bulk_show) echo "Einblenden" ;;
    de:app_bulk_hide) echo "Ausblenden" ;;
    de:app_bulk_delete) echo "Auswahl löschen" ;;
    de:app_bulk_delete_confirm) echo "{count} ausgewählte Kacheln löschen?" ;;
    de:app_select_tile) echo "{tile} auswählen" ;;
    de:confirm_title) echo "Bitte bestätigen" ;;
    de:confirm_cancel) echo "Abbrechen" ;;
    de:confirm_continue) echo "Fortfahren" ;;
    de:retry) echo "Erneut versuchen" ;;
    de:startup_loading) echo "Launcher wird geladen..." ;;
    de:startup_error_title) echo "Start fehlgeschlagen" ;;
    de:startup_error) echo "Die Launcher-Einstellungen konnten nicht geladen werden." ;;
    de:save_loading) echo "Einstellungen werden gespeichert..." ;;
    de:save_error) echo "Einstellungen konnten nicht gespeichert werden. Bitte erneut versuchen." ;;
    de:app_catalog_loading) echo "Installierte Apps werden geladen..." ;;
    de:app_catalog_empty) echo "Keine installierten Desktop-Apps gefunden. Webseiten- und Medienkacheln sind weiterhin verfügbar." ;;
    de:app_catalog_error) echo "Installierte Apps konnten nicht geladen werden. Vorhandene Kacheln bleiben unverändert." ;;
    de:browser_catalog_loading) echo "Browser werden geladen..." ;;
    de:browser_catalog_empty) echo "Kein unterstützter Browser gefunden." ;;
    de:browser_catalog_error) echo "Die Browser-Liste konnte nicht geladen werden. Die aktuelle Auswahl bleibt erhalten." ;;
    de:recommendations_loading) echo "App-Empfehlungen werden geladen..." ;;
    de:recommendations_empty) echo "Zurzeit sind keine App-Empfehlungen verfügbar." ;;
    de:recommendations_error) echo "App-Empfehlungen konnten nicht geladen werden." ;;
    de:placeholder_title) echo "Überschrift" ;;
    de:placeholder_parent_label) echo "Eltern-Button" ;;
    de:placeholder_exit_label) echo "Beenden-Button" ;;
    de:add_tile) echo "Kachel hinzufügen" ;;
    de:back) echo "Zurück" ;;
    de:save) echo "Speichern" ;;
    de:layout_large) echo "Groß (4)" ;;
    de:layout_small) echo "Klein (9)" ;;
    de:visible) echo "sichtbar" ;;
    de:special_media) echo "Spezial: Filme und Musik" ;;
    de:browser_page) echo "Webseite" ;;
    de:web_mode_embedded) echo "Eingebettet" ;;
    de:web_mode_external) echo "Extern" ;;
    de:no_app) echo "Kein Programm" ;;
    de:custom_cmd) echo "Benutzerdefiniert" ;;
    de:move_up) echo "Hoch" ;;
    de:move_down) echo "Runter" ;;
    de:delete) echo "Löschen" ;;
    de:new_tile) echo "Neue Kachel" ;;
    de:tile_paint) echo "Malen" ;;
    de:tile_games) echo "Lernspiele" ;;
    de:tile_music) echo "Filme und Musik" ;;
    de:tile_browser) echo "Kinder-Internet" ;;
    de:browser_url) echo "https://www.fragfinn.de/" ;;
    de:pin_title) echo "PIN eingeben" ;;
    de:pin_placeholder) echo "4-6 Zahlen" ;;
    de:pin_wrong) echo "Falscher PIN" ;;
    de:pin_set) echo "PIN setzen" ;;
    de:pin_change) echo "PIN ändern" ;;
    de:pin_remove) echo "PIN entfernen" ;;
    de:pin_confirm) echo "Wiederholen" ;;
    de:pin_mismatch) echo "PINs stimmen nicht überein" ;;
    de:pin_saved) echo "PIN gespeichert" ;;
    de:pin_removed) echo "PIN entfernt" ;;
    de:admin_page_prev) echo "Vorherige Seite" ;;
    de:admin_page_next) echo "Nächste Seite" ;;
    de:update_check) echo "Auf Updates prüfen" ;;
    de:update_available) echo "Update verfügbar" ;;
    de:update_up_to_date) echo "Aktuell" ;;
    de:update_loading) echo "Updates werden geprüft..." ;;
    de:update_error) echo "Update-Prüfung fehlgeschlagen" ;;
    de:version_label) echo "Version" ;;
    de:update_now) echo "Jetzt aktualisieren" ;;
    de:update_progress) echo "Update wird installiert... bitte warten" ;;
    de:update_confirm) echo "Browser wird geschlossen und das Update installiert. Fortfahren?" ;;
    de:runtime_failure_title) echo "Neustart fehlgeschlagen" ;;
    de:runtime_failure_body) echo "Cozy Kids Launcher konnte nach mehreren Versuchen nicht neu gestartet werden. Bitte starte den Kindermodus erneut. Wenn das Problem wiederkehrt, lade nach einem erfolgreichen Start die Diagnose in den Eltern-Einstellungen herunter." ;;
    de:install_done) echo "Installation abgeschlossen." ;;
    de:next_steps) echo "Du kannst Cozy Kids Launcher jetzt über den Desktop-Shortcut oder nach dem nächsten Login starten." ;;
    de:recommended_title) echo "Empfohlene Apps" ;;
    de:recommended_installed) echo "installiert" ;;
    de:recommended_not_installed) echo "nicht installiert" ;;
    de:recommended_prompt) echo "Tiles für empfohlene Apps erstellen, falls installiert? [j/N]" ;;
    en:app_name) echo "Cozy Kids Launcher" ;;
    en:shortcut_name) echo "Kids Mode" ;;
    en:autostart_name) echo "Cozy Kids Launcher on Login" ;;
    en:config_title) echo "Hello Kiddo 🌈" ;;
    en:parent_label) echo "Parent" ;;
    en:exit_label) echo "Exit kids mode" ;;
    en:shutdown_label) echo "Shut down" ;;
    en:no_media_title) echo "No media found" ;;
    en:no_media_body) echo "No music or video files were found here yet." ;;
    en:no_media_back) echo "Back to home screen" ;;
    en:admin_title) echo "Parent settings" ;;
    en:admin_nav_label) echo "Parent settings sections" ;;
    en:admin_overview) echo "Overview" ;;
    en:admin_children) echo "Children" ;;
    en:admin_apps_media) echo "Apps & Media" ;;
    en:admin_screen_time) echo "Screen Time" ;;
    en:admin_appearance) echo "Appearance" ;;
    en:admin_system) echo "System" ;;
    en:app_search_label) echo "Search apps and media" ;;
    en:app_filter_label) echo "Filter by visibility" ;;
    en:app_filter_all) echo "All tiles" ;;
    en:app_filter_visible) echo "Visible" ;;
    en:app_filter_hidden) echo "Hidden" ;;
    en:app_filter_empty) echo "No tiles match your search and filter." ;;
    en:app_filter_count) echo "{shown} of {total} tiles" ;;
    en:app_bulk_actions) echo "Bulk actions" ;;
    en:app_bulk_select_all) echo "Select results" ;;
    en:app_bulk_selected) echo "{count} selected" ;;
    en:app_bulk_show) echo "Show" ;;
    en:app_bulk_hide) echo "Hide" ;;
    en:app_bulk_delete) echo "Delete selection" ;;
    en:app_bulk_delete_confirm) echo "Delete {count} selected tiles?" ;;
    en:app_select_tile) echo "Select {tile}" ;;
    en:confirm_title) echo "Please confirm" ;;
    en:confirm_cancel) echo "Cancel" ;;
    en:confirm_continue) echo "Continue" ;;
    en:retry) echo "Try again" ;;
    en:startup_loading) echo "Loading launcher..." ;;
    en:startup_error_title) echo "Startup failed" ;;
    en:startup_error) echo "The launcher settings could not be loaded." ;;
    en:save_loading) echo "Saving settings..." ;;
    en:save_error) echo "Settings could not be saved. Please try again." ;;
    en:app_catalog_loading) echo "Loading installed apps..." ;;
    en:app_catalog_empty) echo "No installed desktop apps found. Website and media tiles are still available." ;;
    en:app_catalog_error) echo "Installed apps could not be loaded. Existing tiles remain unchanged." ;;
    en:browser_catalog_loading) echo "Loading browsers..." ;;
    en:browser_catalog_empty) echo "No supported browser found." ;;
    en:browser_catalog_error) echo "The browser list could not be loaded. The current selection is preserved." ;;
    en:recommendations_loading) echo "Loading app recommendations..." ;;
    en:recommendations_empty) echo "No app recommendations are currently available." ;;
    en:recommendations_error) echo "App recommendations could not be loaded." ;;
    en:placeholder_title) echo "Title" ;;
    en:placeholder_parent_label) echo "Parent button" ;;
    en:placeholder_exit_label) echo "Exit button" ;;
    en:add_tile) echo "Add tile" ;;
    en:back) echo "Back" ;;
    en:save) echo "Save" ;;
    en:layout_large) echo "Large (4)" ;;
    en:layout_small) echo "Small (9)" ;;
    en:visible) echo "visible" ;;
    en:special_media) echo "Special: Movies and music" ;;
    en:browser_page) echo "Website" ;;
    en:web_mode_embedded) echo "Embedded" ;;
    en:web_mode_external) echo "External" ;;
    en:no_app) echo "No app" ;;
    en:custom_cmd) echo "Custom" ;;
    en:move_up) echo "Up" ;;
    en:move_down) echo "Down" ;;
    en:delete) echo "Delete" ;;
    en:new_tile) echo "New tile" ;;
    en:tile_paint) echo "Paint" ;;
    en:tile_games) echo "Learning games" ;;
    en:tile_music) echo "Movies and music" ;;
    en:tile_browser) echo "Kids browser" ;;
    en:browser_url) echo "https://www.pbskids.org/" ;;
    en:pin_title) echo "Enter PIN" ;;
    en:pin_placeholder) echo "4-6 digits" ;;
    en:pin_wrong) echo "Wrong PIN" ;;
    en:pin_set) echo "Set PIN" ;;
    en:pin_change) echo "Change PIN" ;;
    en:pin_remove) echo "Remove PIN" ;;
    en:pin_confirm) echo "Repeat" ;;
    en:pin_mismatch) echo "PINs do not match" ;;
    en:pin_saved) echo "PIN saved" ;;
    en:pin_removed) echo "PIN removed" ;;
    en:admin_page_prev) echo "Previous page" ;;
    en:admin_page_next) echo "Next page" ;;
    en:update_check) echo "Check for updates" ;;
    en:update_available) echo "Update available" ;;
    en:update_up_to_date) echo "Up to date" ;;
    en:update_loading) echo "Checking for updates..." ;;
    en:update_error) echo "Update check failed" ;;
    en:version_label) echo "Version" ;;
    en:update_now) echo "Update now" ;;
    en:update_progress) echo "Installing update... please wait" ;;
    en:update_confirm) echo "Close browser and install update now?" ;;
    en:runtime_failure_title) echo "Restart failed" ;;
    en:runtime_failure_body) echo "Cozy Kids Launcher could not restart after several attempts. Please start kids mode again. If the problem returns, download diagnostics from Parent settings after a successful start." ;;
    en:install_done) echo "Installation complete." ;;
    en:next_steps) echo "You can now launch Cozy Kids Launcher from the desktop shortcut or after the next login." ;;
    en:recommended_title) echo "Recommended apps" ;;
    en:recommended_installed) echo "installed" ;;
    en:recommended_not_installed) echo "not installed" ;;
    en:recommended_prompt) echo "Create tiles for recommended apps if installed? [y/N]" ;;
    de:app_browser_title) echo "App-Browser" ;;
    de:install) echo "Installieren" ;;
    de:added) echo "Hinzugefügt" ;;
    de:installed) echo "installiert" ;;
    de:not_installed) echo "nicht installiert" ;;
    de:copy_command) echo "Kopieren" ;;
    de:command_copied) echo "Kopiert!" ;;
    de:install_started) echo "Installation gestartet. Suche nach einem Passwort-Dialog, oder führe den Befehl aus:" ;;
    de:install_manual) echo "Bitte führe diesen Befehl im Terminal aus:" ;;
    de:close) echo "Schließen" ;;
    de:export_config) echo "Konfiguration exportieren" ;;
    de:import_config) echo "Konfiguration importieren" ;;
    de:export_diagnostics) echo "Diagnose herunterladen" ;;
    de:import_success) echo "Konfiguration importiert" ;;
    de:import_error) echo "Import fehlgeschlagen" ;;
    de:invalid_config) echo "Ungültige Konfigurationsdatei" ;;
    de:import_confirm) echo "Dies überschreibt die gesamte Konfiguration. Fortfahren?" ;;
    de:backup_title) echo "Sicherungen" ;;
    de:backup_restore) echo "Wiederherstellen" ;;
    de:backup_empty) echo "Keine gültigen Sicherungen gefunden." ;;
    de:backup_loading) echo "Sicherungen werden geladen..." ;;
    de:backup_load_error) echo "Sicherungen konnten nicht geladen werden." ;;
    de:backup_restoring) echo "Sicherung wird wiederhergestellt..." ;;
    de:backup_confirm) echo "Diese Sicherung ersetzt die aktuellen Einstellungen. Der Eltern-PIN bleibt erhalten und vorher wird automatisch eine neue Sicherung erstellt. Fortfahren?" ;;
    de:backup_success) echo "Sicherung wiederhergestellt." ;;
    de:backup_error) echo "Sicherung konnte nicht wiederhergestellt werden." ;;
    de:backup_installer) echo "Vor Installation oder Update" ;;
    de:backup_pre_restore) echo "Vor Wiederherstellung" ;;
    de:backup_pin_preserved) echo "Der aktuelle Eltern-PIN bleibt bei einer Wiederherstellung unverändert." ;;
    de:activity_title) echo "Aktivitätsübersicht" ;;
    de:activity_hint) echo "Optional und nur lokal: Zeigt abgeschlossene App-Nutzungen der letzten 90 Tage." ;;
    de:activity_enabled) echo "Aktivität lokal aufzeichnen" ;;
    de:activity_enabled_status) echo "Neue Nutzungen werden lokal aufgezeichnet, solange diese Option aktiviert ist." ;;
    de:activity_disabled_status) echo "Die Aufzeichnung ist aus. Vorhandene Daten bleiben, bis du sie löschst." ;;
    de:activity_time) echo "Nutzungszeit (90 Tage)" ;;
    de:activity_launches) echo "Abgeschlossene Nutzungen" ;;
    de:activity_recent) echo "Letzte Aktivitäten" ;;
    de:activity_empty) echo "Noch keine Aktivität aufgezeichnet." ;;
    de:activity_loading) echo "Aktivität wird geladen..." ;;
    de:activity_error) echo "Aktivität konnte nicht geladen werden." ;;
    de:activity_export) echo "Aktivität exportieren" ;;
    de:activity_clear) echo "Aktivität löschen" ;;
    de:activity_clear_confirm) echo "Alle lokal gespeicherten Aktivitätsdaten wirklich löschen?" ;;
    de:activity_clear_success) echo "Aktivitätsdaten wurden gelöscht." ;;
    de:activity_clear_error) echo "Aktivitätsdaten konnten nicht gelöscht werden." ;;
    de:activity_unknown_profile) echo "Gelöschtes Profil" ;;
    de:activity_unknown_app) echo "Entfernte App" ;;
    de:activity_less_minute) echo "< 1 Min." ;;
    de:activity_minutes) echo "{count} Min." ;;
    de:activity_hours_minutes) echo "{hours} Std. {minutes} Min." ;;
    en:app_browser_title) echo "App Browser" ;;
    en:install) echo "Install" ;;
    en:added) echo "Added" ;;
    en:installed) echo "installed" ;;
    en:not_installed) echo "not installed" ;;
    en:copy_command) echo "Copy" ;;
    en:command_copied) echo "Copied!" ;;
    en:install_started) echo "Installation started. Watch for a password dialog, or run the command below:" ;;
    en:install_manual) echo "Please run this command in a terminal:" ;;
    en:close) echo "Close" ;;
    en:export_config) echo "Export config" ;;
    en:import_config) echo "Import config" ;;
    en:export_diagnostics) echo "Download diagnostics" ;;
    en:import_success) echo "Config imported" ;;
    en:import_error) echo "Import failed" ;;
    en:invalid_config) echo "Invalid config file" ;;
    en:import_confirm) echo "This will overwrite all settings. Continue?" ;;
    en:backup_title) echo "Backups" ;;
    en:backup_restore) echo "Restore" ;;
    en:backup_empty) echo "No valid backups found." ;;
    en:backup_loading) echo "Loading backups..." ;;
    en:backup_load_error) echo "Backups could not be loaded." ;;
    en:backup_restoring) echo "Restoring backup..." ;;
    en:backup_confirm) echo "This backup will replace the current settings. The Parent PIN will be preserved and a new safety backup will be created first. Continue?" ;;
    en:backup_success) echo "Backup restored." ;;
    en:backup_error) echo "Backup could not be restored." ;;
    en:backup_installer) echo "Before installation or update" ;;
    en:backup_pre_restore) echo "Before restore" ;;
    en:backup_pin_preserved) echo "The current Parent PIN is preserved when restoring a backup." ;;
    en:activity_title) echo "Activity overview" ;;
    en:activity_hint) echo "Optional and local only: Shows completed app use from the last 90 days." ;;
    en:activity_enabled) echo "Track activity locally" ;;
    en:activity_enabled_status) echo "New usage is recorded locally while this option is enabled." ;;
    en:activity_disabled_status) echo "Tracking is off. Existing data remains until you remove it." ;;
    en:activity_time) echo "Usage time (90 days)" ;;
    en:activity_launches) echo "Completed sessions" ;;
    en:activity_recent) echo "Recent activity" ;;
    en:activity_empty) echo "No activity has been recorded yet." ;;
    en:activity_loading) echo "Loading activity..." ;;
    en:activity_error) echo "Activity could not be loaded." ;;
    en:activity_export) echo "Export activity" ;;
    en:activity_clear) echo "Clear activity" ;;
    en:activity_clear_confirm) echo "Remove all locally stored activity data?" ;;
    en:activity_clear_success) echo "Activity data was removed." ;;
    en:activity_clear_error) echo "Activity data could not be removed." ;;
    en:activity_unknown_profile) echo "Deleted profile" ;;
    en:activity_unknown_app) echo "Removed app" ;;
    en:activity_less_minute) echo "< 1 min" ;;
    en:activity_minutes) echo "{count} min" ;;
    en:activity_hours_minutes) echo "{hours} hr {minutes} min" ;;
    de:timer_label) echo "Bildschirmzeit" ;;
    en:timer_label) echo "Screen time" ;;
    de:schedule_weekly_title) echo "Wochenplan" ;;
    en:schedule_weekly_title) echo "Weekly schedule" ;;
    de:schedule_weekly_hint) echo "Lege fest, wann dieses Kinderprofil Apps starten darf. Die Zeiten verwenden die lokale Gerätezeit." ;;
    en:schedule_weekly_hint) echo "Choose when this child profile may start apps. Times use the device's local time." ;;
    de:schedule_enabled) echo "Zeitplan aktiv" ;;
    en:schedule_enabled) echo "Schedule enabled" ;;
    de:schedule_app_title) echo "Zeitfenster pro App" ;;
    en:schedule_app_title) echo "Per-app availability" ;;
    de:schedule_app_hint) echo "Optional kannst du für einzelne Apps engere Zeitfenster festlegen." ;;
    en:schedule_app_hint) echo "Optionally set narrower time windows for individual apps." ;;
    de:schedule_select_app) echo "App auswählen" ;;
    en:schedule_select_app) echo "Select app" ;;
    de:schedule_add_window) echo "Zeitfenster hinzufügen" ;;
    en:schedule_add_window) echo "Add time window" ;;
    de:schedule_remove_window) echo "Zeitfenster entfernen" ;;
    en:schedule_remove_window) echo "Remove time window" ;;
    de:schedule_start) echo "Beginn" ;;
    en:schedule_start) echo "Start" ;;
    de:schedule_end) echo "Ende" ;;
    en:schedule_end) echo "End" ;;
    de:schedule_clear_app) echo "App-Regel entfernen" ;;
    en:schedule_clear_app) echo "Remove app rule" ;;
    de:schedule_no_windows) echo "Gesperrt" ;;
    en:schedule_no_windows) echo "Blocked" ;;
    de:schedule_blocked_title) echo "Jetzt ist Pause" ;;
    en:schedule_blocked_title) echo "Time for a break" ;;
    de:schedule_profile_blocked) echo "Der Wochenplan erlaubt gerade keine Apps. Frag deine Eltern, wenn etwas geändert werden soll." ;;
    en:schedule_profile_blocked) echo "The weekly schedule does not allow apps right now. Ask a parent if it should be changed." ;;
    de:schedule_app_blocked) echo "Diese App ist laut Zeitplan gerade nicht verfügbar." ;;
    en:schedule_app_blocked) echo "This app is not available at this time." ;;
    de:schedule_open_parents) echo "Elterneinstellungen" ;;
    en:schedule_open_parents) echo "Parent settings" ;;
    de:weekday_monday) echo "Montag" ;;
    en:weekday_monday) echo "Monday" ;;
    de:weekday_tuesday) echo "Dienstag" ;;
    en:weekday_tuesday) echo "Tuesday" ;;
    de:weekday_wednesday) echo "Mittwoch" ;;
    en:weekday_wednesday) echo "Wednesday" ;;
    de:weekday_thursday) echo "Donnerstag" ;;
    en:weekday_thursday) echo "Thursday" ;;
    de:weekday_friday) echo "Freitag" ;;
    en:weekday_friday) echo "Friday" ;;
    de:weekday_saturday) echo "Samstag" ;;
    en:weekday_saturday) echo "Saturday" ;;
    de:weekday_sunday) echo "Sonntag" ;;
    en:weekday_sunday) echo "Sunday" ;;
    de:timer_off) echo "Aus" ;;
    en:timer_off) echo "Off" ;;
    de:timer_15) echo "15 Minuten" ;;
    en:timer_15) echo "15 minutes" ;;
    de:timer_30) echo "30 Minuten" ;;
    en:timer_30) echo "30 minutes" ;;
    de:timer_60) echo "60 Minuten" ;;
    en:timer_60) echo "60 minutes" ;;
    de:timer_custom) echo "Eigene" ;;
    en:timer_custom) echo "Custom" ;;
    de:timer_start) echo "Timer starten" ;;
    en:timer_start) echo "Start timer" ;;
    de:timer_stop) echo "Timer stoppen" ;;
    en:timer_stop) echo "Stop timer" ;;
    de:timer_active) echo "Timer läuft" ;;
    en:timer_active) echo "Timer running" ;;
    de:timer_expired) echo "Zeit um!" ;;
    en:timer_expired) echo "Time's up!" ;;
    de:timer_remaining) echo "Noch {time}" ;;
    en:timer_remaining) echo "{time} left" ;;
    de:timer_warning_title) echo "Noch 5 Minuten!" ;;
    en:timer_warning_title) echo "5 minutes left!" ;;
    de:timer_warning_text) echo "Die Bildschirmzeit läuft bald ab." ;;
    en:timer_warning_text) echo "Screen time is running out." ;;
    de:timer_enter_pin) echo "PIN eingeben:" ;;
    en:timer_enter_pin) echo "Enter PIN:" ;;
    de:timer_extend) echo "Verlängern" ;;
    en:timer_extend) echo "Extend" ;;
    de:timer_exit) echo "Beenden" ;;
    en:timer_exit) echo "Exit" ;;
    de:timer_wrong_pin) echo "Falscher PIN" ;;
    en:timer_wrong_pin) echo "Wrong PIN" ;;
    de:timer_extended) echo "Verlängert!" ;;
    en:timer_extended) echo "Extended!" ;;
    de:timer_expired_title) echo "Zeit ist um!" ;;
    en:timer_expired_title) echo "Time is up!" ;;
    de:timer_expired_body) echo "Frag Mama oder Papa, um weiterzuspielen." ;;
    en:timer_expired_body) echo "Ask Mom or Dad to keep playing." ;;
    de:timer_minutes) echo "Minuten" ;;
    en:timer_minutes) echo "minutes" ;;
    de:starting_app) echo "Starte {app}..." ;;
    en:starting_app) echo "Starting {app}..." ;;
    de:empty_state_emoji) echo "🤔" ;;
    en:empty_state_emoji) echo "🤔" ;;
    de:empty_state_text) echo "Frag Mama oder Papa, um Apps hinzuzufügen!" ;;
    en:empty_state_text) echo "Ask Mom or Dad to add apps!" ;;
    de:preview_title) echo "Vorschau" ;;
    en:preview_title) echo "Preview" ;;
    *) die "Missing translation for $ACTIVE_LANG:$key" ;;
  esac
}

json_text() {
  python3 - "$1" <<'PY'
import json, sys
print(json.dumps(sys.argv[1], ensure_ascii=False))
PY
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      TARGET_USER="$2"
      shift 2
      ;;
    --home)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      TARGET_HOME="$2"
      shift 2
      ;;
    --lang)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      LANG_MODE="$2"
      EXPLICIT_LANG=1
      shift 2
      ;;
    --browser)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_BROWSER="$2"
      EXPLICIT_BROWSER=1
      shift 2
      ;;
    --title)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_TITLE="$2"
      EXPLICIT_TITLE=1
      shift 2
      ;;
    --theme)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_THEME="$2"
      EXPLICIT_THEME=1
      shift 2
      ;;
    --layout)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_LAYOUT="$2"
      EXPLICIT_LAYOUT=1
      shift 2
      ;;
    --launch-mode)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_LAUNCH_MODE="$2"
      EXPLICIT_LAUNCH_MODE=1
      shift 2
      ;;
    --parent-label)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_PARENT_LABEL="$2"
      EXPLICIT_PARENT_LABEL=1
      shift 2
      ;;
    --exit-label)
      [[ -n "${2:-}" ]] || die "Missing value for $1"
      DEFAULT_EXIT_LABEL="$2"
      EXPLICIT_EXIT_LABEL=1
      shift 2
      ;;
    --install-shutdown-helper)
      INSTALL_SHUTDOWN_HELPER="1"
      EXPLICIT_SHUTDOWN=1
      shift
      ;;
    --recommended)
      RECOMMENDED="1"
      EXPLICIT_RECOMMENDED=1
      shift
      ;;
    --skip-browser-check)
      SKIP_BROWSER_CHECK="1"
      shift
      ;;
    --force)
      FORCE="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      die "Unknown option: $1"
      ;;
  esac
done

[[ -n "$TARGET_USER" ]] || die "No target user resolved. Use --user <name>."

if [[ -z "$TARGET_HOME" ]]; then
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6)"
fi
[[ -n "$TARGET_HOME" ]] || die "Could not resolve home directory for user '$TARGET_USER'."
[[ -d "$TARGET_HOME" ]] || die "Home directory does not exist: $TARGET_HOME"

case "$LANG_MODE" in
  auto) ACTIVE_LANG="$(auto_detect_lang)" ;;
  de|en) ACTIVE_LANG="$LANG_MODE" ;;
  *) die "Unsupported language: $LANG_MODE" ;;
esac

case "$DEFAULT_THEME" in
  rosa|lila|blau|gruen|regenbogen|wald|weltraum|ocean|dinosaurier|baustelle|prinzessin|bauernhof|katzen|hunde) ;;
  *) die "Unsupported theme: $DEFAULT_THEME" ;;
esac

case "$DEFAULT_LAYOUT" in
  gross|klein) ;;
  *) die "Unsupported layout: $DEFAULT_LAYOUT" ;;
esac

case "$DEFAULT_LAUNCH_MODE" in
  window|fullscreen|kiosk) ;;
  *) die "Unsupported launch mode: $DEFAULT_LAUNCH_MODE" ;;
esac

guided_setup() {
  local input
  echo ""
  echo "========================================="
  echo "  Guided Setup"
  echo "========================================="
  echo ""

  if [[ "$EXPLICIT_LANG" == "0" ]]; then
    echo "Choose language:"
    echo "  1) English"
    echo "  2) Deutsch"
    echo "  3) Auto-detect (default)"
    prompt_read "Choice [3]: " input
    case "$input" in
      1) LANG_MODE="en"; EXPLICIT_LANG=1 ;;
      2) LANG_MODE="de"; EXPLICIT_LANG=1 ;;
      *) ;;
    esac
    case "$LANG_MODE" in
      auto) ACTIVE_LANG="$(auto_detect_lang)" ;;
      de|en) ACTIVE_LANG="$LANG_MODE" ;;
    esac
  fi

  if [[ "$EXPLICIT_BROWSER" == "0" ]]; then
    echo ""
    echo "Choose browser:"
    echo "  1) Auto-detect (default)"
    echo "  2) Firefox"
    echo "  3) Chromium"
    echo "  4) Google Chrome"
    echo "  5) Other browser"
    prompt_read "Choice [1]: " input
    case "$input" in
      2) DEFAULT_BROWSER="firefox"; EXPLICIT_BROWSER=1 ;;
      3) DEFAULT_BROWSER="chromium"; EXPLICIT_BROWSER=1 ;;
      4)
        if command -v google-chrome >/dev/null 2>&1; then
          DEFAULT_BROWSER="google-chrome"; EXPLICIT_BROWSER=1
        elif command -v google-chrome-stable >/dev/null 2>&1; then
          DEFAULT_BROWSER="google-chrome-stable"; EXPLICIT_BROWSER=1
        else
          DEFAULT_BROWSER="google-chrome"; EXPLICIT_BROWSER=1
        fi
        ;;
      5)
        prompt_read "Browser command name (e.g. brave, opera, vivaldi): " input
        if [[ -n "$input" ]]; then
          DEFAULT_BROWSER="$input"; EXPLICIT_BROWSER=1
        fi
        ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_THEME" == "0" ]]; then
    echo ""
    echo "Choose theme:"
    echo "  1) Rosa (default)"
    echo "  2) Lila"
    echo "  3) Blau"
    echo "  4) Gruen"
    echo "  5) Regenbogen"
    echo "  6) Wald"
    echo "  7) Weltraum"
    echo "  8) Ocean"
    echo "  9) Dinosaurier"
    echo " 10) Baustelle"
    echo " 11) Prinzessin"
    echo " 12) Bauernhof"
    echo " 13) Katzen"
    echo " 14) Hunde"
    prompt_read "Choice [1]: " input
    case "$input" in
      2) DEFAULT_THEME="lila"; EXPLICIT_THEME=1 ;;
      3) DEFAULT_THEME="blau"; EXPLICIT_THEME=1 ;;
      4) DEFAULT_THEME="gruen"; EXPLICIT_THEME=1 ;;
      5) DEFAULT_THEME="regenbogen"; EXPLICIT_THEME=1 ;;
      6) DEFAULT_THEME="wald"; EXPLICIT_THEME=1 ;;
      7) DEFAULT_THEME="weltraum"; EXPLICIT_THEME=1 ;;
      8) DEFAULT_THEME="ocean"; EXPLICIT_THEME=1 ;;
      9) DEFAULT_THEME="dinosaurier"; EXPLICIT_THEME=1 ;;
      10) DEFAULT_THEME="baustelle"; EXPLICIT_THEME=1 ;;
      11) DEFAULT_THEME="prinzessin"; EXPLICIT_THEME=1 ;;
      12) DEFAULT_THEME="bauernhof"; EXPLICIT_THEME=1 ;;
      13) DEFAULT_THEME="katzen"; EXPLICIT_THEME=1 ;;
      14) DEFAULT_THEME="hunde"; EXPLICIT_THEME=1 ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_LAYOUT" == "0" ]]; then
    echo ""
    echo "Choose tile layout:"
    echo "  1) Gross / Large - 4 big tiles (default)"
    echo "  2) Klein / Small - 9 smaller tiles"
    prompt_read "Choice [1]: " input
    case "$input" in
      2) DEFAULT_LAYOUT="klein"; EXPLICIT_LAYOUT=1 ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_LAUNCH_MODE" == "0" ]]; then
    echo ""
    echo "Choose launch mode:"
    echo "  1) Kiosk - fullscreen, no window controls (default)"
    echo "  2) Fullscreen - fullscreen with minimal controls"
    echo "  3) Window - regular browser window"
    prompt_read "Choice [1]: " input
    case "$input" in
      2) DEFAULT_LAUNCH_MODE="fullscreen"; EXPLICIT_LAUNCH_MODE=1 ;;
      3) DEFAULT_LAUNCH_MODE="window"; EXPLICIT_LAUNCH_MODE=1 ;;
      *) ;;
    esac
  fi

  if [[ "$EXPLICIT_TITLE" == "0" ]]; then
    echo ""
    prompt_read "Launcher title [$(text config_title)]: " input
    if [[ -n "$input" ]]; then
      DEFAULT_TITLE="$input"
      EXPLICIT_TITLE=1
    fi
  fi

  if [[ "$EXPLICIT_PARENT_LABEL" == "0" ]]; then
    echo ""
    prompt_read "Parent button label [$(text parent_label)]: " input
    if [[ -n "$input" ]]; then
      DEFAULT_PARENT_LABEL="$input"
      EXPLICIT_PARENT_LABEL=1
    fi
  fi

  if [[ "$EXPLICIT_EXIT_LABEL" == "0" ]]; then
    echo ""
    prompt_read "Exit button label [$(text exit_label)]: " input
    if [[ -n "$input" ]]; then
      DEFAULT_EXIT_LABEL="$input"
      EXPLICIT_EXIT_LABEL=1
    fi
  fi

  if [[ "$EXPLICIT_SHUTDOWN" == "0" ]]; then
    echo ""
    prompt_read "Install shutdown helper? [y/N]: " input
    case "$input" in
      [jJyY]*) INSTALL_SHUTDOWN_HELPER="1"; EXPLICIT_SHUTDOWN=1 ;;
    esac
  fi

  if [[ "$EXPLICIT_RECOMMENDED" == "0" ]]; then
    echo ""
    prompt_read "Create tiles for recommended apps if installed? [y/N]: " input
    case "$input" in
      [jJyY]*) RECOMMENDED="1"; EXPLICIT_RECOMMENDED=1 ;;
    esac
  fi
}

# Offer guided mode when running interactively without explicit customizations
if is_interactive; then
  echo ""
  prompt_read "Use quick defaults, or walk through options? [d/w]: " input
  case "$input" in
    [wW]*) guided_setup ;;
    *) echo "Using defaults..." ;;
  esac

  # Re-derive language if it changed during guided setup
  case "$LANG_MODE" in
    auto) ACTIVE_LANG="$(auto_detect_lang)" ;;
    de|en) ACTIVE_LANG="$LANG_MODE" ;;
  esac
fi

find_browser() {
  if [[ "$DEFAULT_BROWSER" != "auto" ]]; then
    command -v "$DEFAULT_BROWSER" >/dev/null 2>&1 || die "Browser not found: $DEFAULT_BROWSER"
    printf '%s' "$DEFAULT_BROWSER"
    return
  fi

  local candidates=(firefox chromium chromium-browser google-chrome google-chrome-stable brave brave-browser opera opera-stable vivaldi vivaldi-stable microsoft-edge microsoft-edge-stable cachy-browser librewolf)
  local browser
  for browser in "${candidates[@]}"; do
    if command -v "$browser" >/dev/null 2>&1; then
      printf '%s' "$browser"
      return
    fi
  done

  # Snap-installed browsers (Ubuntu / Zorin)
  if [[ -d /snap/bin ]]; then
    for browser in "${candidates[@]}"; do
      if [[ -x "/snap/bin/$browser" ]]; then
        printf '%s' "/snap/bin/$browser"
        return
      fi
    done
  fi

  if [[ "$SKIP_BROWSER_CHECK" == "1" ]]; then
    printf '%s' "firefox"
    return
  fi

  die "No supported browser found. Install Firefox, Chromium, or another supported browser, or pass --browser."
}

BROWSER_CMD="$(find_browser)"
command -v python3 >/dev/null 2>&1 || die "python3 is required"
command -v install >/dev/null 2>&1 || die "install is required"
command -v flock >/dev/null 2>&1 || die "flock is required (provided by util-linux)"

# Summary
echo ""
echo "========================================="
echo "  Install Summary"
echo "========================================="
echo "  User:             $TARGET_USER"
echo "  Home:             $TARGET_HOME"
echo "  Language:         $ACTIVE_LANG"
echo "  Browser:          $BROWSER_CMD"
echo "  Theme:            $DEFAULT_THEME"
echo "  Layout:           $DEFAULT_LAYOUT"
echo "  Launch mode:      $DEFAULT_LAUNCH_MODE"
echo "  Title:            ${DEFAULT_TITLE:-$(text config_title)}"
echo "  Parent label:     ${DEFAULT_PARENT_LABEL:-$(text parent_label)}"
echo "  Exit label:       ${DEFAULT_EXIT_LABEL:-$(text exit_label)}"
echo "  Shutdown helper:  $INSTALL_SHUTDOWN_HELPER"
echo "  Recommended apps: $RECOMMENDED"
echo ""

if is_interactive; then
  prompt_read "Proceed with installation? [Y/n]: " input
  case "$input" in
    [nN]*) echo "Installation cancelled."; exit 0 ;;
  esac
fi

APP_ROOT="$TARGET_HOME/.local/share/$APP_DIR_NAME"
FRONTEND_DIR="$APP_ROOT/frontend"
BIN_DIR="$TARGET_HOME/.local/bin"
CFG_DIR="$TARGET_HOME/.config/$APP_DIR_NAME"
AUTOSTART_DIR="$TARGET_HOME/.config/autostart"
DESKTOP_DIR="$TARGET_HOME/Desktop"
if [[ ! -d "$DESKTOP_DIR" && -d "$TARGET_HOME/Schreibtisch" ]]; then
  DESKTOP_DIR="$TARGET_HOME/Schreibtisch"
fi
CACHE_DIR="$TARGET_HOME/.cache/$APP_DIR_NAME"
RUNTIME_BIN="$BIN_DIR/$APP_BIN_NAME"
CONFIG_FILE="$CFG_DIR/config.json"
SERVER_FILE="$APP_ROOT/server.py"
INDEX_FILE="$APP_ROOT/index.html"
FRONTEND_STYLES_FILE="$FRONTEND_DIR/styles.css"
FRONTEND_DESIGN_SYSTEM_FILE="$FRONTEND_DIR/design-system.css"
FRONTEND_STATE_FILE="$FRONTEND_DIR/state.js"
FRONTEND_LOCALIZATION_FILE="$FRONTEND_DIR/localization.js"
FRONTEND_LOCALES_DIR="$FRONTEND_DIR/locales"
FRONTEND_ICONS_FILE="$FRONTEND_DIR/icons.js"
FRONTEND_DIALOGS_FILE="$FRONTEND_DIR/dialogs.js"
FRONTEND_LAUNCHER_FILE="$FRONTEND_DIR/launcher-ui.js"
FRONTEND_PROFILES_FILE="$FRONTEND_DIR/profiles.js"
FRONTEND_SCHEDULE_FILE="$FRONTEND_DIR/schedule-controls.js"
FRONTEND_ACTIVITY_FILE="$FRONTEND_DIR/activity-dashboard.js"
FRONTEND_SETTINGS_FILE="$FRONTEND_DIR/parent-settings.js"
FRONTEND_FIRST_RUN_FILE="$FRONTEND_DIR/first-run.js"
FRONTEND_RUNTIME_FILE="$FRONTEND_DIR/runtime-controls.js"
MEDIA_FILE="$APP_ROOT/no-media.html"
UPDATE_SCRIPT="$APP_ROOT/update.sh"
AUTOSTART_FILE="$AUTOSTART_DIR/$AUTOSTART_FILE_ID"
DESKTOP_FILE="$DESKTOP_DIR/$DESKTOP_SHORTCUT_ID"
APP_DESKTOP_FILE="$TARGET_HOME/.local/share/applications/$DESKTOP_FILE_ID"
UNINSTALL_FILE="$APP_ROOT/uninstall.txt"
BACKUP_ROOT="$TARGET_HOME/.local/share/$APP_DIR_NAME-backups"
BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d-%H%M%S)"

mkdir -p "$APP_ROOT" "$FRONTEND_DIR" "$BIN_DIR" "$CFG_DIR" "$AUTOSTART_DIR" "$DESKTOP_DIR" "$CACHE_DIR" "$(dirname "$APP_DESKTOP_FILE")" "$BACKUP_ROOT"
[[ ! -L "$BACKUP_ROOT" ]] || die "Backup root must not be a symbolic link: $BACKUP_ROOT"
mkdir "$BACKUP_DIR" || die "Could not create a unique backup directory: $BACKUP_DIR"
chmod 0700 "$CFG_DIR" "$CACHE_DIR" "$BACKUP_ROOT" "$BACKUP_DIR"

backup_if_exists() {
  local path="$1"
  [[ -e "$path" ]] || return 0
  cp -a "$path" "$BACKUP_DIR/$(basename "$path")"
}

write_file() {
  local path="$1"
  local mode="$2"
  local tmp
  tmp="$(mktemp)"
  cat > "$tmp"
  if [[ -e "$path" && "$FORCE" != "1" ]]; then
    backup_if_exists "$path"
  fi
  install -m "$mode" "$tmp" "$path"
  rm -f "$tmp"
}

render_template() {
  local src="$1"
  local dest="$2"
  local mode="$3"

  if [[ ! -f "$src" ]]; then
    die "Template not found: $src"
  fi

  local tmp
  tmp="$(mktemp)"

  # Export all template variables so Python can see them
  export APP_ID DEFAULT_PORT BROWSER_CMD DEFAULT_THEME DEFAULT_LAYOUT
  export DEFAULT_LAUNCH_MODE INSTALL_SHUTDOWN_HELPER ACTIVE_LANG
  export DEFAULT_TITLE DEFAULT_PARENT_LABEL DEFAULT_EXIT_LABEL SHUTDOWN_LABEL
  export ADMIN_TITLE PLACEHOLDER_TITLE PLACEHOLDER_PARENT_LABEL PLACEHOLDER_EXIT_LABEL
  export LABEL_LAYOUT_LARGE LABEL_LAYOUT_SMALL LABEL_ADD_TILE LABEL_BACK LABEL_SAVE
  export LABEL_VISIBLE LABEL_SPECIAL_MEDIA LABEL_NO_APP LABEL_CUSTOM_CMD
  export LABEL_MOVE_UP LABEL_MOVE_DOWN LABEL_DELETE DEFAULT_NEW_TILE_LABEL
  export LABEL_COPY_COMMAND LABEL_CLOSE
  export LABEL_EXPORT_CONFIG LABEL_IMPORT_CONFIG LABEL_EXPORT_DIAGNOSTICS IMPORT_SUCCESS IMPORT_ERROR INVALID_CONFIG IMPORT_CONFIRM LABEL_PREVIEW_TITLE STARTING_APP EMPTY_STATE_EMOJI EMPTY_STATE_TEXT
  export BACKUP_TITLE BACKUP_RESTORE BACKUP_EMPTY BACKUP_LOADING BACKUP_LOAD_ERROR BACKUP_RESTORING BACKUP_CONFIRM BACKUP_SUCCESS BACKUP_ERROR BACKUP_INSTALLER BACKUP_PRE_RESTORE BACKUP_PIN_PRESERVED
  export JSON_BROWSER_PAGE JSON_WEB_MODE_EMBEDDED JSON_WEB_MODE_EXTERNAL
  export NO_MEDIA_TITLE NO_MEDIA_BODY NO_MEDIA_BACK
  export PIN_TITLE PIN_PLACEHOLDER PIN_WRONG PIN_SET PIN_CHANGE PIN_REMOVE PIN_CONFIRM PIN_MISMATCH PIN_SAVED PIN_REMOVED ADMIN_PAGE_PREV ADMIN_PAGE_NEXT
  export DEFAULT_TILE_PAINT DEFAULT_TILE_GAMES DEFAULT_TILE_MUSIC DEFAULT_TILE_BROWSER DEFAULT_BROWSER_URL
  export JSON_ADMIN_TITLE JSON_ADMIN_NAV_LABEL JSON_ADMIN_OVERVIEW JSON_ADMIN_CHILDREN JSON_ADMIN_APPS_MEDIA JSON_ADMIN_SCREEN_TIME JSON_ADMIN_APPEARANCE JSON_ADMIN_SYSTEM
  export JSON_APP_SEARCH_LABEL JSON_APP_FILTER_LABEL JSON_APP_FILTER_ALL JSON_APP_FILTER_VISIBLE JSON_APP_FILTER_HIDDEN JSON_APP_FILTER_EMPTY JSON_APP_FILTER_COUNT
  export JSON_APP_BULK_ACTIONS JSON_APP_BULK_SELECT_ALL JSON_APP_BULK_SELECTED JSON_APP_BULK_SHOW JSON_APP_BULK_HIDE JSON_APP_BULK_DELETE JSON_APP_BULK_DELETE_CONFIRM JSON_APP_SELECT_TILE
  export JSON_CONFIRM_TITLE JSON_CONFIRM_CANCEL JSON_CONFIRM_CONTINUE
  export STARTUP_LOADING
  export JSON_RETRY JSON_STARTUP_LOADING JSON_STARTUP_ERROR_TITLE JSON_STARTUP_ERROR JSON_SAVE_LOADING JSON_SAVE_ERROR
  export JSON_APP_CATALOG_LOADING JSON_APP_CATALOG_EMPTY JSON_APP_CATALOG_ERROR JSON_BROWSER_CATALOG_LOADING JSON_BROWSER_CATALOG_EMPTY JSON_BROWSER_CATALOG_ERROR
  export JSON_RECOMMENDATIONS_LOADING JSON_RECOMMENDATIONS_EMPTY JSON_RECOMMENDATIONS_ERROR
  export JSON_PLACEHOLDER_TITLE JSON_PLACEHOLDER_PARENT_LABEL JSON_PLACEHOLDER_EXIT_LABEL
  export JSON_ADD_TILE JSON_BACK JSON_SAVE JSON_VISIBLE JSON_SPECIAL_MEDIA
  export JSON_NO_APP JSON_CUSTOM_CMD JSON_MOVE_UP JSON_MOVE_DOWN JSON_DELETE JSON_NEW_TILE
  export JSON_PIN_TITLE JSON_PIN_PLACEHOLDER JSON_PIN_WRONG JSON_PIN_SET JSON_PIN_CHANGE JSON_PIN_REMOVE JSON_PIN_CONFIRM JSON_PIN_MISMATCH JSON_PIN_SAVED JSON_PIN_REMOVED JSON_ADMIN_PAGE_PREV JSON_ADMIN_PAGE_NEXT
  export JSON_UPDATE_CHECK JSON_UPDATE_AVAILABLE JSON_UPDATE_UP_TO_DATE JSON_UPDATE_LOADING JSON_UPDATE_ERROR JSON_VERSION_LABEL JSON_UPDATE_NOW JSON_UPDATE_PROGRESS JSON_UPDATE_CONFIRM
  export JSON_EXPORT_CONFIG JSON_IMPORT_CONFIG JSON_EXPORT_DIAGNOSTICS JSON_IMPORT_SUCCESS JSON_IMPORT_ERROR JSON_INVALID_CONFIG JSON_IMPORT_CONFIRM
  export JSON_BACKUP_TITLE JSON_BACKUP_RESTORE JSON_BACKUP_EMPTY JSON_BACKUP_LOADING JSON_BACKUP_LOAD_ERROR JSON_BACKUP_RESTORING JSON_BACKUP_CONFIRM JSON_BACKUP_SUCCESS JSON_BACKUP_ERROR JSON_BACKUP_INSTALLER JSON_BACKUP_PRE_RESTORE JSON_BACKUP_PIN_PRESERVED
  export JSON_ACTIVITY_TITLE JSON_ACTIVITY_HINT JSON_ACTIVITY_ENABLED JSON_ACTIVITY_ENABLED_STATUS JSON_ACTIVITY_DISABLED_STATUS JSON_ACTIVITY_TIME JSON_ACTIVITY_LAUNCHES JSON_ACTIVITY_RECENT JSON_ACTIVITY_EMPTY JSON_ACTIVITY_LOADING JSON_ACTIVITY_ERROR JSON_ACTIVITY_EXPORT JSON_ACTIVITY_CLEAR JSON_ACTIVITY_CLEAR_CONFIRM JSON_ACTIVITY_CLEAR_SUCCESS JSON_ACTIVITY_CLEAR_ERROR JSON_ACTIVITY_UNKNOWN_PROFILE JSON_ACTIVITY_UNKNOWN_APP JSON_ACTIVITY_LESS_MINUTE JSON_ACTIVITY_MINUTES JSON_ACTIVITY_HOURS_MINUTES
  export UPDATE_CHECK UPDATE_AVAILABLE UPDATE_UP_TO_DATE UPDATE_ERROR VERSION_LABEL UPDATE_NOW UPDATE_PROGRESS UPDATE_CONFIRM
  export RUNTIME_FAILURE_TITLE RUNTIME_FAILURE_BODY
  export RECOMMENDED_TITLE RECOMMENDED_INSTALLED RECOMMENDED_NOT_INSTALLED RECOMMENDED_PROMPT
  export JSON_RECOMMENDED_TITLE JSON_RECOMMENDED_INSTALLED JSON_RECOMMENDED_NOT_INSTALLED JSON_RECOMMENDED_PROMPT
  export JSON_APP_BROWSER_TITLE JSON_INSTALL JSON_ADDED JSON_INSTALLED JSON_NOT_INSTALLED JSON_COPY_COMMAND JSON_COMMAND_COPIED JSON_INSTALL_STARTED JSON_INSTALL_MANUAL JSON_CLOSE
  export TIMER_LABEL TIMER_OFF TIMER_15 TIMER_30 TIMER_60 TIMER_CUSTOM TIMER_START TIMER_STOP TIMER_ACTIVE TIMER_EXPIRED TIMER_REMAINING TIMER_WARNING_TITLE TIMER_WARNING_TEXT TIMER_ENTER_PIN TIMER_EXTEND TIMER_EXIT TIMER_WRONG_PIN TIMER_EXTENDED TIMER_EXPIRED_TITLE TIMER_EXPIRED_BODY TIMER_MINUTES
  export JSON_TIMER_LABEL JSON_TIMER_OFF JSON_TIMER_15 JSON_TIMER_30 JSON_TIMER_60 JSON_TIMER_MINUTES JSON_TIMER_CUSTOM JSON_TIMER_START JSON_TIMER_STOP JSON_TIMER_ACTIVE JSON_TIMER_EXPIRED JSON_TIMER_REMAINING JSON_TIMER_WARNING_TITLE JSON_TIMER_WARNING_TEXT JSON_TIMER_ENTER_PIN JSON_TIMER_EXTEND JSON_TIMER_EXIT JSON_TIMER_WRONG_PIN JSON_TIMER_EXTENDED JSON_STARTING_APP JSON_EMPTY_STATE_EMOJI JSON_EMPTY_STATE_TEXT JSON_PREVIEW_TITLE
  export JSON_SCHEDULE_WEEKLY_TITLE JSON_SCHEDULE_WEEKLY_HINT JSON_SCHEDULE_ENABLED JSON_SCHEDULE_APP_TITLE JSON_SCHEDULE_APP_HINT JSON_SCHEDULE_SELECT_APP JSON_SCHEDULE_ADD_WINDOW JSON_SCHEDULE_REMOVE_WINDOW JSON_SCHEDULE_START JSON_SCHEDULE_END JSON_SCHEDULE_CLEAR_APP JSON_SCHEDULE_NO_WINDOWS JSON_SCHEDULE_BLOCKED_TITLE JSON_SCHEDULE_PROFILE_BLOCKED JSON_SCHEDULE_APP_BLOCKED JSON_SCHEDULE_OPEN_PARENTS
  export JSON_WEEKDAY_MONDAY JSON_WEEKDAY_TUESDAY JSON_WEEKDAY_WEDNESDAY JSON_WEEKDAY_THURSDAY JSON_WEEKDAY_FRIDAY JSON_WEEKDAY_SATURDAY JSON_WEEKDAY_SUNDAY
  export APP_NAME

  python3 - "$src" "$tmp" <<'PY'
import sys, os, re
src, dst = sys.argv[1], sys.argv[2]
with open(src, 'r', encoding='utf-8') as f:
    content = f.read()

def replacer(m):
    key = m.group(1)
    return os.environ.get(key, m.group(0))

content = re.sub(r'\{\{(\w+)\}\}', replacer, content)
with open(dst, 'w', encoding='utf-8') as f:
    f.write(content)
PY

  if [[ -e "$dest" && "$FORCE" != "1" ]]; then
    backup_if_exists "$dest"
  fi
  install -m "$mode" "$tmp" "$dest"
  rm -f "$tmp"
}

DEFAULT_TITLE="$(trim "${DEFAULT_TITLE:-$(text config_title)}")"
DEFAULT_PARENT_LABEL="$(trim "${DEFAULT_PARENT_LABEL:-$(text parent_label)}")"
DEFAULT_EXIT_LABEL="$(trim "${DEFAULT_EXIT_LABEL:-$(text exit_label)}")"
SHUTDOWN_LABEL="$(text shutdown_label)"
SHORTCUT_NAME="$(text shortcut_name)"
AUTOSTART_NAME="$(text autostart_name)"
APP_NAME="$(text app_name)"
NO_MEDIA_TITLE="$(text no_media_title)"
NO_MEDIA_BODY="$(text no_media_body)"
NO_MEDIA_BACK="$(text no_media_back)"
ADMIN_TITLE="$(text admin_title)"
ADMIN_NAV_LABEL="$(text admin_nav_label)"
ADMIN_OVERVIEW="$(text admin_overview)"
ADMIN_CHILDREN="$(text admin_children)"
ADMIN_APPS_MEDIA="$(text admin_apps_media)"
ADMIN_SCREEN_TIME="$(text admin_screen_time)"
ADMIN_APPEARANCE="$(text admin_appearance)"
ADMIN_SYSTEM="$(text admin_system)"
APP_SEARCH_LABEL="$(text app_search_label)"
APP_FILTER_LABEL="$(text app_filter_label)"
APP_FILTER_ALL="$(text app_filter_all)"
APP_FILTER_VISIBLE="$(text app_filter_visible)"
APP_FILTER_HIDDEN="$(text app_filter_hidden)"
APP_FILTER_EMPTY="$(text app_filter_empty)"
APP_FILTER_COUNT="$(text app_filter_count)"
APP_BULK_ACTIONS="$(text app_bulk_actions)"
APP_BULK_SELECT_ALL="$(text app_bulk_select_all)"
APP_BULK_SELECTED="$(text app_bulk_selected)"
APP_BULK_SHOW="$(text app_bulk_show)"
APP_BULK_HIDE="$(text app_bulk_hide)"
APP_BULK_DELETE="$(text app_bulk_delete)"
APP_BULK_DELETE_CONFIRM="$(text app_bulk_delete_confirm)"
APP_SELECT_TILE="$(text app_select_tile)"
CONFIRM_TITLE="$(text confirm_title)"
CONFIRM_CANCEL="$(text confirm_cancel)"
CONFIRM_CONTINUE="$(text confirm_continue)"
RETRY="$(text retry)"
STARTUP_LOADING="$(text startup_loading)"
STARTUP_ERROR_TITLE="$(text startup_error_title)"
STARTUP_ERROR="$(text startup_error)"
SAVE_LOADING="$(text save_loading)"
SAVE_ERROR="$(text save_error)"
APP_CATALOG_LOADING="$(text app_catalog_loading)"
APP_CATALOG_EMPTY="$(text app_catalog_empty)"
APP_CATALOG_ERROR="$(text app_catalog_error)"
BROWSER_CATALOG_LOADING="$(text browser_catalog_loading)"
BROWSER_CATALOG_EMPTY="$(text browser_catalog_empty)"
BROWSER_CATALOG_ERROR="$(text browser_catalog_error)"
RECOMMENDATIONS_LOADING="$(text recommendations_loading)"
RECOMMENDATIONS_EMPTY="$(text recommendations_empty)"
RECOMMENDATIONS_ERROR="$(text recommendations_error)"
PLACEHOLDER_TITLE="$(text placeholder_title)"
PLACEHOLDER_PARENT_LABEL="$(text placeholder_parent_label)"
PLACEHOLDER_EXIT_LABEL="$(text placeholder_exit_label)"
LABEL_ADD_TILE="$(text add_tile)"
LABEL_BACK="$(text back)"
LABEL_SAVE="$(text save)"
LABEL_LAYOUT_LARGE="$(text layout_large)"
LABEL_LAYOUT_SMALL="$(text layout_small)"
LABEL_VISIBLE="$(text visible)"
LABEL_SPECIAL_MEDIA="$(text special_media)"
LABEL_NO_APP="$(text no_app)"
LABEL_CUSTOM_CMD="$(text custom_cmd)"
LABEL_MOVE_UP="$(text move_up)"
LABEL_MOVE_DOWN="$(text move_down)"
LABEL_DELETE="$(text delete)"
DEFAULT_NEW_TILE_LABEL="$(text new_tile)"
PIN_TITLE="$(text pin_title)"
PIN_PLACEHOLDER="$(text pin_placeholder)"
PIN_WRONG="$(text pin_wrong)"
PIN_SET="$(text pin_set)"
PIN_CHANGE="$(text pin_change)"
PIN_REMOVE="$(text pin_remove)"
PIN_CONFIRM="$(text pin_confirm)"
PIN_MISMATCH="$(text pin_mismatch)"
PIN_SAVED="$(text pin_saved)"
PIN_REMOVED="$(text pin_removed)"
ADMIN_PAGE_PREV="$(text admin_page_prev)"
ADMIN_PAGE_NEXT="$(text admin_page_next)"
UPDATE_CHECK="$(text update_check)"
UPDATE_AVAILABLE="$(text update_available)"
UPDATE_UP_TO_DATE="$(text update_up_to_date)"
UPDATE_LOADING="$(text update_loading)"
UPDATE_ERROR="$(text update_error)"
VERSION_LABEL="$(text version_label)"
UPDATE_NOW="$(text update_now)"
UPDATE_PROGRESS="$(text update_progress)"
UPDATE_CONFIRM="$(text update_confirm)"
RUNTIME_FAILURE_TITLE="$(text runtime_failure_title)"
RUNTIME_FAILURE_BODY="$(text runtime_failure_body)"
DEFAULT_TILE_PAINT="$(text tile_paint)"
DEFAULT_TILE_GAMES="$(text tile_games)"
DEFAULT_TILE_MUSIC="$(text tile_music)"
DEFAULT_TILE_BROWSER="$(text tile_browser)"
DEFAULT_BROWSER_URL="$(text browser_url)"
RECOMMENDED_TITLE="$(text recommended_title)"
RECOMMENDED_INSTALLED="$(text recommended_installed)"
RECOMMENDED_NOT_INSTALLED="$(text recommended_not_installed)"
RECOMMENDED_PROMPT="$(text recommended_prompt)"
APP_BROWSER_TITLE="$(text app_browser_title)"
BROWSER_PAGE="$(text browser_page)"
WEB_MODE_EMBEDDED="$(text web_mode_embedded)"
WEB_MODE_EXTERNAL="$(text web_mode_external)"
LABEL_INSTALL="$(text install)"
LABEL_ADDED="$(text added)"
LABEL_INSTALLED="$(text installed)"
LABEL_NOT_INSTALLED="$(text not_installed)"
LABEL_COPY_COMMAND="$(text copy_command)"
LABEL_COMMAND_COPIED="$(text command_copied)"
LABEL_INSTALL_STARTED="$(text install_started)"
LABEL_INSTALL_MANUAL="$(text install_manual)"
LABEL_CLOSE="$(text close)"
LABEL_EXPORT_CONFIG="$(text export_config)"
LABEL_IMPORT_CONFIG="$(text import_config)"
LABEL_EXPORT_DIAGNOSTICS="$(text export_diagnostics)"
IMPORT_SUCCESS="$(text import_success)"
IMPORT_ERROR="$(text import_error)"
INVALID_CONFIG="$(text invalid_config)"
IMPORT_CONFIRM="$(text import_confirm)"
BACKUP_TITLE="$(text backup_title)"
BACKUP_RESTORE="$(text backup_restore)"
BACKUP_EMPTY="$(text backup_empty)"
BACKUP_LOADING="$(text backup_loading)"
BACKUP_LOAD_ERROR="$(text backup_load_error)"
BACKUP_RESTORING="$(text backup_restoring)"
BACKUP_CONFIRM="$(text backup_confirm)"
BACKUP_SUCCESS="$(text backup_success)"
BACKUP_ERROR="$(text backup_error)"
BACKUP_INSTALLER="$(text backup_installer)"
BACKUP_PRE_RESTORE="$(text backup_pre_restore)"
BACKUP_PIN_PRESERVED="$(text backup_pin_preserved)"
ACTIVITY_TITLE="$(text activity_title)"
ACTIVITY_HINT="$(text activity_hint)"
ACTIVITY_ENABLED="$(text activity_enabled)"
ACTIVITY_ENABLED_STATUS="$(text activity_enabled_status)"
ACTIVITY_DISABLED_STATUS="$(text activity_disabled_status)"
ACTIVITY_TIME="$(text activity_time)"
ACTIVITY_LAUNCHES="$(text activity_launches)"
ACTIVITY_RECENT="$(text activity_recent)"
ACTIVITY_EMPTY="$(text activity_empty)"
ACTIVITY_LOADING="$(text activity_loading)"
ACTIVITY_ERROR="$(text activity_error)"
ACTIVITY_EXPORT="$(text activity_export)"
ACTIVITY_CLEAR="$(text activity_clear)"
ACTIVITY_CLEAR_CONFIRM="$(text activity_clear_confirm)"
ACTIVITY_CLEAR_SUCCESS="$(text activity_clear_success)"
ACTIVITY_CLEAR_ERROR="$(text activity_clear_error)"
ACTIVITY_UNKNOWN_PROFILE="$(text activity_unknown_profile)"
ACTIVITY_UNKNOWN_APP="$(text activity_unknown_app)"
ACTIVITY_LESS_MINUTE="$(text activity_less_minute)"
ACTIVITY_MINUTES="$(text activity_minutes)"
ACTIVITY_HOURS_MINUTES="$(text activity_hours_minutes)"
TIMER_LABEL="$(text timer_label)"
TIMER_OFF="$(text timer_off)"
TIMER_15="$(text timer_15)"
TIMER_30="$(text timer_30)"
TIMER_60="$(text timer_60)"
TIMER_CUSTOM="$(text timer_custom)"
TIMER_START="$(text timer_start)"
TIMER_STOP="$(text timer_stop)"
TIMER_ACTIVE="$(text timer_active)"
TIMER_EXPIRED="$(text timer_expired)"
TIMER_REMAINING="$(text timer_remaining)"
TIMER_WARNING_TITLE="$(text timer_warning_title)"
TIMER_WARNING_TEXT="$(text timer_warning_text)"
TIMER_ENTER_PIN="$(text timer_enter_pin)"
TIMER_EXTEND="$(text timer_extend)"
TIMER_EXIT="$(text timer_exit)"
TIMER_WRONG_PIN="$(text timer_wrong_pin)"
TIMER_EXTENDED="$(text timer_extended)"
TIMER_EXPIRED_TITLE="$(text timer_expired_title)"
TIMER_EXPIRED_BODY="$(text timer_expired_body)"
TIMER_MINUTES="$(text timer_minutes)"
SCHEDULE_WEEKLY_TITLE="$(text schedule_weekly_title)"
SCHEDULE_WEEKLY_HINT="$(text schedule_weekly_hint)"
SCHEDULE_ENABLED="$(text schedule_enabled)"
SCHEDULE_APP_TITLE="$(text schedule_app_title)"
SCHEDULE_APP_HINT="$(text schedule_app_hint)"
SCHEDULE_SELECT_APP="$(text schedule_select_app)"
SCHEDULE_ADD_WINDOW="$(text schedule_add_window)"
SCHEDULE_REMOVE_WINDOW="$(text schedule_remove_window)"
SCHEDULE_START="$(text schedule_start)"
SCHEDULE_END="$(text schedule_end)"
SCHEDULE_CLEAR_APP="$(text schedule_clear_app)"
SCHEDULE_NO_WINDOWS="$(text schedule_no_windows)"
SCHEDULE_BLOCKED_TITLE="$(text schedule_blocked_title)"
SCHEDULE_PROFILE_BLOCKED="$(text schedule_profile_blocked)"
SCHEDULE_APP_BLOCKED="$(text schedule_app_blocked)"
SCHEDULE_OPEN_PARENTS="$(text schedule_open_parents)"
WEEKDAY_MONDAY="$(text weekday_monday)"
WEEKDAY_TUESDAY="$(text weekday_tuesday)"
WEEKDAY_WEDNESDAY="$(text weekday_wednesday)"
WEEKDAY_THURSDAY="$(text weekday_thursday)"
WEEKDAY_FRIDAY="$(text weekday_friday)"
WEEKDAY_SATURDAY="$(text weekday_saturday)"
WEEKDAY_SUNDAY="$(text weekday_sunday)"
LABEL_PREVIEW_TITLE="$(text preview_title)"
STARTING_APP="$(text starting_app)"
EMPTY_STATE_EMOJI="$(text empty_state_emoji)"
EMPTY_STATE_TEXT="$(text empty_state_text)"
PREVIEW_TITLE="$(text preview_title)"

JSON_ADMIN_TITLE="$(json_text "$ADMIN_TITLE")"
JSON_ADMIN_NAV_LABEL="$(json_text "$ADMIN_NAV_LABEL")"
JSON_ADMIN_OVERVIEW="$(json_text "$ADMIN_OVERVIEW")"
JSON_ADMIN_CHILDREN="$(json_text "$ADMIN_CHILDREN")"
JSON_ADMIN_APPS_MEDIA="$(json_text "$ADMIN_APPS_MEDIA")"
JSON_ADMIN_SCREEN_TIME="$(json_text "$ADMIN_SCREEN_TIME")"
JSON_ADMIN_APPEARANCE="$(json_text "$ADMIN_APPEARANCE")"
JSON_ADMIN_SYSTEM="$(json_text "$ADMIN_SYSTEM")"
JSON_APP_SEARCH_LABEL="$(json_text "$APP_SEARCH_LABEL")"
JSON_APP_FILTER_LABEL="$(json_text "$APP_FILTER_LABEL")"
JSON_APP_FILTER_ALL="$(json_text "$APP_FILTER_ALL")"
JSON_APP_FILTER_VISIBLE="$(json_text "$APP_FILTER_VISIBLE")"
JSON_APP_FILTER_HIDDEN="$(json_text "$APP_FILTER_HIDDEN")"
JSON_APP_FILTER_EMPTY="$(json_text "$APP_FILTER_EMPTY")"
JSON_APP_FILTER_COUNT="$(json_text "$APP_FILTER_COUNT")"
JSON_APP_BULK_ACTIONS="$(json_text "$APP_BULK_ACTIONS")"
JSON_APP_BULK_SELECT_ALL="$(json_text "$APP_BULK_SELECT_ALL")"
JSON_APP_BULK_SELECTED="$(json_text "$APP_BULK_SELECTED")"
JSON_APP_BULK_SHOW="$(json_text "$APP_BULK_SHOW")"
JSON_APP_BULK_HIDE="$(json_text "$APP_BULK_HIDE")"
JSON_APP_BULK_DELETE="$(json_text "$APP_BULK_DELETE")"
JSON_APP_BULK_DELETE_CONFIRM="$(json_text "$APP_BULK_DELETE_CONFIRM")"
JSON_APP_SELECT_TILE="$(json_text "$APP_SELECT_TILE")"
JSON_CONFIRM_TITLE="$(json_text "$CONFIRM_TITLE")"
JSON_CONFIRM_CANCEL="$(json_text "$CONFIRM_CANCEL")"
JSON_CONFIRM_CONTINUE="$(json_text "$CONFIRM_CONTINUE")"
JSON_RETRY="$(json_text "$RETRY")"
JSON_STARTUP_LOADING="$(json_text "$STARTUP_LOADING")"
JSON_STARTUP_ERROR_TITLE="$(json_text "$STARTUP_ERROR_TITLE")"
JSON_STARTUP_ERROR="$(json_text "$STARTUP_ERROR")"
JSON_SAVE_LOADING="$(json_text "$SAVE_LOADING")"
JSON_SAVE_ERROR="$(json_text "$SAVE_ERROR")"
JSON_APP_CATALOG_LOADING="$(json_text "$APP_CATALOG_LOADING")"
JSON_APP_CATALOG_EMPTY="$(json_text "$APP_CATALOG_EMPTY")"
JSON_APP_CATALOG_ERROR="$(json_text "$APP_CATALOG_ERROR")"
JSON_BROWSER_CATALOG_LOADING="$(json_text "$BROWSER_CATALOG_LOADING")"
JSON_BROWSER_CATALOG_EMPTY="$(json_text "$BROWSER_CATALOG_EMPTY")"
JSON_BROWSER_CATALOG_ERROR="$(json_text "$BROWSER_CATALOG_ERROR")"
JSON_RECOMMENDATIONS_LOADING="$(json_text "$RECOMMENDATIONS_LOADING")"
JSON_RECOMMENDATIONS_EMPTY="$(json_text "$RECOMMENDATIONS_EMPTY")"
JSON_RECOMMENDATIONS_ERROR="$(json_text "$RECOMMENDATIONS_ERROR")"
JSON_PLACEHOLDER_TITLE="$(json_text "$PLACEHOLDER_TITLE")"
JSON_PLACEHOLDER_PARENT_LABEL="$(json_text "$PLACEHOLDER_PARENT_LABEL")"
JSON_PLACEHOLDER_EXIT_LABEL="$(json_text "$PLACEHOLDER_EXIT_LABEL")"
JSON_ADD_TILE="$(json_text "$LABEL_ADD_TILE")"
JSON_BACK="$(json_text "$LABEL_BACK")"
JSON_SAVE="$(json_text "$LABEL_SAVE")"
JSON_VISIBLE="$(json_text "$LABEL_VISIBLE")"
JSON_SPECIAL_MEDIA="$(json_text "$LABEL_SPECIAL_MEDIA")"
JSON_NO_APP="$(json_text "$LABEL_NO_APP")"
JSON_CUSTOM_CMD="$(json_text "$LABEL_CUSTOM_CMD")"
JSON_MOVE_UP="$(json_text "$LABEL_MOVE_UP")"
JSON_MOVE_DOWN="$(json_text "$LABEL_MOVE_DOWN")"
JSON_DELETE="$(json_text "$LABEL_DELETE")"
JSON_NEW_TILE="$(json_text "$DEFAULT_NEW_TILE_LABEL")"
JSON_PIN_TITLE="$(json_text "$PIN_TITLE")"
JSON_PIN_PLACEHOLDER="$(json_text "$PIN_PLACEHOLDER")"
JSON_PIN_WRONG="$(json_text "$PIN_WRONG")"
JSON_PIN_SET="$(json_text "$PIN_SET")"
JSON_PIN_CHANGE="$(json_text "$PIN_CHANGE")"
JSON_PIN_REMOVE="$(json_text "$PIN_REMOVE")"
JSON_PIN_CONFIRM="$(json_text "$PIN_CONFIRM")"
JSON_PIN_MISMATCH="$(json_text "$PIN_MISMATCH")"
JSON_PIN_SAVED="$(json_text "$PIN_SAVED")"
JSON_PIN_REMOVED="$(json_text "$PIN_REMOVED")"
JSON_ADMIN_PAGE_PREV="$(json_text "$ADMIN_PAGE_PREV")"
JSON_ADMIN_PAGE_NEXT="$(json_text "$ADMIN_PAGE_NEXT")"
JSON_UPDATE_CHECK="$(json_text "$UPDATE_CHECK")"
JSON_UPDATE_AVAILABLE="$(json_text "$UPDATE_AVAILABLE")"
JSON_UPDATE_UP_TO_DATE="$(json_text "$UPDATE_UP_TO_DATE")"
JSON_UPDATE_LOADING="$(json_text "$UPDATE_LOADING")"
JSON_UPDATE_ERROR="$(json_text "$UPDATE_ERROR")"
JSON_VERSION_LABEL="$(json_text "$VERSION_LABEL")"
JSON_UPDATE_NOW="$(json_text "$UPDATE_NOW")"
JSON_UPDATE_PROGRESS="$(json_text "$UPDATE_PROGRESS")"
JSON_UPDATE_CONFIRM="$(json_text "$UPDATE_CONFIRM")"
JSON_RECOMMENDED_TITLE="$(json_text "$RECOMMENDED_TITLE")"
JSON_RECOMMENDED_INSTALLED="$(json_text "$RECOMMENDED_INSTALLED")"
JSON_RECOMMENDED_NOT_INSTALLED="$(json_text "$RECOMMENDED_NOT_INSTALLED")"
JSON_RECOMMENDED_PROMPT="$(json_text "$RECOMMENDED_PROMPT")"
JSON_APP_BROWSER_TITLE="$(json_text "$APP_BROWSER_TITLE")"
JSON_BROWSER_PAGE="$(json_text "$BROWSER_PAGE")"
JSON_WEB_MODE_EMBEDDED="$(json_text "$WEB_MODE_EMBEDDED")"
JSON_WEB_MODE_EXTERNAL="$(json_text "$WEB_MODE_EXTERNAL")"
JSON_INSTALL="$(json_text "$LABEL_INSTALL")"
JSON_ADDED="$(json_text "$LABEL_ADDED")"
JSON_INSTALLED="$(json_text "$LABEL_INSTALLED")"
JSON_NOT_INSTALLED="$(json_text "$LABEL_NOT_INSTALLED")"
JSON_COPY_COMMAND="$(json_text "$LABEL_COPY_COMMAND")"
JSON_COMMAND_COPIED="$(json_text "$LABEL_COMMAND_COPIED")"
JSON_INSTALL_STARTED="$(json_text "$LABEL_INSTALL_STARTED")"
JSON_INSTALL_MANUAL="$(json_text "$LABEL_INSTALL_MANUAL")"
JSON_CLOSE="$(json_text "$LABEL_CLOSE")"
JSON_EXPORT_CONFIG="$(json_text "$LABEL_EXPORT_CONFIG")"
JSON_IMPORT_CONFIG="$(json_text "$LABEL_IMPORT_CONFIG")"
JSON_EXPORT_DIAGNOSTICS="$(json_text "$LABEL_EXPORT_DIAGNOSTICS")"
JSON_IMPORT_SUCCESS="$(json_text "$IMPORT_SUCCESS")"
JSON_IMPORT_ERROR="$(json_text "$IMPORT_ERROR")"
JSON_INVALID_CONFIG="$(json_text "$INVALID_CONFIG")"
JSON_IMPORT_CONFIRM="$(json_text "$IMPORT_CONFIRM")"
JSON_BACKUP_TITLE="$(json_text "$BACKUP_TITLE")"
JSON_BACKUP_RESTORE="$(json_text "$BACKUP_RESTORE")"
JSON_BACKUP_EMPTY="$(json_text "$BACKUP_EMPTY")"
JSON_BACKUP_LOADING="$(json_text "$BACKUP_LOADING")"
JSON_BACKUP_LOAD_ERROR="$(json_text "$BACKUP_LOAD_ERROR")"
JSON_BACKUP_RESTORING="$(json_text "$BACKUP_RESTORING")"
JSON_BACKUP_CONFIRM="$(json_text "$BACKUP_CONFIRM")"
JSON_BACKUP_SUCCESS="$(json_text "$BACKUP_SUCCESS")"
JSON_BACKUP_ERROR="$(json_text "$BACKUP_ERROR")"
JSON_BACKUP_INSTALLER="$(json_text "$BACKUP_INSTALLER")"
JSON_BACKUP_PRE_RESTORE="$(json_text "$BACKUP_PRE_RESTORE")"
JSON_BACKUP_PIN_PRESERVED="$(json_text "$BACKUP_PIN_PRESERVED")"
JSON_ACTIVITY_TITLE="$(json_text "$ACTIVITY_TITLE")"
JSON_ACTIVITY_HINT="$(json_text "$ACTIVITY_HINT")"
JSON_ACTIVITY_ENABLED="$(json_text "$ACTIVITY_ENABLED")"
JSON_ACTIVITY_ENABLED_STATUS="$(json_text "$ACTIVITY_ENABLED_STATUS")"
JSON_ACTIVITY_DISABLED_STATUS="$(json_text "$ACTIVITY_DISABLED_STATUS")"
JSON_ACTIVITY_TIME="$(json_text "$ACTIVITY_TIME")"
JSON_ACTIVITY_LAUNCHES="$(json_text "$ACTIVITY_LAUNCHES")"
JSON_ACTIVITY_RECENT="$(json_text "$ACTIVITY_RECENT")"
JSON_ACTIVITY_EMPTY="$(json_text "$ACTIVITY_EMPTY")"
JSON_ACTIVITY_LOADING="$(json_text "$ACTIVITY_LOADING")"
JSON_ACTIVITY_ERROR="$(json_text "$ACTIVITY_ERROR")"
JSON_ACTIVITY_EXPORT="$(json_text "$ACTIVITY_EXPORT")"
JSON_ACTIVITY_CLEAR="$(json_text "$ACTIVITY_CLEAR")"
JSON_ACTIVITY_CLEAR_CONFIRM="$(json_text "$ACTIVITY_CLEAR_CONFIRM")"
JSON_ACTIVITY_CLEAR_SUCCESS="$(json_text "$ACTIVITY_CLEAR_SUCCESS")"
JSON_ACTIVITY_CLEAR_ERROR="$(json_text "$ACTIVITY_CLEAR_ERROR")"
JSON_ACTIVITY_UNKNOWN_PROFILE="$(json_text "$ACTIVITY_UNKNOWN_PROFILE")"
JSON_ACTIVITY_UNKNOWN_APP="$(json_text "$ACTIVITY_UNKNOWN_APP")"
JSON_ACTIVITY_LESS_MINUTE="$(json_text "$ACTIVITY_LESS_MINUTE")"
JSON_ACTIVITY_MINUTES="$(json_text "$ACTIVITY_MINUTES")"
JSON_ACTIVITY_HOURS_MINUTES="$(json_text "$ACTIVITY_HOURS_MINUTES")"
JSON_TIMER_LABEL="$(json_text "$TIMER_LABEL")"
JSON_TIMER_OFF="$(json_text "$TIMER_OFF")"
JSON_TIMER_15="$(json_text "$TIMER_15")"
JSON_TIMER_30="$(json_text "$TIMER_30")"
JSON_TIMER_60="$(json_text "$TIMER_60")"
JSON_TIMER_MINUTES="$(json_text "$TIMER_MINUTES")"
JSON_TIMER_CUSTOM="$(json_text "$TIMER_CUSTOM")"
JSON_TIMER_START="$(json_text "$TIMER_START")"
JSON_TIMER_STOP="$(json_text "$TIMER_STOP")"
JSON_TIMER_ACTIVE="$(json_text "$TIMER_ACTIVE")"
JSON_TIMER_EXPIRED="$(json_text "$TIMER_EXPIRED")"
JSON_TIMER_REMAINING="$(json_text "$TIMER_REMAINING")"
JSON_TIMER_WARNING_TITLE="$(json_text "$TIMER_WARNING_TITLE")"
JSON_TIMER_WARNING_TEXT="$(json_text "$TIMER_WARNING_TEXT")"
JSON_TIMER_ENTER_PIN="$(json_text "$TIMER_ENTER_PIN")"
JSON_TIMER_EXTEND="$(json_text "$TIMER_EXTEND")"
JSON_TIMER_EXIT="$(json_text "$TIMER_EXIT")"
JSON_TIMER_WRONG_PIN="$(json_text "$TIMER_WRONG_PIN")"
JSON_TIMER_EXTENDED="$(json_text "$TIMER_EXTENDED")"
JSON_SCHEDULE_WEEKLY_TITLE="$(json_text "$SCHEDULE_WEEKLY_TITLE")"
JSON_SCHEDULE_WEEKLY_HINT="$(json_text "$SCHEDULE_WEEKLY_HINT")"
JSON_SCHEDULE_ENABLED="$(json_text "$SCHEDULE_ENABLED")"
JSON_SCHEDULE_APP_TITLE="$(json_text "$SCHEDULE_APP_TITLE")"
JSON_SCHEDULE_APP_HINT="$(json_text "$SCHEDULE_APP_HINT")"
JSON_SCHEDULE_SELECT_APP="$(json_text "$SCHEDULE_SELECT_APP")"
JSON_SCHEDULE_ADD_WINDOW="$(json_text "$SCHEDULE_ADD_WINDOW")"
JSON_SCHEDULE_REMOVE_WINDOW="$(json_text "$SCHEDULE_REMOVE_WINDOW")"
JSON_SCHEDULE_START="$(json_text "$SCHEDULE_START")"
JSON_SCHEDULE_END="$(json_text "$SCHEDULE_END")"
JSON_SCHEDULE_CLEAR_APP="$(json_text "$SCHEDULE_CLEAR_APP")"
JSON_SCHEDULE_NO_WINDOWS="$(json_text "$SCHEDULE_NO_WINDOWS")"
JSON_SCHEDULE_BLOCKED_TITLE="$(json_text "$SCHEDULE_BLOCKED_TITLE")"
JSON_SCHEDULE_PROFILE_BLOCKED="$(json_text "$SCHEDULE_PROFILE_BLOCKED")"
JSON_SCHEDULE_APP_BLOCKED="$(json_text "$SCHEDULE_APP_BLOCKED")"
JSON_SCHEDULE_OPEN_PARENTS="$(json_text "$SCHEDULE_OPEN_PARENTS")"
JSON_WEEKDAY_MONDAY="$(json_text "$WEEKDAY_MONDAY")"
JSON_WEEKDAY_TUESDAY="$(json_text "$WEEKDAY_TUESDAY")"
JSON_WEEKDAY_WEDNESDAY="$(json_text "$WEEKDAY_WEDNESDAY")"
JSON_WEEKDAY_THURSDAY="$(json_text "$WEEKDAY_THURSDAY")"
JSON_WEEKDAY_FRIDAY="$(json_text "$WEEKDAY_FRIDAY")"
JSON_WEEKDAY_SATURDAY="$(json_text "$WEEKDAY_SATURDAY")"
JSON_WEEKDAY_SUNDAY="$(json_text "$WEEKDAY_SUNDAY")"
JSON_STARTING_APP="$(json_text "$STARTING_APP")"
JSON_EMPTY_STATE_EMOJI="$(json_text "$EMPTY_STATE_EMOJI")"
JSON_EMPTY_STATE_TEXT="$(json_text "$EMPTY_STATE_TEXT")"
JSON_PREVIEW_TITLE="$(json_text "$PREVIEW_TITLE")"

backup_if_exists "$RUNTIME_BIN"
backup_if_exists "$SERVER_FILE"
backup_if_exists "$INDEX_FILE"
backup_if_exists "$FRONTEND_STYLES_FILE"
backup_if_exists "$FRONTEND_DESIGN_SYSTEM_FILE"
backup_if_exists "$FRONTEND_STATE_FILE"
backup_if_exists "$FRONTEND_LOCALIZATION_FILE"
backup_if_exists "$FRONTEND_LOCALES_DIR"
backup_if_exists "$FRONTEND_ICONS_FILE"
backup_if_exists "$FRONTEND_DIALOGS_FILE"
backup_if_exists "$FRONTEND_LAUNCHER_FILE"
backup_if_exists "$FRONTEND_PROFILES_FILE"
backup_if_exists "$FRONTEND_SCHEDULE_FILE"
backup_if_exists "$FRONTEND_ACTIVITY_FILE"
backup_if_exists "$FRONTEND_SETTINGS_FILE"
backup_if_exists "$FRONTEND_FIRST_RUN_FILE"
backup_if_exists "$FRONTEND_RUNTIME_FILE"
backup_if_exists "$MEDIA_FILE"
backup_if_exists "$UPDATE_SCRIPT"
backup_if_exists "$CONFIG_FILE"
backup_if_exists "$AUTOSTART_FILE"
backup_if_exists "$DESKTOP_FILE"
backup_if_exists "$APP_DESKTOP_FILE"

# Render templates from src/
render_template "$SRC_DIR/server.py" "$SERVER_FILE" 0644
install -m 0644 "$SRC_DIR/app_detection.py" "$APP_ROOT/app_detection.py"
install -m 0644 "$SRC_DIR/application_launcher.py" "$APP_ROOT/application_launcher.py"
install -m 0644 "$SRC_DIR/activity_store.py" "$APP_ROOT/activity_store.py"
install -m 0644 "$SRC_DIR/backup_store.py" "$APP_ROOT/backup_store.py"
install -m 0644 "$SRC_DIR/config_store.py" "$APP_ROOT/config_store.py"
install -m 0644 "$SRC_DIR/config_validation.py" "$APP_ROOT/config_validation.py"
install -m 0644 "$SRC_DIR/profile_config.py" "$APP_ROOT/profile_config.py"
install -m 0644 "$SRC_DIR/schedule_rules.py" "$APP_ROOT/schedule_rules.py"
install -m 0644 "$SRC_DIR/lifecycle_state.py" "$APP_ROOT/lifecycle_state.py"
install -m 0644 "$SRC_DIR/media_library.py" "$APP_ROOT/media_library.py"
install -m 0644 "$SRC_DIR/parent_auth.py" "$APP_ROOT/parent_auth.py"
install -m 0644 "$SRC_DIR/runtime_diagnostics.py" "$APP_ROOT/runtime_diagnostics.py"
install -m 0644 "$SRC_DIR/process_state.py" "$APP_ROOT/process_state.py"
install -m 0755 "$SRC_DIR/process_supervisor.py" "$APP_ROOT/process_supervisor.py"
install -m 0644 "$SRC_DIR/timer_state.py" "$APP_ROOT/timer_state.py"
install -m 0644 "$SRC_DIR/update_manager.py" "$APP_ROOT/update_manager.py"
render_template "$SRC_DIR/index.html" "$INDEX_FILE" 0644
render_template "$SRC_DIR/frontend/design-system.css" "$FRONTEND_DESIGN_SYSTEM_FILE" 0644
render_template "$SRC_DIR/frontend/styles.css" "$FRONTEND_STYLES_FILE" 0644
render_template "$SRC_DIR/frontend/state.js" "$FRONTEND_STATE_FILE" 0644
render_template "$SRC_DIR/frontend/localization.js" "$FRONTEND_LOCALIZATION_FILE" 0644
install -d -m 0755 "$FRONTEND_LOCALES_DIR"
install -m 0644 "$SRC_DIR/frontend/locales/de.json" "$FRONTEND_LOCALES_DIR/de.json"
install -m 0644 "$SRC_DIR/frontend/locales/en.json" "$FRONTEND_LOCALES_DIR/en.json"
render_template "$SRC_DIR/frontend/icons.js" "$FRONTEND_ICONS_FILE" 0644
render_template "$SRC_DIR/frontend/dialogs.js" "$FRONTEND_DIALOGS_FILE" 0644
render_template "$SRC_DIR/frontend/launcher-ui.js" "$FRONTEND_LAUNCHER_FILE" 0644
render_template "$SRC_DIR/frontend/profiles.js" "$FRONTEND_PROFILES_FILE" 0644
render_template "$SRC_DIR/frontend/schedule-controls.js" "$FRONTEND_SCHEDULE_FILE" 0644
render_template "$SRC_DIR/frontend/activity-dashboard.js" "$FRONTEND_ACTIVITY_FILE" 0644
render_template "$SRC_DIR/frontend/parent-settings.js" "$FRONTEND_SETTINGS_FILE" 0644
render_template "$SRC_DIR/frontend/first-run.js" "$FRONTEND_FIRST_RUN_FILE" 0644
render_template "$SRC_DIR/frontend/runtime-controls.js" "$FRONTEND_RUNTIME_FILE" 0644
render_template "$SRC_DIR/no-media.html" "$MEDIA_FILE" 0644
render_template "$SRC_DIR/launcher.sh" "$RUNTIME_BIN" 0755
render_template "$SRC_DIR/browser.html" "$APP_ROOT/browser.html" 0644
render_template "$SRC_DIR/overlay.py" "$APP_ROOT/overlay.py" 0755
render_template "$SRC_DIR/timer_watchdog.py" "$APP_ROOT/timer_watchdog.py" 0755

# Install the standalone updater used by the parent UI and the command line.
install -m 0755 "$REPO_DIR/scripts/update.sh" "$UPDATE_SCRIPT"

# Copy theme wallpapers (binary files, no template rendering)
if [[ -d "$SRC_DIR/../themes" ]]; then
  cp -r "$SRC_DIR/../themes" "$APP_ROOT/themes"
fi

# Generate config JSON with proper escaping
python3 - "$CONFIG_FILE" "$ACTIVE_LANG" "$DEFAULT_TITLE" "$DEFAULT_THEME" "$DEFAULT_LAYOUT" "$DEFAULT_PARENT_LABEL" "$DEFAULT_EXIT_LABEL" "$SHUTDOWN_LABEL" "$DEFAULT_TILE_PAINT" "$DEFAULT_TILE_GAMES" "$DEFAULT_TILE_MUSIC" "$DEFAULT_TILE_BROWSER" "$DEFAULT_BROWSER_URL" "$SRC_DIR/recommendations.json" "$RECOMMENDED" <<'PY'
import json, sys, shutil, os
path, lang, title, theme, layout, parent_label, exit_label, shutdown_label, tile_paint, tile_games, tile_music, tile_browser, browser_url, rec_path, recommended = sys.argv[1:16]
config = {
    "configVersion": 2,
    "language": lang,
    "parentLabel": parent_label,
    "exitLabel": exit_label,
    "shutdownLabel": shutdown_label,
    "pinHash": "",
    "autoScanDone": False,
    "setupCompleted": False,
    "activityTrackingEnabled": False,
    "activeProfileId": "default",
    "profiles": [{
        "id": "default",
        "name": "Kiddo",
        "avatar": "🌈",
        "title": title,
        "theme": theme,
        "layoutMode": layout,
        "currentPage": 0,
        "timerMinutes": 0,
        "timerWarningMinutes": 5,
        "favorites": [],
        "appLimits": {},
        "tiles": [
            {"id": "paint", "label": tile_paint, "emoji": "🎨", "cmd": ["tuxpaint"], "visible": True},
            {"id": "games", "label": tile_games, "emoji": "🧩", "cmd": ["gcompris"], "visible": True},
            {"id": "music", "label": tile_music, "emoji": "🎵", "cmd": ["special:filme-musik"], "visible": True},
            {"id": "browser", "label": tile_browser, "emoji": "🌐", "cmd": ["special:external-browser:" + browser_url], "visible": False}
        ]
    }]
}
profile = config["profiles"][0]
existing_ids = {"paint", "games", "music", "browser"}
if recommended == "1" and os.path.isfile(rec_path):
    with open(rec_path, 'r', encoding='utf-8') as f:
        recs = json.load(f)
    for rec in recs:
        if rec["id"] in existing_ids:
            continue
        cmds = rec.get("cmd", [])
        alt_cmds = rec.get("alt_cmds", [])
        found_cmd = None
        for cmd in cmds:
            if shutil.which(cmd):
                found_cmd = cmd
                break
        if not found_cmd:
            for cmd in alt_cmds:
                if shutil.which(cmd):
                    found_cmd = cmd
                    break
        if found_cmd:
            label = rec.get("label_de" if lang == "de" else "label_en", rec["id"])
            if cmds and found_cmd == cmds[0]:
                tile_cmd = cmds
            elif cmds and cmds[0] in ("kstart", "kstart5"):
                # KDE wrapper: use wrapper + args if available, else bare app
                tile_cmd = cmds if shutil.which(cmds[0]) else [found_cmd]
            else:
                # Normal alt_cmd replacement: keep all args
                tile_cmd = [found_cmd] + list(cmds[1:])
            profile["tiles"].append({
                "id": rec["id"],
                "label": label,
                "emoji": rec.get("emoji", "✨"),
                "cmd": tile_cmd,
                "visible": True
            })
            existing_ids.add(rec["id"])
    if existing_ids > {"paint", "games", "music", "browser"}:
        config["autoScanDone"] = True
with open(path, 'w', encoding='utf-8') as f:
    json.dump(config, f, ensure_ascii=False, indent=2)
    f.write('\n')
PY
chmod 0600 "$CONFIG_FILE"

# Copy recommendations data for runtime use
if [[ -f "$SRC_DIR/recommendations.json" ]]; then
  install -m 0644 "$SRC_DIR/recommendations.json" "$APP_ROOT/recommendations.json"
fi

write_file "$AUTOSTART_FILE" 0644 <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$AUTOSTART_NAME
Exec=$RUNTIME_BIN --autostart
Terminal=false
NoDisplay=true
X-KDE-autostart-phase=2
EOF

write_file "$DESKTOP_FILE" 0755 <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$SHORTCUT_NAME
Exec=$RUNTIME_BIN
Icon=preferences-desktop-theme
Terminal=false
Categories=Utility;
EOF

write_file "$APP_DESKTOP_FILE" 0644 <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$APP_NAME
Exec=$RUNTIME_BIN
Icon=preferences-desktop-theme
Terminal=false
Categories=Utility;
EOF

write_file "$UNINSTALL_FILE" 0644 <<EOF
Remove these paths to uninstall:
- $APP_ROOT
- $CFG_DIR
- $RUNTIME_BIN
- $AUTOSTART_FILE
- $DESKTOP_FILE
- $APP_DESKTOP_FILE

Backups from this run are in:
- $BACKUP_DIR
EOF

# Write version marker
if [[ -f "$REPO_DIR/VERSION" ]]; then
  install -m 0644 "$REPO_DIR/VERSION" "$APP_ROOT/version"
fi

chown -R "$TARGET_USER":"$TARGET_USER" "$APP_ROOT" "$CFG_DIR" "$CACHE_DIR" "$BACKUP_ROOT"
chown "$TARGET_USER":"$TARGET_USER" "$RUNTIME_BIN" "$AUTOSTART_FILE" "$DESKTOP_FILE" "$APP_DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
  if [[ "$(id -un)" == "$TARGET_USER" ]]; then
    update-desktop-database "$TARGET_HOME/.local/share/applications" >/dev/null 2>&1 || true
  elif command -v runuser >/dev/null 2>&1 && [[ "$(id -u)" == "0" ]]; then
    runuser -u "$TARGET_USER" -- sh -lc 'update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true'
  fi
fi

echo "$(text install_done)"
echo "$APP_NAME"
echo "  user: $TARGET_USER"
echo "  home: $TARGET_HOME"
echo "  language: $ACTIVE_LANG"
echo "  browser: $BROWSER_CMD"
echo "  shutdown helper enabled: $INSTALL_SHUTDOWN_HELPER"
echo "  backup dir: $BACKUP_DIR"
echo "$(text next_steps)"
