# Installed-app discovery

The Parent tile editor discovers installed graphical applications from desktop
entries. Its `/api/apps` response remains a list of `{name, exec}` objects.
Names follow the saved German/English interface language; setup completion and
language-changing configuration reloads refresh the selector.

This is the installed-app selector behind custom tiles. The curated app-store
recommendations and package-provider mappings are maintained separately.

## Search roots and precedence

Discovery searches the following roots in order:

1. `$XDG_DATA_HOME/applications`, defaulting to `~/.local/share/applications`;
2. the `applications` directory in each absolute `$XDG_DATA_DIRS` component,
   defaulting to `/usr/local/share:/usr/share`;
3. missing standard user/system Flatpak export and Snap application roots.

Relative XDG paths are ignored and repeated roots are deduplicated. Registered
XDG export directories retain their configured precedence. Subdirectories are
walked in stable order without following directory symlinks; symlinks to regular
desktop files remain usable for exported applications.

The first desktop-file ID wins. A user override with `Hidden=true` or
`NoDisplay=true` masks a lower-priority system entry even when it supplies no
launch command. Nested paths use the standard ID mapping, such as
`vendor/app.desktop` → `vendor-app.desktop`. Identical resulting commands are
deduplicated after desktop-ID precedence has been applied.

These rules follow the [XDG base-directory specification](https://specifications.freedesktop.org/basedir/latest/)
and [desktop-file ID rules](https://specifications.freedesktop.org/desktop-entry/latest/file-naming.html#desktop-file-id).

## Representable entries

Only the `[Desktop Entry]` group supplies application fields; additional desktop
actions cannot replace the main name/command or hide it. Entries require
`Type=Application`, a default `Name`, an available executable and an `Exec`
fallback. Optional `TryExec` must resolve to an executable; empty or unavailable
values are skipped. Visibility follows `Hidden`, `NoDisplay`, and the first
matching desktop in `OnlyShowIn`/`NotShowIn`.
Executable checks cover the initial program and declared TryExec; wrapper-internal
dependencies still require per-app validation.

The existing tile model represents argv-based graphical launches. Entries
requiring a terminal or a working directory, and D-Bus-only entries without an
Exec fallback, are omitted. Discovery uses the fallback command rather than
delegating launch ownership to desktop D-Bus activation. These are deliberate
limits of the current adapter, not full desktop-menu implementation coverage.

Localized names use locale/territory/modifier fallbacks before the default
`Name`. See the [desktop entry keys](https://specifications.freedesktop.org/desktop-entry/latest/recognized-keys.html).

## Command handling

Desktop string escapes and Exec double quoting are decoded before field codes
are expanded. Literal `%%`, localized `%c`, icon `%i` and desktop-file `%k` values
retain their argument boundaries and are expanded once. File/URL placeholders
have no operands in the tile editor and are removed; deprecated codes are
ignored. Unknown codes, undefined quoted field codes, malformed quoting and
unquoted reserved characters are skipped instead of guessed.

The output is serialized with `shlex.join` for the existing single-string tile
editor. The launch adapter parses that representation back to argv and starts
the owned process directly. Discovery itself only reads metadata and checks
executable availability. See the [Exec specification](https://specifications.freedesktop.org/desktop-entry/latest/exec-variables.html).

Each file is limited to 1 MiB, each scan to 10,000 desktop files and 300 returned
apps by default. Returned commands fit the tile model's 2,048-character element
limit. Invalid UTF-8, duplicate main-group keys, non-regular files and missing
files are skipped.

## Evidence and remaining work

Tests cover action-group isolation, empty TryExec, executable permissions,
hidden overrides, nested IDs, XDG order, Flatpak export command boundaries,
locale fallbacks, percent/string quoting, malformed inputs and scan limits.
HTTP tests round-trip a discovered command through a saved tile and back to its
exact launch argv. The browser suite seeds a real desktop file in its isolated
home and checks German/English names after configuration reloads.

Read-only WSL comparison against GLib agreed on the executable of all four
eligible desktop entries in that small test environment. This is a compatibility
sample, not a broad performance or distribution benchmark.

Flatpak export discovery covers already installed apps. Managed Flatpak package
actions remain a later provider milestone. New curated recipes and graphical
fullscreen/input/return acceptance still follow [CATALOG_FULLSCREEN.md](CATALOG_FULLSCREEN.md).
