# Privacy and Safety Notes

This project is intended for private family computers.

## Local-first

The launcher is designed to run locally:

- local config file
- local HTTP server on localhost
- local browser in kiosk mode
- local application launching

No cloud backend is required.

The launcher keeps small, rotating technical event logs locally. Parents can
download a diagnostics JSON file from Parent settings when troubleshooting.
Both the logs and the export use a fixed allowlist and exclude PIN data,
personal labels, tile commands, URLs, usernames, and local paths. Nothing is
uploaded automatically.

Child profiles, including names, avatars, themes, tiles, favorites, and limits,
are stored together in the same private local configuration. Creating,
selecting, and deleting profiles uses the existing Parent-authentication
boundary. Configuration exports and backups contain every profile so they can
be restored together; deleting a profile removes it from the active
configuration and later backup rotation determines how long older copies remain.

Installer and pre-restore backups remain under the user's local data directory.
They can contain the same family settings and hashed Parent PIN as the active
configuration, so their directories are restricted to the local user. Parent
settings expose only a backup's date and origin, not paths or configuration
values. A restore preserves the currently active Parent PIN.

The launcher also keeps one private lifecycle status file in its cache. It
contains only a fixed state and reason plus, during recovery, a bounded attempt
number. It never contains process IDs, names, commands, paths, or family
settings. Parent diagnostics apply the same fixed allowlist.

## What parents should review before using

- which applications are visible to the child
- whether a web browser is enabled
- whether shutdown should be available
- whether parent settings should be protected with a PIN

When configured, the PIN is stored as a salted password hash. The public launcher API exposes only that a PIN exists. A successful PIN entry creates a temporary parent session for sensitive actions.

## Publishing guidance

Before sharing screenshots or configs publicly:

- remove personal names if desired
- hide private filenames
- avoid showing private wallpaper assets if they are licensed or personal
- avoid screenshots with notifications, chats, browser history, or Wi-Fi names

## Security scope

This project is a launcher UI, not a hardened sandbox.

It improves usability for children, but it is not a full kiosk security solution by itself.
The parent PIN protects launcher controls; it does not replace Linux user separation, disk encryption, operating-system updates, or a restricted child account.
