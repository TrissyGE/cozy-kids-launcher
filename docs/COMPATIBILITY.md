# Compatibility policy

The release contract covers the launcher and existing family data on the
distributions and desktop sessions qualified for that release. The
[desktop matrix](DESKTOP_TESTING.md) records the exact candidate, session and
browser combinations. A catalog package mapping describes a package name.
Distribution acceptance requires a separate install and launch test.

## Configuration and local data

- `configVersion` identifies the stored schema. The current schema is 2.
  Supported older configurations are migrated in order and validated before
  use. A newer unknown schema is rejected.
- A migration must retain user choices, profile isolation, and tile command
  semantics. Test it against the previous stored format and any older format
  it still accepts. Add a schema version for an incompatible stored shape.
- The Parent export is a configuration backup. Game saves, firmware,
  media state and emulator data have separate storage and backup rules.
- Downgrading may require restoring a configuration export made before the
  schema upgrade. Test an installer failure and rollback separately from
  deliberately running an older executable.

## Loopback API

The HTTP API is a private interface between the installed browser UI and its
matching local server. It accepts the local listener's host and port.
Remote access, reverse proxies and third-party API compatibility are outside
the release contract. During a UI or server change, test the installed
client and server together. For changed write routes, also exercise Parent
authentication, origin checks, and malformed input.

## Packages and migration

A distribution package must identify its update owner and include
tested transitions from the script installation. A migration must preserve
private state, keep a single active launcher, migrate desktop entries and
autostart, and expose a clear uninstall path. Exercise clean install,
upgrade, rollback, backup restore and removal on each claimed distribution
before marking that package supported.

For the current per-user runtime layout, a packager can place a
`package-managed` marker next to the installed `version` file before the
first start. In that mode the launcher shows the installed version and
delegates updates to the system package manager. The release updater,
update-channel changes and stale launcher update triggers are disabled.
The script installer also refuses to overwrite a marked installation.
The [Debian package builder](PACKAGING.md) uses the same contract in a
system-wide, read-only runtime. Its explicit per-user migration backs up and
redirects the old entry points while retaining family data. It supports
restoring the script entry points before returning to script-managed updates.
Ubuntu VM lifecycle evidence and remaining distribution gates are recorded
in the [desktop test guide](DESKTOP_TESTING.md).

## Stable and Preview updates

Stable installations select a complete stable release. Preview is an
explicit opt-in to eligible versioned candidates. Returning to Stable
keeps the no-downgrade rule. Legacy installations use stable `main`, which
the release workflow advances only to a published stable tag. After a
verified release update the updater fails closed if release discovery is
unavailable. See the [release verification procedure](RELEASING.md).
