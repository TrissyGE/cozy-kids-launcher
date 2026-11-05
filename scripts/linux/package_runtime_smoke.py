#!/usr/bin/env python3
"""Check the installed package's private first start and real local HTTP API."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen


def main():
    root = Path("/usr/share/cozy-kids-launcher")
    if os.geteuid() == 0:
        raise RuntimeError("Run this probe as an ordinary user after package installation")
    assert not os.access(root, os.W_OK)
    assert (root / "package-managed").is_file()
    with tempfile.TemporaryDirectory(prefix="cozy-deb-runtime-") as directory:
        home = Path(directory)
        config = home / ".config/cozy-kids-launcher/config.json"
        environment = {**os.environ, "HOME": directory, "LANG": "it_IT.UTF-8", "NO_PROXY": "127.0.0.1,localhost"}
        subprocess.run(["/usr/bin/cozy-kids-launcher", "--initialize-only"], env=environment, check=True)
        data = json.loads(config.read_text())
        assert data["language"] == "it"
        assert config.stat().st_mode & 0o777 == 0o600
        initial = config.read_bytes()
        subprocess.run(["/usr/bin/cozy-kids-launcher", "--initialize-only"], env=environment, check=True)
        assert config.read_bytes() == initial
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        environment["COZY_KIDS_PORT"] = str(port)
        base = f"http://127.0.0.1:{port}"
        def api(path, body=None):
            payload = None if body is None else json.dumps(body).encode()
            with urlopen(Request(base + path, data=payload, headers={"Content-Type": "application/json"}), timeout=10) as response:
                return json.load(response)
        with tempfile.TemporaryFile() as log:
            server = subprocess.Popen(["python3", str(root / "server.py")], env=environment, stdout=log, stderr=log)
            try:
                for _ in range(100):
                    try:
                        assert api("/api/update/status")["source"] == "package-manager"
                        break
                    except OSError:
                        if server.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(log.read().decode())
                        time.sleep(0.1)
                else:
                    raise RuntimeError("Installed server did not become ready")
                with urlopen(base + "/index.html", timeout=10) as response:
                    assert b"Cozy" in response.read()
                with urlopen(base + "/frontend/locales/it.json", timeout=10) as response:
                    assert json.load(response)["adminTitle"]
                sys.path.insert(0, str(root))
                from backup_store import create_pre_restore_backup
                backup = create_pre_restore_backup(str(home / ".local/share/cozy-kids-launcher-backups"), json.loads(config.read_text()))
                changed = json.loads(config.read_text())
                changed["profiles"][0]["name"] = "Changed after backup"
                config.write_text(json.dumps(changed))
                assert api("/api/backups/restore", {"backupId": backup["id"]})["status"] == "ok"
                assert json.loads(config.read_text())["profiles"][0]["name"] == data["profiles"][0]["name"]
            finally:
                server.terminate()
                server.wait(timeout=15)
    print("Installed package first start, private state, static assets, update owner and configuration restore passed")


if __name__ == "__main__":
    main()
