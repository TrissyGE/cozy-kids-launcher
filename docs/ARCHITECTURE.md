# Architecture

## Design principle

Do not replace the desktop session.

Instead:

- keep a normal Linux desktop as the base
- start a fullscreen kids launcher on top
- allow easy exit back to desktop

This avoids fragile desktop-environment hacks and makes the setup easier to maintain.

## Components

### 1. Fullscreen browser UI

A local HTML/CSS/JS app renders:

- title
- tile grid
- paging
- parent settings
- shutdown / exit controls

### 2. Local HTTP server

A tiny Python HTTP server:

- serves the frontend
- loads and saves config JSON
- lists installed applications
- launches configured programs
- handles shutdown and exit actions

### 3. Desktop integration

- autostart launches kids mode after login
- desktop shortcut reopens kids mode
- shutdown listener allows safe local poweroff

## Why not do everything in Plasma directly?

Because desktop-shell configuration becomes brittle fast:

- folder views cache strangely
- screen mappings drift
- widget layouts are fragile
- switching modes by rewriting Plasma config is unreliable

The browser-overlay approach is much more robust.
