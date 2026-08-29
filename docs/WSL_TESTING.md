# Graphical testing with WSLg

Windows 11 with WSL 2 and WSLg is a convenient development environment for the launcher. It can display Linux X11 and Wayland windows on the Windows desktop and forwards Linux audio. The test scripts use a completely isolated home directory under `~/.local/state/cozy-kids-launcher/wsl-smoke`.

WSLg is not a complete Linux desktop. It is suitable for launcher rendering, browser, audio, video, process, and basic overlay tests. Final kiosk, focus, always-on-top, autostart, shutdown, and GNOME/KDE/XFCE integration still need a Linux virtual machine or physical Linux device.

## One-time setup

In an Ubuntu WSL shell, from the repository root:

```bash
sudo bash scripts/wsl/setup-test-env.sh
```

This installs Tk, X11 diagnostics, Mesa diagnostics, PulseAudio tools, VLC, FFmpeg, a small Python WebSocket client for deterministic DevTools screenshots, window-control tools, and Google Chrome Stable on amd64. Pass `--without-chrome` if a supported Chromium-family browser is already installed.

## Run the smoke test

The fast, headless browser journeys do not require a visible WSLg session:

```bash
python3 scripts/wsl/browser-e2e.py
```

They cover home rendering, PIN setup and rejection, saved settings, theme selection, timer start/stop, and current/available/error update states against local fixtures. The same run exercises keyboard-only and touch navigation, reduced motion, forced colors, and the 800x600 home and Parent layouts. Output is kept under `.test-artifacts/browser-e2e/`.

For the full multimedia and WSLg integration test, run:

```bash
bash scripts/wsl/run-gui-smoke.sh
```

The test:

1. verifies WSLg display, PulseAudio, and OpenGL;
2. generates deterministic H.264/AAC video and WAV audio fixtures;
3. installs the current checkout into an isolated test home;
4. starts the local server on port `38439`;
5. renders launcher and website screenshots in headless Chrome;
6. launches the media tile through the real HTTP route and checks VLC;
7. checks embedded and external web launch routes;
8. probes every recommended website and records current iframe policies.

The normal user installation under `~/.config/cozy-kids-launcher` and `~/.local/share/cozy-kids-launcher` is not modified.

Use `--headless` to skip the short visible external-browser window. Use `--visible-seconds N` to change how long it stays open. Results are written to:

```text
~/.local/state/cozy-kids-launcher/wsl-smoke/
  artifacts/
  logs/
```

If Mesa reports `llvmpipe`, the script automatically selects WSLg's D3D12 Gallium driver when `/dev/dxg` exists. It does not change the user's shell profile.

## Website and DRM checklist

The network probe can also run independently:

```bash
python3 scripts/wsl/probe-web-targets.py
python3 scripts/wsl/probe-web-targets.py --json
```

Header and page-load tests cannot prove that protected playback works. For YouTube Kids, Netflix, Disney+, Prime Video, PBS Kids, ZDFtivi, and KiKA, manually verify:

1. the tile opens in the dedicated external browser profile;
2. navigation, video, fullscreen, and audio work;
3. the launcher overlay remains usable;
4. closing the overlay terminates only the child app and returns focus;
5. for subscription services, an ordinary test account can log in and Widevine playback starts.

Never commit the generated browser profile or share account credentials. The persistent external profile allows a developer to log in locally once without mixing streaming cookies into the main launcher profile.

## Final Linux desktop matrix

Before a release, repeat the manual smoke test in at least one full desktop VM:

| Environment | What it validates |
| --- | --- |
| WSLg | Fast UI, browser, codecs, audio, and process smoke tests |
| Ubuntu GNOME VM | Autostart, kiosk, focus, overlay, and shutdown integration |
| KDE Plasma VM | KDE wrappers, fullscreen focus, overlay, and desktop shortcuts |
| XFCE VM | Lightweight target behavior and generic X11 integration |

Use the repeatable harness and evidence rules in [DESKTOP_TESTING.md](DESKTOP_TESTING.md). WSLg results must not be recorded as a GNOME, KDE Plasma, or XFCE matrix pass.

Microsoft's WSLg documentation explicitly describes GUI application support and notes that it does not provide a full desktop experience: [Run Linux GUI apps with WSL](https://learn.microsoft.com/en-us/windows/wsl/tutorials/gui-apps).
