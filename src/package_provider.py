"""Prepare allowlisted native-package instructions; never execute a transaction."""

from pathlib import Path
import re
import shlex
import shutil


PROVIDERS = {
    "apt": ("apt", "install", "--no-remove"),
    "dnf": ("dnf", "install"),
    "pacman": ("pacman", "-S"),
    "zypper": ("zypper", "install"),
}
OS_PROVIDERS = {
    "debian": "apt", "ubuntu": "apt", "linuxmint": "apt", "zorin": "apt",
    "fedora": "dnf", "rhel": "dnf", "centos": "dnf",
    "arch": "pacman", "manjaro": "pacman",
    "opensuse": "zypper", "opensuse-tumbleweed": "zypper",
    "opensuse-leap": "zypper", "suse": "zypper", "sles": "zypper",
}
IMMUTABLE_VARIANTS = {"silverblue", "kinoite", "sericea", "onyx", "coreos", "aeon", "kalpa", "microos"}
PACKAGE_NAME = re.compile(r"[a-z0-9](?:[a-z0-9+.-]{0,126}[a-z0-9])?")


def read_os_release(paths=("/etc/os-release", "/usr/lib/os-release")):
    """Read only identification fields, including on supported Python 3.9."""
    for path in paths:
        try:
            with open(path, encoding="utf-8") as handle:
                contents = handle.read(16385)
        except OSError:
            continue
        except UnicodeError:
            return {}
        if len(contents) > 16384:
            return {}
        result = {}
        for line in contents.splitlines():
            key, separator, value = line.partition("=")
            if not separator or key not in ("ID", "ID_LIKE", "VARIANT_ID"):
                continue
            try:
                words = shlex.split(value, comments=True)
            except ValueError:
                return {}
            if len(words) != 1:
                return {}
            result[key] = words[0]
        return result
    return {}


def detect_native_provider(os_release=None, which=None, immutable=None):
    release = read_os_release() if os_release is None else os_release
    executable = shutil.which if which is None else which
    if immutable is None:
        immutable = Path("/run/ostree-booted").exists()
    if immutable or release.get("VARIANT_ID", "").lower() in IMMUTABLE_VARIANTS:
        return None
    identifiers = [release.get("ID", ""), *release.get("ID_LIKE", "").split()]
    for identifier in identifiers:
        provider = OS_PROVIDERS.get(identifier.lower())
        if provider:
            # Do not choose another distribution's tool merely because it is installed.
            return provider if executable(PROVIDERS[provider][0]) else None
    return None


def prepare_install(package, recommendations, *, provider=None):
    if not isinstance(package, str) or not PACKAGE_NAME.fullmatch(package):
        raise ValueError("Invalid package")
    recommendation = next(
        (item for item in recommendations if item.get("package") == package), None
    )
    if recommendation is None:
        raise ValueError("Invalid package")
    provider = detect_native_provider() if provider is None else provider
    if provider not in PROVIDERS:
        return {"status": "unsupported", "reason": "provider_unavailable"}
    # The legacy catalog's package field contains Debian names only.
    packages = recommendation.get("packages", {})
    if not isinstance(packages, dict):
        raise ValueError("Invalid package mapping")
    native_package = packages.get(provider, package if provider == "apt" else None)
    if native_package is None:
        return {"status": "unsupported", "provider": provider, "reason": "package_unmapped"}
    if not isinstance(native_package, str) or not PACKAGE_NAME.fullmatch(native_package):
        raise ValueError("Invalid package mapping")
    argv = ["sudo", *PROVIDERS[provider], native_package]
    return {
        "status": "manual", "provider": provider,
        "argv": argv, "command": shlex.join(argv),
    }
