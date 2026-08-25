# Privacy and Safety Notes

This project is intended for private family computers.

## Local-first

The launcher is designed to run locally:

- local config file
- local HTTP server on localhost
- local browser in kiosk mode
- local application launching

No cloud backend is required.

## What parents should review before using

- which applications are visible to the child
- whether a web browser is enabled
- whether shutdown should be available
- whether parent settings should be protected with a PIN

When configured, the PIN is stored as a salted password hash. The public launcher API exposes only that a PIN exists. A successful PIN entry creates a temporary parent session for sensitive actions.

## Publishing guidance

Before sharing screenshots or configs publicly:

- remove personal names if desired
- hide private filenames
- avoid showing private wallpaper assets if they are licensed or personal
- avoid screenshots with notifications, chats, browser history, or Wi-Fi names

## Security scope

This project is a launcher UI, not a hardened sandbox.

It improves usability for children, but it is not a full kiosk security solution by itself.
The parent PIN protects launcher controls; it does not replace Linux user separation, disk encryption, operating-system updates, or a restricted child account.
