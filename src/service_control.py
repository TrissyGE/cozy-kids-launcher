"""Opt-in systemd user supervision for the existing graphical launcher."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from lifecycle_state import clear_lifecycle_request, read_lifecycle_state, write_lifecycle_request


UNIT = "cozy-kids-launcher.service"
GRAPHICAL_ENV = (
    "DISPLAY", "WAYLAND_DISPLAY", "XAUTHORITY", "XDG_SESSION_TYPE",
    "XDG_CURRENT_DESKTOP", "XDG_SESSION_DESKTOP", "DBUS_SESSION_BUS_ADDRESS", "PATH",
)


def systemctl(*arguments):
    result = subprocess.run(
        ["systemctl", "--user", *arguments], capture_output=True, text=True, timeout=45,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "systemd user command failed")
    return result.stdout.strip()


def atomic_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".cozy-service-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def session_environment(environment):
    if not (environment.get("DISPLAY") or environment.get("WAYLAND_DISPLAY")):
        raise ValueError("Start Cozy Kids from the graphical desktop session.")
    lines = []
    for key in GRAPHICAL_ENV:
        value = environment.get(key, "")
        if any(character in value for character in "\0\r\n"):
            raise ValueError(f"Invalid graphical environment variable: {key}")
        escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
        lines.append(f'{key}="{escaped}"\n')
    return "".join(lines)


class UserService:
    def __init__(self, home, environment):
        self.environment = environment
        self.app_root = home / ".local/share/cozy-kids-launcher"
        self.marker = home / ".config/cozy-kids-launcher/user-service"
        self.cache = home / ".cache/cozy-kids-launcher"
        config_home = Path(environment.get("XDG_CONFIG_HOME") or home / ".config")
        self.unit_path = config_home / "systemd/user" / UNIT

    def template(self):
        return (self.app_root / UNIT).read_text(encoding="utf-8")

    def check_unit(self):
        if self.unit_path.is_symlink() or (
            self.unit_path.exists() and self.unit_path.read_text(encoding="utf-8") != self.template()
        ):
            raise ValueError(f"Existing {UNIT} differs from the Cozy Kids service.")

    def require_enabled(self):
        if not self.marker.is_file() or not self.unit_path.is_file():
            raise ValueError("Run cozy-kids-launcher --service enable first.")
        self.check_unit()

    def require_launcher_idle(self):
        import fcntl

        lock = self.cache / "launcher.lock"
        if not lock.exists():
            return
        try:
            with lock.open("r") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise ValueError("Close the running launcher before starting the user service.") from error

    def enable(self):
        self.check_unit()
        if not self.marker.is_file():
            self.require_launcher_idle()
        previous = self.unit_path.exists()
        if not previous:
            atomic_text(self.unit_path, self.template())
        try:
            systemctl("daemon-reload")
            atomic_text(self.marker, "systemd\n")
        except (OSError, RuntimeError, subprocess.SubprocessError):
            if not previous:
                self.unit_path.unlink(missing_ok=True)
            raise

    def active_state(self):
        return systemctl("show", UNIT, "--property=ActiveState", "--value")

    def stop(self):
        self.require_enabled()
        request = self.cache / "lifecycle-request.json"
        active = self.active_state() in {"active", "activating", "reloading"}
        if active:
            write_lifecycle_request(request, "manual-stop")
        try:
            systemctl("stop", UNIT)
        finally:
            if active:
                clear_lifecycle_request(request)

    def disable(self):
        self.require_enabled()
        self.stop()
        self.unit_path.unlink()
        self.marker.unlink()
        systemctl("daemon-reload")

    def start(self, recover=False):
        self.require_enabled()
        environment = session_environment(self.environment)
        runtime = self.environment.get("XDG_RUNTIME_DIR")
        if not runtime or not Path(runtime).is_dir():
            raise ValueError("The graphical session has no XDG_RUNTIME_DIR.")
        if recover:
            self.stop()
        elif self.active_state() in {"active", "activating", "reloading"}:
            return
        self.require_launcher_idle()
        atomic_text(Path(runtime) / "cozy-kids-launcher-session.env", environment)
        systemctl("start", UNIT)

    def status(self):
        enabled = self.marker.is_file()
        try:
            lifecycle = read_lifecycle_state(self.cache / "lifecycle.json")
        except (OSError, ValueError):
            lifecycle = None
        return {
            "mode": "systemd" if enabled else "standalone",
            "unitState": self.active_state() if enabled else None,
            "lastLifecycle": lifecycle,
        }


def main():
    import fcntl

    parser = argparse.ArgumentParser(prog="cozy-kids-launcher --service")
    parser.add_argument("command", choices=("enable", "disable", "start", "stop", "recover", "status"))
    parser.add_argument("--autostart", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    service = UserService(Path.home(), os.environ)
    try:
        if args.command == "status":
            print(json.dumps(service.status(), indent=2))
        else:
            if args.autostart:
                # Match the existing XDG autostart delay without blocking manual starts.
                time.sleep(12)
            service.cache.mkdir(mode=0o700, parents=True, exist_ok=True)
            with (service.cache / "service-control.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                if args.command in ("start", "recover"):
                    service.start(recover=args.command == "recover")
                else:
                    getattr(service, args.command)()
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(str(error))


if __name__ == "__main__":
    main()
