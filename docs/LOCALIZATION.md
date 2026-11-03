# Languages and translation contributions

English, German, Spanish, French and Italian are enabled. Choose a language during
installation or setup, or under **Parent settings → System** and save.
Profile names, home titles and tile labels already set by the family are
preserved.

The guided installer, launcher, app catalog and media library use these packs.
Standalone bootstrap diagnostics and `--help` are in English. Native helpers
read the saved language when displaying timer messages, and the local server
renders each new embedded browser wrapper in the saved language. Both use the
same canonical translation tables as the installer.
Speech feedback requires a local engine and an available voice for the
selected language.

## Current translation pipeline

`src/language_registry.json` lists enabled language codes, display names and
icons, and specifies the default language. The installer uses it for locale
detection, the guided menu and locale installation. Backend configuration
validation reads the same registry, and the installed frontend uses it for
first-run choices and locale loading on the launcher and media screens.

Edit the canonical translation tables in
`src/translations/`. The installer reads these tables directly.
`scripts/generate-locales.py` maps the same keys to `uiText` and generates
the browser resources in `src/frontend/locales/`. After editing a table, run:

```bash
python3 scripts/generate-locales.py
python3 scripts/check.py
```

English supplies missing strings when loading a partial translation. The loader rejects unknown or duplicate keys,
changed named placeholders such as `{count}`, and values with line breaks.
The generator also checks that every key referenced by the installer and browser
mapping is available. Generation requires all enabled tables to cover the
English keys. Translate new keys in every enabled language before regenerating.

Setup and child profile texts use the `first_run_*` and `profile_*` keys. The
generator groups them for the frontend, and the installer embeds the selected
language in the launcher for startup. If a different locale cannot be loaded
during setup, the screen keeps the current language and offers a retry.

Catalog data is already open to additional language keys: `name_es`,
`desc_fr`, `age_it` or a reference's `label_es`, for example. The shared
`catalogText` lookup uses the configured language and falls back to English.
No language-specific branch is needed to add these fields. A catalog field
alone does not enable its language in settings.

The catalog result and package counts use browser plural rules. Their singular
and general forms must carry the same placeholders. The browser also formats
dates and numbers using the current interface locale.

## Reviewing a new language

Start a draft in `src/translations/<code>.json`. Keep it out of
`src/language_registry.json` while it is being translated. Run
`python3 scripts/generate-locales.py --report <code>` to list missing keys
without enabling the draft. The report measures key coverage. A complete key
count still needs a language review.

Use a consistent term for the adult settings area, keep the screen timer
distinct from a child's daily app budget, and keep PIN and package confirmation
labels explicit about what the action does. Preserve placeholders, family
labels, product names and commands. Follow the existing catalog guidance for
claims about privacy, network access and age suitability.

The PR author records the tested flows and remaining gaps. A fluent reviewer
checks terminology, tone, and the rendered screens before the maintainer
enables the pack. Review the installer, child view, Parent settings, catalog,
and error states. Include long labels, localized dates and numbers, keyboard
use, available local voices, and 800×600 layouts. Use the required Linux
[desktop sessions](DESKTOP_TESTING.md) for native helper acceptance. Record
which sessions were actually exercised.

## Right-to-left layouts

Set `"direction": "rtl"` on the registry entry for a right-to-left language.
The installer and browser wrapper set the document direction, and the
launcher and media library update it when they load the saved locale.
The direction defaults to left-to-right for registry entries without the
field.

Use CSS inline start and end for spacing and placement. Previous and next
controls follow reading order, while arrow keys move in the physical
direction shown on screen. Keep command arguments, URLs and PIN digits
left-to-right. Let user-entered names and home titles determine their own
direction.

The browser suite exercises an in-memory RTL fixture at 800×600. Before
enabling a real pack, a fluent reviewer still needs to check mixed-script
text, labels, screen readers, touch input, and the native helper windows.
Physical-device and right-to-left language acceptance remain tracked in
[ROADMAP.md](ROADMAP.md).
