# Languages and translation contributions

German and English are the enabled UI languages today. Spanish and French are
the next requested languages, followed by Italian. Their complete translations
and review are tracked in [ROADMAP.md](ROADMAP.md).

## Current translation pipeline

`src/language_registry.json` lists enabled language codes, display names and
icons, and specifies the default language. The installer uses it for locale
detection, the guided menu and locale installation. Backend configuration
validation reads the same registry, and the installed frontend uses it for
first-run choices and locale loading on the launcher and media screens.

Edit the canonical German and English translation tables in
`src/translations/`. The installer reads these tables directly.
`scripts/generate-locales.py` maps the same keys to `uiText` and generates
the browser resources in `src/frontend/locales/`. After editing a table, run:

```bash
python3 scripts/generate-locales.py
python3 scripts/check.py
```

English supplies missing strings. The loader rejects unknown or duplicate keys,
changed named placeholders such as `{count}`, and values with line breaks.
The generator also checks that every key referenced by the installer and browser
mapping is available. Keep both enabled languages aligned when changing text.

Setup and child profile texts use the `first_run_*` and `profile_*` keys. The
generator groups them for the frontend, and the installer embeds the selected
language in the launcher for startup. If a different locale cannot be loaded
during setup, the screen keeps the current language and offers a retry.

Catalog data is already open to additional language keys: `name_es`,
`desc_fr`, `age_it` or a reference's `label_es`, for example. The shared
`catalogText` lookup uses the configured language and falls back to English.
No language-specific branch is needed to add these fields. A catalog field
alone does not enable its language in settings.

## Planned foundation before enabling more UI languages

Move the remaining specialized frontend text tables and language-specific
rendering branches to locale data. Add direction metadata when implementing
RTL support.

Validate plural forms and document terminology, contribution/review ownership
and missing strings.
Review all installer, child, Parent, setup and recovery surfaces for Spanish
and French, then Italian, before enabling each pack. Include long labels,
localized dates/numbers, keyboard use, speech availability and 800×600 layouts
in acceptance. Prepare direction-aware layout for later RTL languages.
