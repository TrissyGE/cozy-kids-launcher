# System packages

The rootless Debian builder installs executable code and static assets below
`/usr/share/cozy-kids-launcher`, a command in `/usr/bin`, and a system desktop
entry. User configuration, cache, backups, activity, firmware and saves keep
their existing locations in the user's home. Package installation, upgrade,
removal and purge do not run code against user homes or start a kiosk as root.
The package has no privileged maintainer scripts.

## Build and inspect

On a Debian-family build host with Python 3.9+, Bash, Git, dpkg-deb and the
script installer's core utilities, run from a checkout:

```sh
python3 scripts/build-deb.py .test-artifacts/packages
dpkg-deb --info .test-artifacts/packages/*.deb
dpkg-deb --contents .test-artifacts/packages/*.deb
```

The default package version includes `VERSION` and the source commit. For a
candidate build use `--version 0.8.0~rc1-1` without changing the release files.
Build the same clean commit twice with identical dpkg/xz versions and compare
the `.deb` and `.sha256` files. The commit timestamp supplies
`SOURCE_DATE_EPOCH`; ownership, modes, ordering and compression are normalized.
The builder reuses the installer renderer and bundles no browser, ROM, BIOS
or downloaded emulator core. Dependencies and optional recommendations appear
in the package metadata. A supported browser must be installed before launch.

Install with the desktop's package installer or `sudo apt install ./FILE.deb`.
The first launch creates a private configuration in the locale selected by
the desktop, with English fallback. An existing configuration is retained
byte for byte and normal startup handles schema validation and recovery.

## Migrate a script installation

1. Install the package and close the old launcher, including its optional
   user service. A running instance prevents migration.
2. As the desktop user run `/usr/bin/cozy-kids-launcher --migrate-script-install`.
3. If the optional service was enabled, run `systemctl --user daemon-reload`.
4. Start Cozy Kids from the applications menu or `/usr/bin/cozy-kids-launcher`.

Migration backs up the user's command, desktop and autostart entries and
standard optional user service before changing any entry. The local command
then delegates to `/usr/bin`. Autostart is preserved only when it existed.
Custom service definitions and linked entry points require manual review.
The old runtime stays in place with an update-owner marker. Its updater and
the script installer refuse to overwrite it. Family configuration, PIN,
profile IDs, commands, media sources, activity, firmware, core imports and
saves are left in place. Backups live in the existing private backup tree.
An interrupted migration can be restored and retried.

Before removing the package, `/usr/bin/cozy-kids-launcher --restore-script-install`
restores the saved entry points and their original modes. It refuses to
overwrite entries edited since migration. Reload the optional user service
after restoration. Restore only when deliberately returning to the script
installation, because it restores the script updater's ownership too.

## Upgrade, rollback and removal

Close the launcher before upgrading or downgrading the package, then start a
new session. Install the previous `.deb` to roll back executable code. A
configuration schema downgrade may require a pre-upgrade configuration
backup, as described in [the compatibility policy](COMPATIBILITY.md).
Use the Parent backup restore for configuration recovery. Game saves and
firmware have their separate backup controls.

`apt remove cozy-kids-launcher` and `apt purge cozy-kids-launcher` remove the
system runtime and command. They preserve family data and migration backups.
Migrated local entry points refer to the removed system command until the
package is reinstalled or the script entries are deliberately restored.
The desktop entries use `TryExec` to avoid offering a missing executable.
Installing again resumes the same family state.

## Acceptance and distribution

Record clean installation, migration, upgrade, rollback, configuration
restore, removal, reinstall and the three desktop sessions for each target
distribution. Ubuntu VM evidence does not certify Mint or Zorin. Signed APT
repository/PPA publication and downstream repository adoption remain separate
roadmap work. No release, tag or repository is published by this builder.

For installed-package desktop checks, use
`scripts/linux/system_package_smoke.py` with the matrix's desktop, session,
browser and mode. `--user-service` additionally tests the actual systemd user
unit in an unused disposable account. It refuses to replace an existing
configuration or user unit. The regular probe uses a temporary home.

The layout and lifecycle follow Debian's [file policy](https://www.debian.org/doc/debian-policy/ch-files.html)
and [package installation procedure](https://www.debian.org/doc/debian-policy/ch-maintainerscripts.html).
