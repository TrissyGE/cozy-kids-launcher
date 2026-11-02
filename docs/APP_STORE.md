# Parent app store

Open **Parent settings → Apps & Media → App store** to browse the local
recommendations. Search matches names, descriptions and categories. Category
and status filters can be combined to find installed, missing or already-added
apps. Existing tiles are recognized even when they are hidden.

Each card has expandable parent guidance: suggested age, offline availability,
license, input devices, network considerations, a review date and HTTPS sources. Missing
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

`src/recommendations.json` stores localized descriptions and optional guidance
fields (`age`, `offline`, `license`, `input`, `network`, `source`, `reviewed`,
`references`). Eleven existing recommendations have sourced guidance: Tux Paint,
GCompris, YouTube Kids, KTurtle, KBruch, KTuberling, KLettres, Kanagram, KHangMan,
KBlocks and KReversi. See [CATALOG_GUIDANCE.md](CATALOG_GUIDANCE.md) for the review
scope and primary sources. YouTube Kids remains an online provider with possible
advertising; KBlocks is a falling-block game requiring timely input.

The expanded details show a localized review date and up to four supporting
references alongside the main project source. Invalid dates display as unknown.
Only HTTPS links without embedded credentials are shown; duplicates are removed
and labels render as plain text. Filtering to one result lets the card use the
available width for more readable details.

Names, descriptions, age/network guidance and reference labels use
`<field>_<language>` data keys, falling back to English when a translation is
absent. This permits more catalog translations without language-specific code
branches. It does not enable unreviewed UI language packs; see
[LOCALIZATION.md](LOCALIZATION.md) for the current pipeline and planned work.

New package mappings and launch recipes require separate per-app fullscreen
and return-to-launcher checks. This discovery increment retains the existing
package mappings, fullscreen supervision and custom launch arguments.

The planned **RetroGameCorner** belongs to the v0.9 Living Room milestone in
[ROADMAP.md](ROADMAP.md). It will need parent guidance and self-provided ROM/BIOS
files; no emulator, game download service or ROM bundle is added by this change.
