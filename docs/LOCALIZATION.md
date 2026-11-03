# Languages and translation contributions

English, German, Spanish and French are enabled. Choose a language during
installation or setup, or under **Parent settings → System** and save.
Profile names, home titles and tile labels already set by the family are
preserved. Italian is tracked in [ROADMAP.md](ROADMAP.md).

The guided installer, launcher, app catalog and media library use these packs.
Standalone bootstrap diagnostics and `--help` are in English. Native helpers
and the embedded browser wrapper use the language selected at installation.
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

Before enabling Italian, review the installer, child UI, Parent settings and
recovery screens. Include long labels, localized dates and numbers, keyboard
use, speech availability and 800×600 layouts. Direction-aware layout and
per-language review ownership are tracked separately in the roadmap.
