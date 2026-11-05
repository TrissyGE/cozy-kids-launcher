#!/usr/bin/env python3
"""Exercise the real generated workload through an isolated installed HTTP API.

Supply only the reviewed local core ZIP. This probe needs no game or BIOS files,
does not download anything, and never uses an existing family's launcher state.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import desktop_smoke as smoke


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", type=Path, default=Path("/usr/share/cozy-kids-launcher"))
    parser.add_argument("--core", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--desktop", choices=("gnome", "kde", "xfce"))
    parser.add_argument("--session", choices=("wayland", "x11"))
    args = parser.parse_args()
    if os.geteuid() == 0:
        raise RuntimeError("Run this probe as a regular user")
    if args.desktop or args.session:
        if not (args.desktop and args.session):
            raise ValueError("Specify both desktop and session")
        errors = smoke.environment_errors(args.desktop, args.session)
        if errors:
            raise RuntimeError(errors)
    root = args.runtime.resolve()
    assert (root / "package-managed").is_file(), "Use an installed or extracted package runtime"
    sys.path.insert(0, str(root))
    import retro_games
    from retro_workload import WORKLOAD_VERSION, workload_sha256
    payload = args.core.read_bytes()
    assert 0 < len(payload) <= retro_games.PS1_CORE_UPLOAD_BYTES
    args.artifacts.mkdir(parents=True, exist_ok=True)
    report = {"desktop": args.desktop or "headless", "session": args.session or "headless",
              "runtimeVersion": (root / "version").read_text().strip(),
              "runtimeFiles": {name: hashlib.sha256((root / name).read_bytes()).hexdigest()
                               for name in ("server.py", "retro_benchmark.py", "retro_benchmark_worker.py", "retro_workload.py")},
              "coreSha256": retro_games.PS1_CORE_SHA256,
              "workload": WORKLOAD_VERSION, "workloadSha256": workload_sha256(),
              "checks": [], "scope": "Generated headless workload only; no gameplay, desktop GPU, sound or controller certification"}
    with tempfile.TemporaryDirectory(prefix="cozy-benchmark-smoke-") as directory:
        home = Path(directory)
        environment = {**os.environ, "HOME": directory, "NO_PROXY": "127.0.0.1,localhost"}
        subprocess.run([sys.executable, str(root / "package_session.py"), "--initialize-only"], env=environment, check=True)
        state = home / ".local/state/cozy-kids-launcher"
        sentinel = home / ".local/share/cozy-preserved-save.srm"
        sentinel.parent.mkdir(parents=True, exist_ok=True)
        sentinel.write_bytes(b"preserved")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            environment["COZY_KIDS_PORT"] = str(listener.getsockname()[1])
        base = "http://127.0.0.1:" + environment["COZY_KIDS_PORT"]
        server = None
        def api(path, body=None, raw=False):
            data = body if raw else None if body is None else json.dumps(body).encode()
            headers = {"Content-Type": "application/octet-stream" if raw else "application/json", "Origin": base}
            with urlopen(Request(base + path, data=data, headers=headers), timeout=15) as response:
                return response.status, json.load(response)
        def start_server(log):
            process = subprocess.Popen([sys.executable, str(root / "server.py")], env=environment, stdout=log, stderr=log)
            def ready():
                if process.poll() is not None:
                    raise RuntimeError("Installed server exited")
                try:
                    return api("/api/update/status")[1].get("source") == "package-manager"
                except OSError:
                    return False
            smoke.wait_until(ready, timeout=30)
            return process
        def finished():
            job = api("/api/retro/benchmark")[1]
            return job if job["status"] not in {"running", "canceling"} else None
        try:
            with (args.artifacts / "server.log").open("w") as log:
                server = start_server(log)
                assert api("/api/retro/benchmark")[1] == {"status": "idle"}
                assert not api("/api/retro/games")[1]["ps1Runtime"]["core"]
                assert api("/api/retro/ps1-core", payload, raw=True)[0] == 200
                assert set(api("/api/retro/games")[1]["ps1Bios"].values()) == {"missing"}
                report["checks"].append("reviewed local core imported with no family BIOS or games")
                first = api("/api/retro/benchmark", {"system": "ps1"})
                assert first[0] == 202
                completed = smoke.wait_until(finished, timeout=30)
                assert completed["status"] == "complete", completed
                result = completed["result"]
                assert result["advancedFrames"] == result["videoFrames"] == 240
                assert result["distinctImages"] >= 24 and not result["desktopRenderingMeasured"]
                assert result["gameCompatibility"] == "unknown"
                report["measurement"] = result
                report["checks"].append("real core executed and validated 240 generated frames after warmup")
                row = next(row for row in api("/api/retro/device")[1]["systems"] if row["catalog"] == "retroarch")
                assert row["performanceMeasured"] and row["resultKey"] == completed["scopeKey"]
                assert row["performance"] == result
                private = state / "retro-benchmark.json"
                assert private.stat().st_mode & 0o777 == 0o600
                assert directory not in private.read_text()
                server.terminate()
                server.wait(timeout=10)
                server = start_server(log)
                assert api("/api/retro/benchmark")[1] == completed
                report["checks"].append("private result attached only to matching scope and survived server restart")
                try:
                    api("/api/retro/benchmark/clear", {"jobId": "stale"})
                    raise AssertionError("Stale job ID was accepted")
                except HTTPError as error:
                    assert error.code == 409
                assert api("/api/retro/benchmark/clear", {"jobId": completed["jobId"]})[1] == {"status": "idle"}
                assert "throughputFps" not in private.read_text() and sentinel.read_bytes() == b"preserved"
                row = next(row for row in api("/api/retro/device")[1]["systems"] if row["catalog"] == "retroarch")
                assert not row["performanceMeasured"]
                report["checks"].append("scoped result removal cleared metrics without touching unrelated saves")
                job = api("/api/retro/benchmark", {"system": "ps1"})[1]
                api("/api/retro/benchmark/cancel", {"jobId": job["jobId"]})
                canceled = smoke.wait_until(finished, timeout=10)
                assert canceled["status"] == "canceled" and "result" not in canceled, canceled
                api("/api/retro/benchmark/clear", {"jobId": job["jobId"]})
                assert sentinel.read_bytes() == b"preserved"
                assert not (state / "ps1-bios").exists()
                report["checks"].append("real worker canceled by job ID with no accepted measurement")
                report["outcome"] = "passed"
        except Exception:
            report["outcome"] = "failed"
            raise
        finally:
            if server is not None and server.poll() is None:
                server.terminate()
                server.wait(timeout=10)
            (args.artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"outcome": report["outcome"], "desktop": report["desktop"],
                      "checks": report["checks"], "throughputFps": report["measurement"]["throughputFps"],
                      "p95FrameMs": report["measurement"]["p95FrameMs"]}), flush=True)


if __name__ == "__main__":
    main()
