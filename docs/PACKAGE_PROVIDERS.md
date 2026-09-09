# Package-provider foundation

The default catalog flow implements **terminal-free** installation for the initial
Ubuntu, Linux Mint and Zorin targets with the APT PackageKit backend. Full desktop
acceptance is still a release gate; implementation is not certification of all
three distributions. Parents review the app's
required packages and download size, explicitly confirm, approve the system
password dialog if requested, and follow progress. On success they can add a
tile to the current child's screen. Nothing is installed merely by opening an
app or its review. The manual-plan API from the first increment remains
compatible, but is no longer the catalog's primary Install action.

## Terminal-free runtime and boundaries

The core launcher remains usable with only its existing dependencies. Direct
installation additionally needs the distribution's `packagekit`, `python3-gi`,
`gir1.2-packagekitglib-1.0`, a working system D-Bus, and a graphical Polkit agent
in a complete desktop session. These are system packages, not pip dependencies.
Missing services or unsupported systems get a localized explanation directing
parents to the graphical system software manager. There is no automatic sudo,
root HTTP server, custom privileged helper, or package-source modification.

`packagekit_backend.py` uses the typed PackageKitGlib client over system D-Bus:

1. Resolve an exact catalog-controlled native name for the native architecture.
2. Simulate a trusted installation; reject ambiguous results, more than 200
   packages, or a plan involving removals/upgrades/downgrades. On the APT
   backend, details provide the sum of archive download sizes (not disk usage).
3. Keep a ten-minute plan and random single-use confirmation token in memory.
4. After confirmation, simulate again and compare exact IDs, dependencies and
   size. A changed plan requires a fresh review. Run `InstallPackages` with
   `ONLY_TRUSTED` and interactive system authorization, then verify the target
   package is installed before reporting success.

Resolution and execution are separate PackageKit transactions, not an atomic
reservation of the system package database. Another package manager can change
system state between them. The system backend remains responsible for locking
and consistency; this layer does not offer a universal rollback guarantee.

`package_install.py` owns one background job. Double clicks, concurrent requests,
lost HTTP replies, stale tokens and unreviewed client-supplied package IDs cannot
start a second job. A private atomic journal records only job ID, catalog app ID
and status; it never stores passwords, confirmation tokens or executable plans.
After a launcher restart it reports uncertainty and never replays an action.
Before preparing another plan, the backend checks for existing transactions.
Closing the dialog does not terminate the system package manager. In-place
reconnection after closing/reopening the dialog works; full daemon-transaction
reattachment across process restarts is future work.

The existing local-origin and Parent-session guards protect all new routes:

- `POST /api/packages/prepare` accepts only `{appId}` and returns a background job.
- `GET /api/packages/status` returns only the current Parent-visible job.
- `POST /api/packages/install` accepts only `{jobId, confirmationToken}`.

PackageKit/Polkit owns system authentication. The Parent PIN is not the Linux
password. Cozy Kids does not collect, store or send that password. No Polkit
policy is weakened or installed by this feature.

## Compatible manual-plan API

`src/package_provider.py` parses `/etc/os-release`, falling back to
`/usr/lib/os-release` only when necessary. Values are data, never sourced into a
shell. The native `ID` takes precedence over `ID_LIKE`; the corresponding tool
must exist. Merely installing another distribution's tool does not select it.
Unknown or recognized immutable/OSTree environments return `unsupported`.
This is a conservative heuristic, not a complete immutable-distribution detector.

| Native provider | Manual command shape | Bundled mapping scope |
| --- | --- | --- |
| APT | `sudo apt install --no-remove <package>` | Legacy catalog Debian names preserved; availability still depends on release/repositories |
| DNF | `sudo dnf install <package>` | Tux Paint and KTurtle |
| Pacman | `sudo pacman -S <package>` | KTurtle; not Tux Paint, which is in the AUR |
| Zypper | `sudo zypper install <package>` | Detection/plan builder tested; no bundled mappings enabled yet |
| Flatpak | Not implemented | Remote choice, trust, permissions, and app IDs still require review |

No plan includes automatic yes, repository changes, or a system upgrade.
Parents must keep their distribution maintained; the launcher does not repair
stale package databases or promise that every legacy APT entry is available.

## API and safety contract

The existing request field `package` remains a catalog lookup key. Explicit
native names belong in the recommendation's `packages` object. Only legacy APT
entries may fall back to `package`; other providers require an explicit mapping.
Names reject leading options, trailing APT action suffixes, whitespace, shell
metacharacters, URLs, and paths. Plans use argument vectors and `shlex.join` for
the human-readable command; no shell or subprocess is executed by the module.

- Unauthenticated requests follow the existing Parent PIN/session gate.
- Invalid input returns HTTP 400, including JSON arrays/objects used as a package.
- HTTP 200 `status: manual` includes `provider`, `argv`, and `command`.
- HTTP 200 `status: unsupported` contains no command and explains an unavailable
  provider or missing mapping through a machine-readable `reason`.
- The dialog distinguishes loading/manual/unsupported/error, offers retry on
  error, never guesses a command, and ignores responses after close/replacement.

## Evidence and remaining release checks

Unit tests cover native selection, immutable-host exclusions, data-only parsing,
all four plan builders, missing mappings, and hostile input. HTTP tests exercise
the Parent boundary. Browser tests exercise acknowledgement, errors, retry,
loading, and stale responses through local fixtures. These are **not** real
Fedora/Arch/openSUSE installation tests or a full distribution support promise.

Additional unit/API tests cover preparation without execution, native simulation
flags, dependency changes, one-use/expired consent, concurrent jobs, restart
behavior, installed-state verification and authentication. Browser fixtures
exercise the real UI, progress, lost replies, adding a tile, safe DOM rendering,
error/recovery states and German/English review at 800x600. They never install
packages on CI runners.

On Ubuntu 24.04.4 WSL, PackageKit 1.2.8's real APT backend successfully resolved
and simulated Tux Paint and KTurtle. A real Tux Paint installation request was
denied without a usable system authorization agent; the UI-facing result was
`authorization`, not success. No Tux Paint package was installed by that test.

On September 9, 2026, the user successfully installed **TuxMath** through the
catalog in the Ubuntu 24.04.4 KDE/Wayland VM as its non-admin desktop user.
The launcher returned `complete` with 100%; the APT history independently records
PackageKit installing TuxMath `2.0.3-9build2` and nine dependencies. The plan
reported 13,423,526 download bytes. The deployed installer engine, PackageKit
bridge and catalog UI file hashes match code commit `94811db`. This verifies
a real desktop installation, not just a simulated transaction.

For that code commit, all 299 local unit/integration tests, static checks, the
complete local browser suite and [all CI jobs](https://github.com/TrissyGE/cozy-kids-launcher/actions/runs/34327132552)
passed. The German/English review screenshots were visually checked. The browser
fixture restores its saved config after exercising tile persistence so later
media checks remain independent of earlier unsaved UI changes.

The user also added the real TuxMath tile and launched it, but reported that it
could not be closed. The red overlay was visible; real pointer clicks did not
terminate the fullscreen game. The installed SDL 1.2 compatibility implementation
[grabs input in fullscreen](https://github.com/libsdl-org/sdl12-compat/blob/release-1.2.68/src/SDL12_compat.c#L6914).
With `--windowed`, the same overlay click terminated TuxMath and the launcher
became visible again. The comparison used the full launcher entry point (with
owned browser records), not the initial installation-only server/browser pair.

TuxMath's catalog command now uses `--windowed`; `legacy_cmds` records its exact
old `["tuxmath", "--fullscreen"]` default for migration. Configuration reads
previously overwrote *all* argument variants sharing a catalog executable, even
undoing a manually selected windowed mode. They now migrate only bare commands,
bare aliases and explicitly listed complete legacy vectors, preserving custom
arguments in every child profile. This is not a global fullscreen restriction;
other apps and customized launch commands still need their own desktop tests.

Full-desktop failure scenarios and Mint/Zorin acceptance are still open. Do not
treat this successful Ubuntu installation and corrected return path as
certification of the complete release matrix.

Read-only developer smoke check:

```bash
python3 scripts/linux/packagekit_smoke.py --app tuxpaint
```

Only in a disposable complete desktop, opt into a **real system installation**:

```bash
python3 scripts/linux/packagekit_smoke.py --app tuxpaint --install
```

Run as the normal desktop user, not root. Confirm the system dialog yourself.
The temporary launcher journal does not sandbox packages: `--install` changes
that Linux system and leaves the selected app installed. For full acceptance,
also follow the catalog UI's review → install → add tile → launch flow, deny
authentication once, test offline/busy states, and record the exact revision.

Primary references checked on September 9, 2026:

- [PackageKit transaction API](https://github.com/PackageKit/PackageKit/blob/main/src/org.freedesktop.PackageKit.Transaction.xml) and [PackageKit architecture](https://github.com/PackageKit/PackageKit)
- [APT install and no-remove semantics](https://manpages.debian.org/testing/apt/apt-get.8.en.html)
- [DNF command reference](https://dnf.readthedocs.io/en/latest/command_ref.html)
- [Pacman manual](https://man.archlinux.org/man/pacman.8.en)
- [openSUSE Zypper usage](https://en.opensuse.org/SDB%3AZypper_usage)
- Fedora [Tux Paint](https://packages.fedoraproject.org/pkgs/tuxpaint/tuxpaint/) and [KTurtle](https://packages.fedoraproject.org/pkgs/kturtle/kturtle/)
- [Arch KTurtle binary package](https://archlinux.org/packages/extra/x86_64/kturtle/) and [Tux Paint AUR recipe](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=tuxpaint)
