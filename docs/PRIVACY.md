# Privacy and Safety Notes

This project is intended for private family computers.

## Local-first

The launcher is designed to run locally:

- local config file
- local HTTP server on localhost
- local browser in kiosk mode
- local application launching

No cloud backend is required.

The local media catalog stays on the loopback server. Its public response uses
opaque identifiers and never returns absolute media or cover paths. Discovery
is bounded, ignores hidden content, and rejects symbolic links that resolve
outside the standard local Videos and Music folders. Cover bytes are served
only after resolving an identifier through that same local catalog. Starting
one item sends its opaque ID and the visible media-tile ID back to localhost;
the browser never receives the file path. The server resolves it again and
applies the tile's current availability rule before launching a player.
Per-profile media favorites and the 50 most recently launched items are kept in
a separate private local state file containing only profile IDs and opaque
media IDs—never titles or paths. The catalog API omits stale IDs, and deleting a
child profile also removes its retained media-library state.

Embedded website tiles are restricted to their configured start origin plus up
to 20 exact additional origins chosen in Parent settings. The local server binds
the wrapper URL back to that tile, emits the matching browser policy, and the
iframe cannot navigate the launcher window itself. If a link leaves the allowed
origins, the child sees a local explanation. External browser mode is deliberately
outside this boundary and is described that way before a parent selects it.

The first-run setup and both bundled interface languages are served entirely
from the local launcher. Completing or skipping setup only updates the same
private local configuration used by Parent settings.

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
Optional weekly and per-app availability windows are stored in that same local
profile and are evaluated only against the device's local time. Availability
polling stays on the launcher's loopback API; no schedule or usage information
is uploaded.

Optional world-theme day periods use only the current hour reported by the
device. The launcher does not request location data, contact an external time
service, or store a history of theme periods.

Returning from the local media library or embedded browser uses one session-only
marker containing the active profile and tile identifiers. It contains no child
name, label, command, URL, or filesystem path and is removed when the launcher
consumes it. Native application return feedback is tracked only in page memory.

Optional activity tracking is disabled by default. When a parent enables it,
the launcher stores only profile and tile identifiers, a start time, and the
completed duration in `~/.local/state/cozy-kids-launcher/activity.json`. It does
not copy child names, app labels, commands, URLs, or media paths into activity
records. Records older than 90 days are ignored and at most 1,000 are retained.
The existing Parent-access boundary protects reading and clearing the records,
and requires a valid Parent session whenever a PIN is configured. Deleting a
child profile also removes its retained activity. The activity file and its
directory are restricted to the local user and are never uploaded. The Parent
dashboard resolves readable names only from the current local configuration;
the downloadable activity export contains the stored identifiers and times,
but no profile names, app labels, commands, URLs, or media paths.
The child-facing picker receives only names and avatars. Switching to another
child still requires the Parent PIN when one is configured. The small
"last launched" marker is stored locally under a separate key for each profile.

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
- whether weekly or per-app availability windows are appropriate
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
