# Screenshot guide

The four images used by the GitHub landing page are generated from the real launcher UI with a clean, deterministic demo profile.

## Regenerate the README images

Requirements:

- Linux or WSL;
- Python 3;
- Google Chrome or Chromium;
- the normal launcher installer prerequisites.

From the repository root:

```bash
python3 scripts/take-screenshots.py
```

On Windows, run the same command inside the configured WSL distribution:

```powershell
wsl.exe -d Ubuntu --cd /path/to/cozy-kids-launcher -- python3 scripts/take-screenshots.py
```

The script:

1. installs the current checkout into a temporary home directory;
2. writes a curated English configuration containing no personal data;
3. starts the local launcher server on an ephemeral port;
4. captures real browser renders at 1440×900;
5. removes the temporary profile and browser data.

It does not read or change the developer's installed launcher configuration.

## Generated files

| File | README content |
|---|---|
| `screenshots/screenshot-home-default.png` | Pink theme and four-tile kids home |
| `screenshots/screenshot-home-world.png` | Illustrated ocean theme |
| `screenshots/screenshot-admin-general.png` | Parent settings and tile management |
| `screenshots/screenshot-theme-picker.png` | Localized theme selection overlay |

Use `--browser <command>` to select a specific Chromium-family browser or `--output-dir <directory>` for a review run that should not replace the checked-in images.

## Review checklist

Before committing regenerated images, verify:

- labels are English and readable;
- the displayed version matches `VERSION`;
- no usernames, paths, network names, browser history, or other personal data appear;
- tiles and controls are not clipped;
- the world-theme background and theme thumbnails loaded;
- all four images have the same 1440×900 dimensions.

Commit screenshot changes only when the interface or the curated demo content changed. Avoid re-encoding unchanged images.

## Full-device release gallery

Some states depend on a real Linux desktop and are intentionally not generated for the README:

- external browser with the close/timer overlay;
- local VLC or MPV playback;
- timer warning and expired block screen;
- desktop shortcut and session startup;
- application recommendations based on installed packages.

Capture those from a disposable user or the [WSLg test environment](WSL_TESTING.md) when they are useful for a release announcement or manual QA. Keep them out of the primary README unless they are current, privacy-safe, and materially clarify a feature.
