# Parent app store

Open **Parent settings → Apps & Media → App store** to browse the local
recommendations. Search matches names, descriptions and categories. Category
and status filters can be combined to find installed, missing or already-added
apps. Existing tiles are recognized even when they are hidden.

Each card has expandable parent guidance: suggested age, offline availability,
license, input devices, network considerations and an HTTPS source. Missing
guidance is shown as unknown. Ages are suggestions; parents decide what suits
their child. Offline support describes the reviewed core use, not a guarantee
that every feature avoids the network.

## Install directly

The normal Install button uses the existing PackageKit workflow:

1. Prepare and display the package plan, including dependencies and download
   size where the provider supplies it.
2. Ask the parent to review and explicitly confirm that plan.
3. Let the desktop request system authorization through Polkit. The launcher
   does not collect or store the system password.
4. Show the real transaction state and recover the status after a reconnect
   without repeating installation consent automatically.
5. Offer to add the installed app as a child-facing tile.

No terminal command needs to be copied for this flow. See
[PACKAGE_PROVIDERS.md](PACKAGE_PROVIDERS.md) for supported distributions,
runtime dependencies, provider limits and the separate real-desktop acceptance
check. Unsupported systems receive guidance to the graphical software manager.
The older manual-plan API remains available for compatibility.

For an already installed app, **Add** saves its tile immediately. A rejected
save restores the previous tile list and displays an error. Removing a tile
does not uninstall its system package. Search and filters are kept only in the
current page session.

The tile editor also has an installed-app selector using localized desktop
entries. Its search roots, override rules and supported launch formats are
documented in [APP_DISCOVERY.md](APP_DISCOVERY.md).

## Curated guidance

`src/recommendations.json` stores bilingual descriptions and optional guidance
fields (`age`, `offline`, `license`, `input`, `network`, `source`, `reviewed`).
Tux Paint, GCompris and YouTube Kids have guidance reviewed against their
official documentation on 2026-11-02. In particular, YouTube Kids is an online
provider with its own privacy rules and possible advertising; it is not
described as universally ad-free.

Review sources: [Tux Paint overview](https://tuxpaint.org/),
[Tux Paint privacy policy](https://tuxpaint.org/privacy/),
[GCompris overview](https://gcompris.net/index-en.html),
[GCompris FAQ](https://gcompris.net/faq-en.html) and
[YouTube Kids advertising](https://support.google.com/youtubekids/answer/6130541?hl=en).

New package mappings and launch recipes require separate per-app fullscreen
and return-to-launcher checks. This discovery increment retains the existing
package mappings, fullscreen supervision and custom launch arguments.

The planned **RetroGameCorner** belongs to the v0.9 Living Room milestone in
[ROADMAP.md](ROADMAP.md). It will need parent guidance and self-provided ROM/BIOS
files; no emulator, game download service or ROM bundle is added by this change.
