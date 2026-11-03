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

The installer in `scripts/install.sh` currently contains the canonical German
and English UI strings. `src/frontend/state.js` maps the generated template
values to `uiText`; `scripts/generate-locales.py` exports the corresponding
JSON resources in `src/frontend/locales/`. After changing UI strings, run:

```bash
python3 scripts/generate-locales.py
python3 scripts/check.py
```

Keep both enabled languages aligned. Use `uiText` for interface labels rather
than writing new translated literals into rendering code. Existing freshness
and language-switching checks protect the generated resources. Plural and
placeholder validation are planned separately.

Catalog data is already open to additional language keys: `name_es`,
`desc_fr`, `age_it` or a reference's `label_es`, for example. The shared
`catalogText` lookup uses the configured language and falls back to English.
No language-specific branch is needed to add these fields. A catalog field
alone does not enable its language in settings.

## Planned foundation before enabling more UI languages

Move canonical translations into data files. A reviewed language should be
enabled by adding its data and registry entry. Until that migration, each
enabled language still needs translations in the installer and the existing
specialized text tables. Add direction metadata when implementing RTL support.

Use a shared English fallback and validate keys, placeholders and plural
forms. Document terminology, contribution/review ownership and missing strings.
Review all installer, child, Parent, setup and recovery surfaces for Spanish
and French, then Italian, before enabling each pack. Include long labels,
localized dates/numbers, keyboard use, speech availability and 800×600 layouts
in acceptance. Prepare direction-aware layout for later RTL languages.
