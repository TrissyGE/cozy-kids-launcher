# Package-provider foundation

This first v0.8 platform increment prepares **manual instructions only**. Opening
the Parent install dialog does not install anything, request privilege, download
scripts, or modify repositories. Parents review and run the displayed command
in their terminal, review their package manager's proposed changes, then refresh
the app list. Automatic actions and progress/recovery need a separate design.

## Detection and supported plans

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

## Evidence and next steps

Unit tests cover native selection, immutable-host exclusions, data-only parsing,
all four plan builders, missing mappings, and hostile input. HTTP tests exercise
the Parent boundary. Browser tests exercise acknowledgement, errors, retry,
loading, and stale responses through local fixtures. These are **not** real
Fedora/Arch/openSUSE installation tests or a full distribution support promise.

Before enabling a new mapping, record its official package source and verify
installation/discovery in a disposable supported distribution. Before adding
automatic transactions, define privilege separation, confirmation, progress,
restart recovery, update/removal, and rollback boundaries.

Primary references checked on September 9, 2026:

- [APT install and no-remove semantics](https://manpages.debian.org/testing/apt/apt-get.8.en.html)
- [DNF command reference](https://dnf.readthedocs.io/en/latest/command_ref.html)
- [Pacman manual](https://man.archlinux.org/man/pacman.8.en)
- [openSUSE Zypper usage](https://en.opensuse.org/SDB%3AZypper_usage)
- Fedora [Tux Paint](https://packages.fedoraproject.org/pkgs/tuxpaint/tuxpaint/) and [KTurtle](https://packages.fedoraproject.org/pkgs/kturtle/kturtle/)
- [Arch KTurtle binary package](https://archlinux.org/packages/extra/x86_64/kturtle/) and [Tux Paint AUR recipe](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=tuxpaint)
