import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import threading
import unittest
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
UPDATE_SCRIPT = REPOSITORY_ROOT / "scripts" / "update.sh"
BASH = shutil.which("bash")


FAKE_INSTALLER = b"""#!/usr/bin/env bash
set -euo pipefail
source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
target_home="$HOME"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --home) target_home="$2"; shift 2 ;;
    --user|--lang|--browser|--launch-mode) shift 2 ;;
    *) shift ;;
  esac
done
mkdir -p "$target_home/.local/share/cozy-kids-launcher"
mkdir -p "$target_home/.config/cozy-kids-launcher"
cp "$source_root/VERSION" "$target_home/.local/share/cozy-kids-launcher/version"
printf '%s\n' '{"language":"overwritten"}' > "$target_home/.config/cozy-kids-launcher/config.json"
if [[ "${COZY_KIDS_TEST_INSTALL_FAIL:-0}" == "1" ]]; then
  printf '%s\n' 'partial install' > "$target_home/.local/share/cozy-kids-launcher/partial"
  exit 42
fi
"""


def make_release_archive(version):
    root = f"cozy-kids-launcher-{version}"
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        for name, payload, mode in (
            (f"{root}/VERSION", f"{version}\n".encode(), 0o644),
            (f"{root}/scripts/install.sh", FAKE_INSTALLER, 0o755),
        ):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            info.mode = mode
            archive.addfile(info, io.BytesIO(payload))
    return output.getvalue()


def make_legacy_archive(version):
    output = io.BytesIO()
    with zipfile.ZipFile(output, mode="w") as archive:
        archive.writestr("cozy-kids-launcher-main/VERSION", f"{version}\n")
        installer = zipfile.ZipInfo("cozy-kids-launcher-main/scripts/install.sh")
        installer.external_attr = 0o755 << 16
        archive.writestr(installer, FAKE_INSTALLER)
    return output.getvalue()


class UpdateFixture:
    def __init__(self, release_version="0.4.0", legacy_version="0.3.5"):
        self.release_version = release_version
        self.legacy_version = legacy_version
        self.release_enabled = True
        self.valid_checksum = True
        self.release_archive = make_release_archive(release_version)
        self.legacy_archive = make_legacy_archive(legacy_version)
        self.server = None
        self.thread = None

    def start(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def send_payload(self, status, payload, content_type="application/octet-stream"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self):
                base_url = f"http://127.0.0.1:{self.server.server_address[1]}"
                if self.path == "/releases/latest":
                    if not fixture.release_enabled:
                        self.send_payload(404, b"not found", "text/plain")
                        return
                    version = fixture.release_version
                    body = {
                        "tag_name": f"v{version}",
                        "draft": False,
                        "prerelease": False,
                        "assets": [
                            {
                                "name": f"cozy-kids-launcher-{version}.tar.gz",
                                "browser_download_url": f"{base_url}/release.tar.gz",
                            },
                            {
                                "name": "SHA256SUMS",
                                "browser_download_url": f"{base_url}/SHA256SUMS",
                            },
                        ],
                    }
                    self.send_payload(200, json.dumps(body).encode(), "application/json")
                    return
                if self.path == "/release.tar.gz":
                    self.send_payload(200, fixture.release_archive)
                    return
                if self.path == "/SHA256SUMS":
                    digest = hashlib.sha256(fixture.release_archive).hexdigest()
                    if not fixture.valid_checksum:
                        digest = "0" * 64
                    name = f"cozy-kids-launcher-{fixture.release_version}.tar.gz"
                    self.send_payload(200, f"{digest}  {name}\n".encode(), "text/plain")
                    return
                if self.path == "/VERSION":
                    self.send_payload(200, f"{fixture.legacy_version}\n".encode(), "text/plain")
                    return
                if self.path == "/main.zip":
                    self.send_payload(200, fixture.legacy_archive)
                    return
                self.send_payload(404, b"not found", "text/plain")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return f"http://127.0.0.1:{self.server.server_address[1]}"

    def stop(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


@unittest.skipUnless(os.name == "posix" and BASH, "requires a POSIX bash environment")
class UpdateScriptIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home = Path(self.temp_dir.name) / "home"
        self.app_root = self.home / ".local" / "share" / "cozy-kids-launcher"
        self.config_file = self.home / ".config" / "cozy-kids-launcher" / "config.json"
        self.app_root.mkdir(parents=True)
        self.config_file.parent.mkdir(parents=True)
        (self.app_root / "version").write_text("0.3.4\n", encoding="utf-8")
        self.original_config = '{"language":"de","title":"Bleibt erhalten"}\n'
        self.config_file.write_text(self.original_config, encoding="utf-8")
        self.fixture = UpdateFixture()
        self.base_url = self.fixture.start()
        self.extra_environment = {}

    def tearDown(self):
        self.fixture.stop()
        self.temp_dir.cleanup()

    def run_updater(self, *arguments):
        environment = dict(os.environ)
        environment.update({
            "HOME": str(self.home),
            "COZY_KIDS_RELEASE_API_URL": f"{self.base_url}/releases/latest",
            "COZY_KIDS_RAW_URL": self.base_url,
            "COZY_KIDS_MAIN_ARCHIVE_URL": f"{self.base_url}/main.zip",
        })
        environment.update(self.extra_environment)
        return subprocess.run(
            [BASH, str(UPDATE_SCRIPT), *arguments],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )

    def installed_version(self):
        return (self.app_root / "version").read_text(encoding="utf-8").strip()

    def test_verified_release_updates_and_preserves_configuration(self):
        result = self.run_updater()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("SHA-256 checksum verified", result.stdout)
        self.assertEqual(self.installed_version(), "0.4.0")
        self.assertEqual(self.config_file.read_text(encoding="utf-8"), self.original_config)
        self.assertEqual((self.app_root / "update-channel").read_text().strip(), "release")

    def test_checksum_mismatch_cannot_replace_the_installation(self):
        self.fixture.valid_checksum = False
        result = self.run_updater()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("checksum verification failed", result.stdout)
        self.assertEqual(self.installed_version(), "0.3.4")
        self.assertEqual(self.config_file.read_text(encoding="utf-8"), self.original_config)

    def test_failed_installer_rolls_back_all_partially_written_app_files(self):
        original_marker = self.app_root / "original-marker"
        original_marker.write_text("keep me\n", encoding="utf-8")
        self.extra_environment["COZY_KIDS_TEST_INSTALL_FAIL"] = "1"

        result = self.run_updater()

        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("restoring the previous installation", result.stdout)
        self.assertEqual(self.installed_version(), "0.3.4")
        self.assertEqual(original_marker.read_text(encoding="utf-8"), "keep me\n")
        self.assertFalse((self.app_root / "partial").exists())
        self.assertEqual(self.config_file.read_text(encoding="utf-8"), self.original_config)

    def test_legacy_main_fallback_keeps_existing_updaters_compatible(self):
        self.fixture.release_enabled = False
        result = self.run_updater()
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("updater-compatible main/VERSION fallback", result.stdout)
        self.assertEqual(self.installed_version(), "0.3.5")
        self.assertFalse((self.app_root / "update-channel").exists())

    def test_release_channel_fails_closed_unless_legacy_is_explicit(self):
        self.fixture.release_enabled = False
        self.fixture.legacy_version = "0.4.1"
        self.fixture.legacy_archive = make_legacy_archive("0.4.1")
        (self.app_root / "version").write_text("0.4.0\n", encoding="utf-8")
        (self.app_root / "update-channel").write_text("release\n", encoding="utf-8")

        refused = self.run_updater()
        self.assertNotEqual(refused.returncode, 0, refused.stdout)
        self.assertIn("mutable main fallback is disabled", refused.stdout)
        self.assertEqual(self.installed_version(), "0.4.0")

        explicit = self.run_updater("--legacy-main")
        self.assertEqual(explicit.returncode, 0, explicit.stdout)
        self.assertEqual(self.installed_version(), "0.4.1")
        self.assertEqual((self.app_root / "update-channel").read_text().strip(), "release")


if __name__ == "__main__":
    unittest.main()
