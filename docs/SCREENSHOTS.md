# Screenshot Guide

For a public GitHub release, capture these screenshots from the real device:

## Required shots

1. **Kids home screen**
   - fullscreen launcher
   - 4-tile layout
   - clear title visible

2. **Kids home screen, alternate theme**
   - show another color preset (e.g., blue or green)

3. **Parent settings, general section**
   - title, theme, layout mode, button labels
   - PIN setup visible

4. **Parent settings, tile management**
   - show card-based tile editing
   - move up/down buttons

5. **Normal desktop with Kids Mode shortcut**
   - proves the overlay model

## Language

Screenshots should be taken with the launcher set to **English** for the GitHub page. Re-install with:

```bash
curl -fsSL https://raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main/scripts/install.sh | bash -s -- --lang en
```

## Capture guidelines

- use clean wallpaper
- avoid personal/private filenames
- keep icons and labels tidy
- hide notifications
- avoid showing personal chat, browser history, Wi-Fi names, etc.

## Suggested filenames

- `screenshot-home.png`
- `screenshot-theme-blue.png`
- `screenshot-parent-general.png`
- `screenshot-parent-tiles.png`
- `screenshot-desktop.png`

Place finished screenshots in a `screenshots/` folder at the repository root and reference them in `README.md`.
