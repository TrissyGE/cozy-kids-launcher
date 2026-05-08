# Screenshot Guide

For a public GitHub release, capture these screenshots from the real device running the latest version.

## Required shots

1. **Kids home screen — default theme**
   - Use the default "Rosa" theme or any bright color theme
   - 4-tile (large) layout visible
   - Title clearly readable
   - Clock badge in top-right corner visible
   - Include at least 3–4 visible tiles with emoji

2. **Kids home screen — world theme**
   - Switch to a world theme with background image (e.g., Wald, Ocean, or Weltraum)
   - Show the wallpaper background behind the tiles
   - Same 4-tile layout

3. **Kids home screen — custom theme**
   - Create a custom theme with your own colours (e.g., orange + yellow gradient)
   - Optional: add a custom background image path
   - Shows the colour-picker result on the kids screen

4. **Parent settings — general**
   - Title input, theme picker button, layout mode dropdown
   - PIN setup section visible
   - Timer section with dropdown and status
   - Update check button and version display

5. **Parent settings — tile management**
   - Show drag-and-drop rows with `⋮⋮` handles
   - Emoji, label, visibility checkbox, app dropdown per row
   - One row expanded with browser URL input (show `special:browser:` or `special:external-browser:`)

6. **App recommendations panel**
   - Scroll down to the recommendations section in admin
   - Show installed vs. missing app cards
   - Include one app with "Add tile" button visible

7. **Theme picker overlay**
   - Open the theme picker in admin
   - Show the grid of 15 theme thumbnails (including "Custom")
   - One theme selected/highlighted

8. **In-app overlay (embedded browser)**
   - Launch a `special:browser:` app (e.g., a kid-friendly website)
   - Show the floating overlay pill with ❌ close button and timer display
   - Overlay should be visible (move mouse to trigger it if auto-hidden)

9. **Timer warning / block screen**
   - Set a 1-minute timer for testing
   - Capture the warning overlay (last 5 minutes)
   - Or the block screen when time is up (PIN entry + extend buttons)

10. **Normal desktop with Kids Mode shortcut**
    - Exit to desktop
    - Show the "Kids Mode" desktop shortcut/icon
    - Clean wallpaper, no personal windows open

## Language

Screenshots should be taken with the launcher set to **English** for the GitHub page. Re-install with:

```bash
curl -fsSL https://raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main/scripts/install.sh | bash -s -- --lang en
```

## Capture guidelines

- Use clean wallpaper (no family photos or sensitive content)
- Avoid personal/private filenames in tiles or apps
- Keep icons and labels tidy
- Hide notifications and system trays if possible
- Avoid showing personal chat, browser history, Wi-Fi names, etc.
- Use a 16:9 or 16:10 screen resolution for consistent aspect ratio
- Capture at native resolution (no upscaling)

## Suggested filenames

Place finished screenshots in `screenshots/` at the repository root:

| File | Content |
|---|---|
| `screenshot-home-default.png` | Kids home, default colour theme |
| `screenshot-home-world.png` | Kids home, world theme with wallpaper |
| `screenshot-home-custom.png` | Kids home, custom colours |
| `screenshot-admin-general.png` | Parent settings, general section |
| `screenshot-admin-tiles.png` | Parent settings, drag-and-drop tile rows |
| `screenshot-admin-recommendations.png` | App recommendations panel |
| `screenshot-theme-picker.png` | Theme picker overlay |
| `screenshot-browser-overlay.png` | Embedded browser with in-app overlay |
| `screenshot-timer-block.png` | Timer expired block screen |
| `screenshot-desktop.png` | Desktop with Kids Mode shortcut |

After capturing, reference them in `README.md` under the "What it looks like" section.
