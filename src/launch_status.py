"""Fixed supervisor exit codes; never transport app output or family values."""

STARTUP_FAILURES = {
    "display-unavailable": (71, "Cannot connect to the X11 display for fullscreen"),
    "wm-unavailable": (72, "The window manager does not advertise fullscreen"),
    "app-exited": (73, "App exited before fullscreen was confirmed"),
    "fullscreen-timeout": (74, "The app did not enter fullscreen"),
    "cancelled": (75, "Fullscreen startup was cancelled"),
    "display-mode": (76, "Managed fullscreen requires the supported X11/xcb platform"),
    "app-unavailable": (77, "The application could not be started"),
    "ownership-unconfirmed": (78, "Tile process ownership could not be established"),
    "overlay-unavailable": (79, "Tile overlay could not be started"),
}


class StartupError(OSError):
    def __init__(self, reason):
        self.reason = reason
        self.exit_code, message = STARTUP_FAILURES[reason]
        super().__init__(message)


def failure_reason(exit_code):
    return next((reason for reason, (code, _) in STARTUP_FAILURES.items()
                 if code == exit_code), "ownership-unconfirmed")
