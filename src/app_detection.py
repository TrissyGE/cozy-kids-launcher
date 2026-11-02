"""Desktop application and browser discovery for Cozy Kids Launcher."""

import os
import re
import shlex
import shutil
import stat


BROWSER_CANDIDATES = (
    "firefox",
    "firefox-esr",
    "librewolf",
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "brave",
    "brave-browser",
    "opera",
    "opera-stable",
    "vivaldi",
    "vivaldi-stable",
    "microsoft-edge",
    "microsoft-edge-stable",
    "edge",
    "cachy-browser",
)

CHROMIUM_BROWSER_NAMES = {
    "chromium",
    "chromium-browser",
    "google-chrome",
    "google-chrome-stable",
    "brave",
    "brave-browser",
    "opera",
    "opera-stable",
    "vivaldi",
    "vivaldi-stable",
    "microsoft-edge",
    "microsoft-edge-stable",
    "edge",
    "cachy-browser",
}


MAX_DESKTOP_BYTES = 1024 * 1024
MAX_DESKTOP_FILES = 10000
MAX_EXEC_CHARS = 2048  # The existing tile editor stores this as one cmd element.
MAX_NAME_CHARS = 1024


def _desktop_string(value):
    escapes = {"s": " ", "n": "\n", "t": "\t", "r": "\r", "\\": "\\"}
    return re.sub(r"\\([sntr\\])", lambda match: escapes[match[1]], value)


def _desktop_values(path):
    try:
        info = os.stat(path)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_DESKTOP_BYTES:
            return None
        with open(path, "rb") as handle:
            payload = handle.read(MAX_DESKTOP_BYTES + 1)
        if len(payload) > MAX_DESKTOP_BYTES or b"\0" in payload:
            return None
        contents = payload.decode("utf-8")
    except (OSError, UnicodeError):
        return None
    values, active, found = {}, False, False
    for line in contents.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            active = line == "[Desktop Entry]"
            if active and found:
                return None
            found = found or active
        elif active:
            key, separator, value = line.partition("=")
            key = key.strip()
            if not separator or key in values:
                return None
            values[key] = value.strip()
    return values if found else None


def _localized_name(values, language, environment):
    locale = language or next(
        (environment.get(key) for key in ("LC_ALL", "LC_MESSAGES", "LANG") if environment.get(key)),
        "C",
    )
    locale, _, modifier = locale.partition("@")
    locale = locale.split(".", 1)[0]
    base = locale.split("_", 1)[0]
    candidates = ([locale + "@" + modifier, locale, base + "@" + modifier, base]
                  if modifier else [locale, base])
    for candidate in [*("Name[" + name + "]" for name in candidates), "Name"]:
        name = _desktop_string(values.get(candidate, ""))
        if name.strip():
            return name if len(name) <= MAX_NAME_CHARS else None
    return None


def _exec_tokens(value):
    """Desktop Exec double quoting, separate from the final shell-free argv."""
    tokens, current = [], []
    quoted = started = closed = was_quoted = False
    index = 0
    while index < len(value):
        char = value[index]
        if quoted:
            if char == '"':
                quoted, closed = False, True
            elif char == "\\":
                index += 1
                if index == len(value) or value[index] not in ('"', "\\", "$", "`"):
                    return None
                current.append(value[index])
            elif char in ("$", "`"):
                return None
            else:
                current.append(char)
        elif char in " \t\r\n":
            if started:
                tokens.append(("".join(current), was_quoted))
                current, started, closed, was_quoted = [], False, False, False
        elif char == '"' and not started:
            quoted = started = was_quoted = True
        elif closed or char in "\"'\\><~|&;$*?#()`":
            return None
        else:
            started = True
            current.append(char)
        index += 1
    if quoted:
        return None
    if started:
        tokens.append(("".join(current), was_quoted))
    return tokens


def _desktop_argv(value, name, icon, path):
    if not value or len(value) > MAX_EXEC_CHARS:
        return None
    tokens = _exec_tokens(_desktop_string(value))
    if not tokens:
        return None
    argv, file_codes = [], 0
    for position, (token, quoted) in enumerate(tokens):
        if token == "%i" and not quoted and position:
            if icon:
                argv.extend(["--icon", icon])
            continue
        expanded, index = [], 0
        while index < len(token):
            char = token[index]
            if char != "%":
                expanded.append(char)
                index += 1
                continue
            if index + 1 == len(token):
                return None
            code = token[index + 1]
            index += 2
            if code == "%":
                expanded.append("%")
            elif quoted or not position:
                return None
            elif code in "fFuU":
                file_codes += 1
                if file_codes > 1 or (code in "FU" and token != "%" + code):
                    return None
            elif code in "dDnNvm":
                pass  # Deprecated codes are removed, never interpreted.
            elif code in ("c", "k"):
                expanded.append(name if code == "c" else os.fspath(path))
            else:
                return None
        result = "".join(expanded)
        if result or token == "":
            argv.append(result)
    if not argv or not argv[0] or "=" in argv[0]:
        return None
    return argv


def parse_desktop_file(path, environ=None, *, language=None, which=None):
    """Read a visible graphical entry representable by an existing argv tile."""
    values = _desktop_values(path)
    if not values or values.get("Type") != "Application" or not values.get("Name"):
        return None
    for flag in ("Hidden", "NoDisplay", "Terminal"):
        if values.get(flag, "false") != "false":
            return None
    if values.get("Path"):
        return None  # The tile model has no working-directory/terminal contract.
    environment = os.environ if environ is None else environ
    only = _desktop_string(values.get("OnlyShowIn", "")).split(";")
    excluded = _desktop_string(values.get("NotShowIn", "")).split(";")
    show = "OnlyShowIn" not in values
    for desktop in filter(None, environment.get("XDG_CURRENT_DESKTOP", "").split(":")):
        if desktop in only or desktop in excluded:
            show = desktop in only
            break
    if not show:
        return None
    executable = which if which is not None else (
        lambda command: shutil.which(command, path=environment.get("PATH", os.defpath))
    )
    if "TryExec" in values:
        candidate = _desktop_string(values["TryExec"])
        if not candidate or not executable(candidate):
            return None
    name = _localized_name(values, language, environment)
    if not name:
        return None
    argv = _desktop_argv(
        values.get("Exec", ""), name, _desktop_string(values.get("Icon", "")), path,
    )
    if not argv or not executable(argv[0]):
        return None
    command = shlex.join(argv)
    return {"name": name, "exec": command} if len(command) <= MAX_EXEC_CHARS else None


def _application_directories(home, environment):
    data_home = environment.get("XDG_DATA_HOME", "")
    if not os.path.isabs(data_home):
        data_home = os.path.join(home, ".local", "share")
    data_dirs = environment.get("XDG_DATA_DIRS") or "/usr/local/share:/usr/share"
    roots = [os.path.join(data_home, "applications")]
    roots.extend(os.path.join(path, "applications")
                 for path in data_dirs.split(os.pathsep) if os.path.isabs(path))
    roots.extend((os.path.join(data_home, "flatpak", "exports", "share", "applications"),
                  "/var/lib/flatpak/exports/share/applications", "/var/lib/snapd/desktop/applications"))
    return list(dict.fromkeys(os.path.normpath(path) for path in roots))


def scan_apps(home, application_dirs=None, limit=300, *, environ=None, language=None, which=None):
    """Discover XDG desktop IDs in precedence order; hidden overrides mask lower entries."""
    if limit <= 0:
        return []
    environment = os.environ if environ is None else environ
    directories = (_application_directories(home, environment)
                   if application_dirs is None else application_dirs)
    apps, seen_ids, seen_commands = [], set(), set()
    examined = 0
    for directory in directories:
        for root, folders, files in os.walk(directory, followlinks=False):
            folders.sort()
            for filename in sorted(files):
                if not filename.endswith(".desktop"):
                    continue
                examined += 1
                if examined > MAX_DESKTOP_FILES:
                    return apps
                path = os.path.join(root, filename)
                desktop_id = os.path.relpath(path, directory).replace(os.sep, "-")
                if desktop_id in seen_ids:
                    continue
                seen_ids.add(desktop_id)
                app = parse_desktop_file(path, environment, language=language, which=which)
                if app and app["exec"] not in seen_commands:
                    seen_commands.add(app["exec"])
                    apps.append(app)
                    if len(apps) >= limit:
                        return apps
    return apps


def browser_family(browser):
    """Return the launch-profile family used by a browser executable."""
    if os.path.basename(browser) in CHROMIUM_BROWSER_NAMES:
        return "chromium"
    return "firefox"


def find_browser(config=None, candidates=BROWSER_CANDIDATES, which=None):
    """Find the configured browser first, then the supported fallbacks."""
    config = config or {}
    preferred = config.get("browser", "")
    ordered_candidates = ([preferred] if preferred else []) + list(candidates)
    executable = shutil.which if which is None else which
    seen = set()
    for candidate in ordered_candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if executable(candidate):
            return candidate
    return None


def browser_statuses(candidates=BROWSER_CANDIDATES, which=None):
    """Return the stable public browser-detection payload."""
    executable = shutil.which if which is None else which
    return [
        {"name": browser, "installed": bool(executable(browser))}
        for browser in candidates
    ]
