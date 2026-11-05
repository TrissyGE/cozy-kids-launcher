#!/usr/bin/env python3
"""Inspect a native catalog adapter; opt into real changes only in disposable tests."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import subprocess

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from package_install import PackageInstaller
from packagekit_backend import InstallError, PackageKitBackend, package_identity
from package_provider import read_os_release


def bootstrap_container(log_directory):
    """Start real daemons in a disposable container without systemd as PID 1."""
    log_directory.mkdir(parents=True, exist_ok=True)
    Path("/run/dbus").mkdir(exist_ok=True)
    subprocess.run(["dbus-uuidgen", "--ensure"], check=True)
    subprocess.run(["dbus-daemon", "--system", "--fork", "--nopidfile"], check=True)
    for name, candidates, arguments in (
        ("polkit", ("/usr/lib/polkit-1/polkitd", "/usr/libexec/polkit-1/polkitd"), ("--no-debug",)),
        ("packagekit", ("/usr/lib/packagekitd", "/usr/libexec/packagekitd", "/usr/lib/PackageKit/packagekitd"),
         ("--keep-environment", "--disable-timer", "--verbose")),
    ):
        path = next((value for value in candidates if Path(value).is_file()), None)
        if path is None:
            raise RuntimeError("Missing container daemon: " + name)
        with (log_directory / (name + ".log")).open("w") as log:
            process = subprocess.Popen([path, *arguments], stdout=log, stderr=log, start_new_session=True)
        time.sleep(.5)
        if process.poll() is not None:
            raise RuntimeError("Container daemon exited: " + name)
    from gi.repository import Gio, GLib
    bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        owners = [bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                                "NameHasOwner", GLib.Variant("(s)", (name,)), GLib.VariantType.new("(b)"),
                                Gio.DBusCallFlags.NONE, 1000, None).unpack()[0]
                  for name in ("org.freedesktop.PackageKit", "org.freedesktop.PolicyKit1")]
        if all(owners):
            return
        time.sleep(.1)
    raise RuntimeError("Container package/authorization daemons did not become ready")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", choices=("tuxpaint", "kturtle", "kolourpaint", "kgeography"), required=True)
    parser.add_argument("--execute", action="store_true", help="Actually install and remove the app; requires an initially absent app in a disposable system")
    parser.add_argument("--expect-denied", action="store_true", help="Expect the real non-admin installation to be denied; never bypass authorization")
    parser.add_argument("--bootstrap-container", action="store_true", help="Start private test daemons; only accepted as root in a disposable container")
    parser.add_argument("--bootstrap-only", action="store_true", help="Only start the container daemons; requires --bootstrap-container")
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    if args.bootstrap_only and not args.bootstrap_container:
        raise ValueError("Bootstrap-only requires --bootstrap-container")
    container = Path("/run/.containerenv").exists() or Path("/.dockerenv").exists()
    if os.geteuid() == 0 and not container:
        raise RuntimeError("Root execution is restricted to disposable containers")
    if args.expect_denied and (not args.execute or os.geteuid() == 0):
        raise ValueError("Denial tests require --execute as an ordinary user")
    if args.bootstrap_container:
        if not container or os.geteuid() != 0:
            raise ValueError("Daemon bootstrap requires a disposable root container")
        bootstrap_container(args.artifacts.parent / "daemons")
        if args.bootstrap_only:
            return
    args.artifacts.mkdir(parents=True, exist_ok=True)
    catalog = json.loads((ROOT / "src/recommendations.json").read_text())
    recipe = next(item for item in catalog if item["id"] == args.app)
    backend = PackageKitBackend()
    try:
        package = backend.catalog_package(recipe)
        initially_installed = any(item.get_info() == backend.pk.InfoEnum.INSTALLED for item in backend._resolve(package))
        report = {"os": read_os_release(), "app": args.app, "package": package, "provider": backend.provider,
                  "backend": backend.control.props.backend_name,
                  "packagekitVersion": ".".join(str(getattr(backend.control.props, "version_" + key)) for key in ("major", "minor", "micro")),
                  "uidKind": "container-root" if os.geteuid() == 0 else "ordinary-user",
                  "runtimeFiles": {name: hashlib.sha256((ROOT / "src" / name).read_bytes()).hexdigest()
                                   for name in ("package_install.py", "package_provider.py", "packagekit_backend.py")},
                  "initiallyInstalled": initially_installed, "checks": [],
                  "manualPending": ["Graphical system authorization", "App fullscreen/input/return in each target distribution"]}
    finally:
        backend.close()
    if args.execute and initially_installed:
        raise RuntimeError("Execution requires an initially absent app; do not remove an existing installation")
    observed = []
    class ObservedInstaller(PackageInstaller):
        def _record_transaction(self, transaction, target):
            super()._record_transaction(transaction, target)
            if self.recovery:
                record = json.loads(self.journal.read_text())
                if record not in observed:
                    observed.append(record)
    def joined(manager):
        deadline, previous = time.monotonic() + 900, None
        while manager.worker.is_alive():
            manager.worker.join(1)
            state = manager.snapshot()
            current = (state["status"], state.get("phase"), state.get("percent"))
            if current != previous:
                print(json.dumps({"status": current[0], "phase": current[1], "percent": current[2]}), flush=True)
                previous = current
            if time.monotonic() > deadline:
                raise RuntimeError("Native package probe exceeded its wait; inspect the disposable daemon")
        return manager.snapshot()
    with tempfile.TemporaryDirectory(prefix="cozy-native-package-") as directory:
        journal = Path(directory) / "job.json"
        manager = ObservedInstaller(journal)
        try:
            manager.prepare(args.app, catalog)
            ready = joined(manager)
            report["review"] = {key: value for key, value in ready.items() if key != "confirmationToken"}
            assert ready["status"] == ("complete" if initially_installed else "ready"), ready
            assert ready["provider"] == report["provider"]
            report["checks"].append("native mapping, real daemon roles and simulation without execution")
            if not initially_installed:
                report["target"] = package_identity(manager.plan["packageIds"][0])
            if args.execute:
                manager.start(ready["jobId"], ready["confirmationToken"])
                result = joined(manager)
                if args.expect_denied:
                    assert result["status"] == "error" and result["error"] == "authorization", result
                    report["checks"].append("ordinary-user transaction denied by system authorization without a password agent")
                else:
                    assert result["status"] == "complete", result
                    assert observed, "Daemon transaction identity was not journaled"
                    assert journal.stat().st_mode & 0o777 == 0o600
                    try:
                        manager.start(ready["jobId"], ready["confirmationToken"])
                        raise AssertionError("Completed consent was replayed")
                    except InstallError as error:
                        assert error.code == "plan_changed"
                    report["checks"].append("real trusted install, exact target verification and single-use consent")
                    # Reconcile a launcher that was offline when the daemon finished.
                    recovered_journal = Path(directory) / "recovered.json"
                    recovered_journal.write_text(json.dumps(observed[-1]))
                    recovered = PackageInstaller(recovered_journal)
                    assert joined(recovered)["status"] == "complete", recovered.snapshot()
                    report["checks"].append("recorded transaction reconciled through daemon history without replay")
                    manager.prepare(args.app, catalog, "update")
                    update = joined(manager)
                    rpm = report["provider"] in {"dnf", "zypper"}
                    expected = "system_maintenance_required" if rpm else "system_update_required" if report["provider"] == "pacman" else "no_update"
                    assert update["status"] == "error" and update["error"] == expected, update
                    report["checks"].append("RPM updates delegated to system manager" if rpm else "Arch partial-update refusal" if expected == "system_update_required" else "freshly installed latest target reports no update")
                    manager.prepare(args.app, catalog, "remove")
                    removal = joined(manager)
                    if rpm:
                        assert removal["status"] == "error" and removal["error"] == "system_maintenance_required", removal
                        report["maintenanceDelegated"] = True
                        report["checks"].append("RPM removal delegated before a daemon removal transaction; app retained")
                    elif removal["status"] == "error" and removal["error"] == "changes_required":
                        report["removalBlocked"] = True
                        report["checks"].append("dependent-removal proposal refused without execution; app retained")
                    else:
                        assert removal["status"] == "ready" and removal["packages"] == [package], removal
                        manager.start(removal["jobId"], removal["confirmationToken"])
                        assert joined(manager)["status"] == "complete", manager.snapshot()
                        report["checks"].append("explicit single-target removal without autoremove or dependent removals")
                backend = PackageKitBackend()
                try:
                    present = any(item.get_info() == backend.pk.InfoEnum.INSTALLED for item in backend._resolve(package))
                    assert present == (report.get("removalBlocked", False) or report.get("maintenanceDelegated", False))
                finally:
                    backend.close()
            report["outcome"] = "passed"
        except Exception:
            report["outcome"] = "failed"
            raise
        finally:
            (args.artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "provider": report["provider"],
                      "backend": report["backend"], "checks": report["checks"]}), flush=True)


if __name__ == "__main__":
    main()
