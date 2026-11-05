# Managed Flatpak qualification

This increment adds a user-scoped libflatpak adapter and an initial reviewed
Tux Paint mapping. It does not publish Cozy Kids itself on Flathub or enable
system-wide Flatpak installation. App update/removal remains in the system
software manager; reviewed runtime dependency updates are included in the
installation plan and shown before consent.

## Review and trust

The product requires exactly one enabled, GPG-verifying user remote with the
reviewed Flathub HTTPS URL. It never adds repositories. The
[pinned Tux Paint manifest](https://github.com/flathub/org.tuxpaint.Tuxpaint/blob/29732e65760427e75e84396b405f236138a5958e/org.tuxpaint.Tuxpaint.json)
and [project Flatpak guidance](https://tuxpaint.org/download/linux-flatpak/)
establish the app ID, fullscreen argument and initial permission ceiling.
The current resolved metadata also declares X11 alongside fallback-X11.
The visible review includes window display, shared memory, graphics, audio
and microphone, the TuxPaint Pictures folder and persistent app storage.

The adapter uses the documented
[libflatpak ready/operation API](https://docs.flatpak.org/en/latest/libflatpak-api-reference.html).
Preview returns false at `ready`; install returns true only if the newly
resolved app/runtime commits, starting commits for runtime updates, metadata,
origins, sizes and permissions match the reviewed plan. Additional remotes,
app rebases, unrelated applications and external extra-data operations are
refused. Installed versions are verified afterward. Existing local global/app
overrides are refused rather than misrepresented as the manifest permissions.
Only the selected Linux user's installation is managed.

## Disposable desktop probe

Install Flatpak, `gir1.2-flatpak-1.0`, the launcher test package and the normal
[desktop matrix dependencies](DESKTOP_TESTING.md). Use an ordinary disposable
desktop account, never root. The optional fixture setup below explicitly adds
Flathub to a new private test directory, outside the normal user installation.
The product has no corresponding automatic remote-setup path.

```bash
python3 scripts/linux/flatpak_smoke.py --desktop kde --session wayland \
  --browser google-chrome --launch-mode fullscreen \
  --flatpak-user-dir /var/tmp/cozy-flatpak-review --prepare-store \
  --artifacts /var/tmp/cozy-flatpak-review-evidence
```

The first run downloads the reviewed app and its actual runtimes. Keep enough
free space for the repository and deployments. Repeat with GNOME Wayland /
Firefox Snap kiosk and XFCE X11 / Chrome kiosk. A shared disposable store avoids
downloading the runtime again; removal of only the test app allows a fresh
Parent installation review for each row. `--observe-seconds 30` pauses after
launch for a VM screenshot. Fixture setup refuses nonempty unmarked stores.

The probe checks the real Parent review, invalid-token rejection, explicit
installation, exact installed-ref verification, the unchanged native recipe,
an explicit fixture tile command, sandbox/app PIDs inside the owned supervisor
tree, a real pointer click on the mapped close overlay, sandbox termination
and Parent exit cleanup. `flatpak ps` machine columns are used because
Flatpak 1.14.6's `Instance.get_all` GI annotation yielded invalid object wrappers.
The adapter avoids the similarly problematic `operation-done` GI flags signal.

## Evidence and limits

The local `0.6.0+flatpak3` test package has SHA-256
`5e946405ba56c57b27423de432ed0f49c87d9bdc38f33e7ffbfda5162a46222d`.
It is based on `develop` `e366ebc` plus this increment; no application release
or tag was published. The Ubuntu 24.04.4 VM uses Flatpak 1.14.6, kernel
6.8.0-139-generic, one vCPU and 5907 MiB, with the primary desktop/browser
versions listed in `DESKTOP_TESTING.md`.

The final installed artifact passed the real review/install, owned sandbox
launch, overlay click and cleanup on all three primary desktop rows: GNOME
Wayland / Firefox Snap kiosk, Plasma Wayland / Chrome fullscreen and XFCE X11 /
Chrome kiosk. The additional read-only snapshot around preview verifies that
opening the review leaves installed refs unchanged. The shared local suite
passed 472 unit/API tests; focused Flatpak browser checks passed all five
languages, including visible permission text and reachable modal actions.

Retain each `report.json`, `runtime.jsonl`, `lifecycle.json` and launcher log.
The reports retain `automation-passed-manual-pending`: actual drawing,
physical keyboard/touch input, final compositor focus and full visual
acceptance remain release checks. The XFCE snapshot confirms a fullscreen
Tux Paint startup surface with its reachable close control; it does not
certify the drawing workflow or real input. Sandbox loopback/font-cache
warnings observed in the disposable environment did not prevent installation,
owned launch or close, and are retained with the fixture observations.

Focused tests cover trust, unknown permissions, forbidden operations,
old/new runtime commits, plan changes and refusal to replay after restart.
The browser Flatpak suite covers exact source/consent payloads, visible
microphone access in all five languages at 800x600, explicit tile switching,
failed-save rollback, retained family labels/visibility and source errors.
Its local package mutations are HTTP fixtures. Hosted CI runs that suite
separately from the real desktop qualification.
