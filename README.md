# Cozy Kids Launcher

A local-first fullscreen kids launcher for Linux desktops.

It gives children a friendly, touchable home screen while keeping a normal desktop session underneath for parents.

## Why this is interesting

Most kids launchers are either:

- mobile-first
- heavily locked-down
- outdated
- ugly
- or tied to a specific platform

Cozy Kids Launcher takes a simpler approach:

- normal Linux desktop stays intact
- kids see a fullscreen launcher
- parents can edit tiles visually
- everything stays local and understandable

## Features

- fullscreen kids home screen
- large app tiles with emoji/icons
- dynamic pages with left/right navigation
- 4-tile or 9-tile layout mode
- parent settings inside the UI
- editable title, colors, labels, and tiles
- local app launching
- exit back to desktop
- local shutdown button
- desktop shortcut to reopen kids mode

## Current maturity

This project is **real and working**, extracted from a private family laptop setup.

It is **publish-ready as a repository** and now includes a first reusable installer flow, though packaging polish is still ongoing.

That means:

- the concept is proven
- the UX is working
- the code is worth sharing
- installer consolidation has started in a reusable form
- broader release polish is still a next step

## Demo flow

1. child logs in
2. fullscreen launcher opens automatically
3. child taps an app tile
4. parent can open settings and edit tiles
5. parent can exit back to desktop
6. parent can reopen kids mode from the desktop shortcut

## Screens you should show on GitHub

See [docs/SCREENSHOTS.md](docs/SCREENSHOTS.md).

Recommended screenshots:

- kids home screen
- parent settings
- tile management
- normal desktop with Kids Mode shortcut

## Repository structure

```text
cozy-kids-launcher/
  README.md
  LICENSE
  VERSION
  CHANGELOG.md
  docs/
    ARCHITECTURE.md
    INSTALL.md
    PRIVACY.md
    ROADMAP.md
    SCREENSHOTS.md
  examples/
    config.example.json
  scripts/
    install.sh
    install-one-liner.sh
    update.sh
    deploy.sh
  src/
    server.py
    index.html
    no-media.html
    launcher.sh
```

## Architecture

Short version:

- a normal desktop session stays underneath
- a local Python server serves the launcher UI on localhost
- a kiosk browser renders the kids interface
- config is stored in local JSON

More here: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Installation

**One line. Open a terminal, paste, press Enter.**

```bash
curl -fsSL https://raw.githubusercontent.com/TrissyGE/cozy-kids-launcher/main/scripts/install-one-liner.sh | bash
```

It downloads, installs, and sets everything up automatically. Log out and back in — the launcher starts on its own.

For details, options, and troubleshooting, see [docs/INSTALL.md](docs/INSTALL.md).

## Privacy

This is designed to stay local-first.

See: [docs/PRIVACY.md](docs/PRIVACY.md)

## Roadmap

See: [docs/ROADMAP.md](docs/ROADMAP.md)

## Example config

See: [examples/config.example.json](examples/config.example.json)

## License

MIT, see [LICENSE](LICENSE).

## Honest note

This project was not born as a polished product. It was built the right way: by solving a real family problem until the result became genuinely good.

That is exactly why it feels different.
