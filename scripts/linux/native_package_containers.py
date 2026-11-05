#!/usr/bin/env python3
"""Run real catalog probes in disposable upstream images, without host home mounts."""

import argparse
import json
from pathlib import Path
import secrets
import subprocess


ROOT = Path(__file__).resolve().parents[2]
FAMILIES = {
    "fedora": {"image": "registry.fedoraproject.org/fedora:44", "app": "kgeography", "setup": [
        ["dnf", "-y", "--setopt=install_weak_deps=False", "install", "PackageKit", "PackageKit-glib",
         "python3-gobject-base", "dbus-daemon", "polkit", "util-linux", "shadow-utils", "qt6-qtbase-gui"]]},
    "arch": {"image": "docker.io/library/archlinux:base", "app": "kolourpaint", "setup": [
        ["pacman", "-Syu", "--noconfirm", "--needed", "packagekit", "python-gobject", "dbus", "polkit", "qt6-base"]]},
    "opensuse": {"image": "docker.io/opensuse/tumbleweed:latest", "app": "kgeography", "setup": [
        ["zypper", "--non-interactive", "install", "--no-recommends", "PackageKit", "PackageKit-backend-zypp",
         "typelib-1_0-PackageKitGlib-1_0", "python3-gobject", "dbus-1-daemon", "dbus-1-tools", "polkit", "libQt6Widgets6", "shadow", "util-linux"]]},
}
SOURCE_FILES = ("package_install.py", "package_provider.py", "packagekit_backend.py", "config_store.py", "profile_config.py", "recommendations.json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine", choices=("docker", "podman"), default="docker")
    parser.add_argument("--family", choices=tuple(FAMILIES), required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--execute", action="store_true", help="Also install/remove the app and verify ordinary-user authorization refusal inside the test container")
    args = parser.parse_args()
    family = FAMILIES[args.family]
    args.artifacts.mkdir(parents=True, exist_ok=True)
    name = "cozy-native-" + args.family + "-" + secrets.token_hex(5)
    started = False
    report = {"family": args.family, "image": family["image"], "app": family["app"], "executionRequested": args.execute}
    def run(*values, **options):
        print("Container action:", " ".join(values[:3]), flush=True)
        return subprocess.run([args.engine, *values], check=True, **options)
    try:
        run("pull", family["image"])
        metadata = json.loads(run("image", "inspect", family["image"], capture_output=True, text=True).stdout)[0]
        report["imageId"] = metadata["Id"]
        report["imageDigests"] = metadata.get("RepoDigests", [])
        run("run", "-d", "--init", "--name", name, "--label", "io.cozy-kids.test=native-catalog",
            "--memory", "2g", "--pids-limit", "2048", "--tmpfs", "/run", family["image"], "sleep", "infinity")
        started = True
        for command in family["setup"]:
            run("exec", name, *command)
        run("exec", name, "mkdir", "-p", "/workspace/src", "/workspace/scripts/linux", "/evidence")
        run("exec", name, "chmod", "1777", "/evidence")
        for file in SOURCE_FILES:
            run("cp", str(ROOT / "src" / file), name + ":/workspace/src/" + file)
        probe = "/workspace/scripts/linux/native_package_probe.py"
        run("cp", str(ROOT / "scripts/linux/native_package_probe.py"), name + ":" + probe)
        run("exec", name, "python3", probe, "--app", family["app"], "--bootstrap-container", "--bootstrap-only", "--artifacts", "/evidence/bootstrap")
        if args.execute:
            run("exec", name, "useradd", "--create-home", "cozyprobe")
            run("exec", name, "runuser", "-u", "cozyprobe", "--", "python3", probe, "--app", family["app"],
                "--execute", "--expect-denied", "--artifacts", "/evidence/ordinary")
        command = ["python3", probe, "--app", family["app"], "--artifacts", "/evidence/root"]
        if args.execute:
            command.append("--execute")
        run("exec", name, *command)
        if args.execute:
            root_report = json.loads(run("exec", name, "cat", "/evidence/root/report.json", capture_output=True, text=True).stdout)
            if root_report.get("outcome") != "passed" or root_report.get("removalBlocked"):
                raise RuntimeError("The native policy probe did not complete")
            if bool(root_report.get("maintenanceDelegated")) != (args.family in {"fedora", "opensuse"}):
                raise RuntimeError("The RPM maintenance boundary was not observed")
        report["outcome"] = "passed"
    except Exception:
        report["outcome"] = "failed"
        raise
    finally:
        (args.artifacts / "container.json").write_text(json.dumps(report, indent=2) + "\n")
        if started:
            try:
                run("cp", name + ":/evidence/.", str(args.artifacts))
            finally:
                # Never prune an engine or remove an unrelated user's container.
                run("rm", "--force", name)


if __name__ == "__main__":
    main()
