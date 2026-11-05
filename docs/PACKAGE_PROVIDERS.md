# Package-provider foundation

The default catalog flow implements **terminal-free** native installation through
reviewed PackageKit adapters: APT on Ubuntu/Mint/Zorin, DNF5 on Fedora, ZYpp on
openSUSE Tumbleweed and ALPM on Arch Linux. Only explicit catalog mappings are
used. Other derivatives keep graphical software-manager guidance; immutable
hosts never receive native transactions. Full target-distribution desktop
acceptance remains a release gate. Parents review the app's
required packages and download size, explicitly confirm, approve the system
password dialog if requested, and follow progress. On success they can add a
tile to the current child's screen. Nothing is installed merely by opening an
app or its review. The manual-plan API from the first increment remains
compatible, but is no longer the catalog's primary Install action.

## Terminal-free runtime and boundaries

The core launcher remains usable with only its existing dependencies. Direct
installation additionally needs PackageKit with the distribution's matching
backend, Python GObject bindings, the PackageKitGlib 1.0 typelib, a working
system D-Bus, and a graphical Polkit agent
in a complete desktop session. These are system packages, not pip dependencies.
Missing services or unsupported systems get a localized explanation directing
parents to the graphical system software manager. There is no automatic sudo,
root HTTP server, custom privileged helper, or package-source modification.

`packagekit_backend.py` uses the typed PackageKitGlib client over system D-Bus:

1. Resolve an exact catalog-controlled native name for the native architecture.
2. Simulate a trusted installation; reject ambiguous results, more than 200
   packages, or a plan involving removals/upgrades/downgrades. Sum the explicit
   `download-size` fields only when all are available and positive. A zero or
   missing field stays unknown; `Details.size` is never substituted as download
   size. See the [PackageKit details properties](https://packagekit.freedesktop.org/doc/class.Details.html).
3. Keep a ten-minute plan and random single-use confirmation token in memory.
4. After confirmation, simulate again and compare exact IDs, dependencies and
   size, provider and daemon backend. A changed plan requires a fresh review. Run `InstallPackages` with
   `ONLY_TRUSTED` and interactive system authorization, then verify the target
   package's exact version and architecture before reporting success.

For an installed native app, maintenance uses `GetUpdates` and
`UpdatePackages`, or `RemovePackages` with dependent removal and autoremove
disabled. Simulation must report exactly the selected package and intended
operation. A plan changing any other package is referred to the system
software manager. An update must verify the reviewed version and architecture
after completion. Removal must verify that the native package is absent.
See the [PackageKit client contract](https://packagekit.freedesktop.org/doc/class.Client.html).

This maintenance flow remains qualified for APT; Arch offers only its checked
single-target removal. Fedora and Tumbleweed expose installation and direct
maintenance to the system software manager. Their reviewed backends do not
fully enforce the requested removal restrictions; see the [source review and
operation boundaries](NATIVE_PACKAGE_TESTING.md#rpm-maintenance-boundary).

Arch does not offer individual app updates. Before reviewing **and executing**
an installation, the adapter also checks for pending system updates and refuses
the installation if any exist. Parents are directed to a coordinated system
update in their software manager, following the [Arch maintenance policy](https://wiki.archlinux.org/title/System_maintenance#Partial_upgrades_are_unsupported).
Removal remains a separate, single-target action. No AUR helper, repository
refresh command or system upgrade is silently executed by the launcher.

Each adapter verifies the daemon's backend name and advertised operation roles
before resolving or executing a package. A matching command on PATH alone does
not qualify a foreign backend. Fedora's [DNF5 transition](https://fedoraproject.org/wiki/Changes/PackageKit-DNF5)
and the distro's actual daemon are checked separately from package-name mappings.

Resolution and execution are separate PackageKit transactions, not an atomic
reservation of the system package database. Another package manager can change
system state between them. The system backend remains responsible for locking
and consistency; this layer does not offer a universal rollback guarantee.

`package_install.py` owns one background job. Double clicks, concurrent requests,
lost HTTP replies, stale tokens and unreviewed client-supplied package IDs cannot
start a second job. A private atomic journal records the job, native provider
and operation. Once the confirmed
PackageKit call reports its transaction ID, the journal also records that ID
and the reviewed target name, version and architecture. It stores no passwords,
confirmation tokens or executable plans.

After a restart the worker checks the recorded transaction on the system bus.
It matches the native provider, exact daemon ID, user and operation, then observes the existing
job through read-only PackageKit D-Bus properties. If the transaction already ended, the
worker checks recent daemon history for the same ID, user and operation.
Success requires a successful daemon result and a fresh package lookup matching
the reviewed version and architecture, or absence after a removal. An
unavailable daemon, expired history or missing ID leaves the result uncertain.
The launcher never repeats the original install, update or removal call.

While a job is being recovered, the launcher rejects new package plans. Closing
or reopening the status dialog only changes local polling. The restored
progress is available in Parent settings without a fresh confirmation.
See the [PackageKit transaction properties](https://github.com/PackageKit/PackageKit/blob/v1.2.8/src/org.freedesktop.PackageKit.Transaction.xml)
and [transaction history API](https://packagekit.freedesktop.org/doc/class.TransactionPast.html).

The existing local-origin and Parent-session guards protect all new routes:

- `POST /api/packages/prepare` accepts `{appId}` for installation, or
  `{appId, operation}` with `install`, `update` or `remove`.
- `GET /api/packages/status` returns only the current Parent-visible job.
- `POST /api/packages/confirm` accepts only `{jobId, confirmationToken}` and
  runs the operation bound to that review. The compatible
  `/api/packages/install` endpoint accepts the same body for installation jobs.

PackageKit/Polkit owns system authentication. The Parent PIN is not the Linux
password. Cozy Kids does not collect, store or send that password. No Polkit
policy is weakened or installed by this feature.

## Compatible manual-plan API

See [NATIVE_PACKAGE_TESTING.md](NATIVE_PACKAGE_TESTING.md) for adapter requirements,
repeatable container probes and the distinction between package transactions
and target-distribution graphical acceptance.

`src/package_provider.py` parses `/etc/os-release`, falling back to
`/usr/lib/os-release` only when necessary. Values are data, never sourced into a
shell. The native `ID` takes precedence over `ID_LIKE`; the corresponding tool
must exist. Merely installing another distribution's tool does not select it.
Unknown or recognized immutable/OSTree environments return `unsupported`.
This is a conservative heuristic, not a complete immutable-distribution detector.

| Native provider | Manual command shape | Bundled mapping scope |
| --- | --- | --- |
| APT | `sudo apt install --no-remove <package>` | Legacy catalog Debian names preserved; availability still depends on release/repositories |
| DNF | `sudo dnf install <package>` | Five mapped catalog apps plus Tux Paint |
| Pacman | `sudo pacman -S <package>` | Five mapped catalog apps from Extra |
| Zypper | `sudo zypper install <package>` | Five mapped catalog apps checked in openSUSE Factory |
| Flatpak | Not implemented | Remote choice, trust, permissions, and app IDs still require review |

No plan includes automatic yes, repository changes, or a system upgrade.
Parents must keep their distribution maintained; the launcher does not repair
stale package databases or promise that every legacy APT entry is available.

The Parent catalog disables the direct Install action when the current host
has no supported PackageKit route. If there is a mapped native name, it shows
that name alongside the guidance to use the graphical software manager.
Package names are hints from the following repositories. Availability in a
particular release or enabled repository still needs verification.

| App | Fedora | Arch Extra | openSUSE Factory |
| --- | --- | --- | --- |
| GCompris | [gcompris-qt](https://packages.fedoraproject.org/pkgs/gcompris-qt/) | [gcompris-qt](https://archlinux.org/packages/extra/x86_64/gcompris-qt/) | [gcompris-qt](https://api.opensuse.org/public/source/openSUSE:Factory/gcompris-qt) |
| KTurtle | [kturtle](https://packages.fedoraproject.org/pkgs/kturtle/) | [kturtle](https://archlinux.org/packages/extra/x86_64/kturtle/) | [kturtle](https://api.opensuse.org/public/source/openSUSE:Factory/kturtle) |
| KGeography | [kgeography](https://packages.fedoraproject.org/pkgs/kgeography/) | [kgeography](https://archlinux.org/packages/extra/x86_64/kgeography/) | [kgeography](https://api.opensuse.org/public/source/openSUSE:Factory/kgeography) |
| KolourPaint | [kolourpaint](https://packages.fedoraproject.org/pkgs/kolourpaint/) | [kolourpaint](https://archlinux.org/packages/extra/x86_64/kolourpaint/) | [kolourpaint](https://api.opensuse.org/public/source/openSUSE:Factory/kolourpaint) |
| SuperTuxKart | [supertuxkart](https://packages.fedoraproject.org/pkgs/supertuxkart/) | [supertuxkart](https://archlinux.org/packages/extra/x86_64/supertuxkart/) | [supertuxkart](https://api.opensuse.org/public/source/openSUSE:Factory/supertuxkart) |

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
loading, and stale responses through local fixtures. Those initial checks were
not native distribution transactions. The later [native probe increment](NATIVE_PACKAGE_TESTING.md)
records actual daemon tests separately from full graphical acceptance.

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
reported 13,423,526 bytes as download size. That historical field came from
`Details.size` and is not valid download-size evidence; the current adapter
uses `download-size` and keeps unavailable values unknown. The deployed installer engine, PackageKit
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

The user correctly rejected a permanent windowed default. The catalog again
requests `["tuxmath", "--fullscreen"]`. For an X11/XWayland launch without an
explicit different SDL driver, the owned supervisor starts SDL ungrabbed and
requests [_NET_WM_STATE_FULLSCREEN](https://specifications.freedesktop.org/wm/latest/ar01s05.html)
on its own normal window. This is actual undecorated, screen-filling fullscreen,
not a maximized or small desktop window. Xlib is used directly; no new wmctrl,
keyboard-grab or privileged dependency is required. The supervisor reports
`ready: false` while starting so shutdown can still cancel it, and reports ready
only after the window manager confirms fullscreen. Unsupported window managers,
early exit, cancellation or a 20-second confirmation timeout clean up the owned
app instead of silently accepting window mode. Explicit native Wayland driver
choices are preserved; a native Wayland fullscreen comparison also closed
successfully on this VM. This does not certify arbitrary SDL builds/backends.

The integrated KDE/Wayland test launched TuxMath from the fullscreen Chrome kiosk
tile, confirmed a 1600x900 `_NET_WM_STATE_FULLSCREEN` window, entered a number
exercise, accepted Linux XTest keyboard input and scored a correct answer. A real
pointer click on the overlay closed the game and returned to the fullscreen
launcher. Windows-automated keystrokes did not reach the VM; physical host keyboard
acceptance remains open and is not inferred from the Linux XTest result.

Configuration reads previously overwrote *all* argument variants sharing a
catalog executable. They now migrate only bare commands, bare aliases and
explicit complete legacy vectors, preserving custom arguments in every profile.
TuxMath no longer has a fullscreen-to-windowed migration. Its temporary test-VM
setting was restored explicitly; genuine Parent-selected windowed arguments
remain unchanged. Other apps, especially legacy KDE wrappers, still need their
own fullscreen/return audit; see the roadmap's fullscreen product contract.

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
