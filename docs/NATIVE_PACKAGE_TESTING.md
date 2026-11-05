# Native catalog adapter checks

The Parent app store selects a package through its catalog app ID and explicit
mapping for the detected provider. A client cannot select a provider, repository,
package ID or command. The daemon must match the distribution and advertise the
required PackageKit roles. A confirmed plan includes the provider and backend;
a changed provider or plan cannot reuse consent. Recovery additionally checks
the recorded provider before observing daemon history. Legacy journals without
a provider retain their original APT meaning.

| Distribution | Expected daemon | Python/introspection packages | Operations |
| --- | --- | --- | --- |
| Ubuntu/Mint/Zorin | `apt` | `python3-gi`, `gir1.2-packagekitglib-1.0` | Install, single-target update and removal |
| Fedora | `dnf5` or legacy `dnf` | `python3-gobject-base`, `PackageKit-glib` | Install; maintenance through the system manager |
| openSUSE Tumbleweed | `zypp` | `python3-gobject`, `typelib-1_0-PackageKitGlib-1_0` | Install; maintenance through the system manager |
| Arch Linux | `alpm` | `python-gobject`, `libpackagekit-glib` | Install on a current system; single-target removal |

PackageKit, its matching backend, system D-Bus and a desktop authorization agent
are required too. This is not a claim that an untested derivative is qualified.
RHEL, Manjaro, Leap and unknown derivatives retain software-manager guidance.
Immutable variants do not receive native transactions. Managed Flatpak remains
a separate roadmap task. No AUR helper or extra package repository is added.

## RPM maintenance boundary

The reviewed PackageKit 1.4.0 [DNF5 implementation](https://github.com/PackageKit/PackageKit/blob/v1.4.0/backends/dnf5/dnf5-backend-thread.cpp)
reads `allow_deps` without applying it and only enables, rather than explicitly
disables, configured cleanup when handling `autoremove`. The
[ZYpp implementation](https://github.com/PackageKit/PackageKit/blob/v1.4.0/backends/zypp/pk-backend-zypp.cpp)
also reads `allow_deps` without using it for its forced removal solve. A clean
simulation cannot make those execution-time restrictions reliable if system
state changes later. RPM updates/removal therefore remain in the system
software manager until their maintenance path is qualified. Both the UI and
server reject those actions; a client cannot bypass the policy.

Initial Fedora Tux Paint and KGeography probes installed and reconciled
successfully, but their removal proposals included extra packages and were
refused. Those findings prompted this boundary, rather than a passing removal
certification. Arch's [ALPM backend](https://github.com/PackageKit/PackageKit/blob/v1.4.0/backends/alpm/pk-alpm-remove.c)
explicitly maps the two removal switches to corresponding libalpm flags.

## Arch consistency

The adapter refuses per-app updates and checks `GetUpdates` before installation
review and again before execution. Pending system updates, including blocked
updates, require the parent's coordinated system update first. An installation
simulation that proposes any upgrades, removals or downgrades is refused on all
providers. This preserves the [Arch system maintenance contract](https://wiki.archlinux.org/title/System_maintenance#Partial_upgrades_are_unsupported).

## Native probes

Run the local adapter read-only in a desktop session:

```sh
python3 scripts/linux/native_package_probe.py --app kturtle \
  --artifacts .test-artifacts/native-preview
```

The explicit `--execute` option installs an initially absent app, verifies the
exact reviewed version and architecture, reconciles a saved in-progress journal
through actual daemon history and checks maintenance policy. Arch removes only
the selected package. RPM probes verify delegation and retain the installed app.
A refused compound removal is reported explicitly. Use a disposable
system; package operations affect that system even though the launcher journal
is temporary. Root execution is accepted only inside a container.

For an isolated test with no host home or D-Bus mounts:

```sh
python3 scripts/linux/native_package_containers.py --engine docker \
  --family arch --execute --artifacts .test-artifacts/native/arch
```

`podman` is supported too; its `--init` helper must be installed. Choose
`fedora`, `arch` or `opensuse`. The runner uses upstream images and creates only
its own randomly named, labelled container. It installs binding packages and
base GTK/Qt libraries, starts private real D-Bus/Polkit/PackageKit daemons and
runs the real adapter. The base libraries represent an existing desktop and
keep an empty server image from exceeding the existing 200-package review limit.
That limit is also checked: the initial minimal Fedora/Arch images refused
Tux Paint/KolourPaint proposals of 283/246 packages before base toolkit setup.

The optional execution mode first runs an ordinary user with no authorization
agent and requires a real `authorization` refusal, then tests a root transaction
inside the disposable container. No Polkit rule is weakened,
password supplied or authorization result mocked. Container-root transactions
test package semantics; they do not certify a graphical password dialog.

The runner copies out reports and daemon logs and removes its own container in
a `finally` block. It never prunes an engine or removes unrelated containers.
Reports record image digests, actual PackageKit version, runtime file hashes,
reviewed package target, checks and remaining graphical acceptance. The focused
`Native package adapters` workflow repeats all three families when their
implementation, catalog mappings or test harness changes.

## Evidence and remaining acceptance — 2026-11-05

All three native probes used PackageKit 1.4.0 and passed the final operation
policy, trusted installation, exact target verification, single-use consent,
daemon-history reconciliation and ordinary-user authorization refusal:

| Native environment | App and target version | Final maintenance result |
| --- | --- | --- |
| Fedora 44 / DNF5 | KGeography `26.08.2-1.fc44`, x86_64 | Updates and removal delegated before a daemon maintenance call |
| Arch Linux / ALPM | KolourPaint `26.08.2-1`, x86_64 | Partial update refused; single-target removal passed |
| Tumbleweed / ZYpp | KGeography `26.08.2-1.1`, x86_64 | Updates and removal delegated before a daemon maintenance call |

Reports identify runtime file hashes and the observed package manager version.
The CI container report additionally records upstream image digests. Real
version-to-version RPM maintenance and graphical target acceptance remain open.

The Parent browser fixture covers native source labels, policy-specific actions,
the Arch explanation and all five languages at 800×600. Fixture mutations never
install packages on the browser runner. The installed Debian runtime was checked
on the Ubuntu desktop matrix; see [DESKTOP_TESTING.md](DESKTOP_TESTING.md). These
Ubuntu sessions and headless native containers do not certify Fedora/Arch/SUSE
fullscreen, physical input or graphical authorization. Record those target
distribution sessions before release qualification.
