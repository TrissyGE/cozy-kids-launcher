import copy
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import retro_benchmark as benchmark
import retro_device
import retro_games
import retro_workload


def worker_result():
    return {"workload": retro_workload.WORKLOAD_VERSION, "workloadSha256": retro_workload.workload_sha256(),
            "coreSha256": retro_games.PS1_CORE_SHA256, "coreLibraryVersion": "r26 7b0e8f8",
            "frames": 240, "warmupFrames": 60, "videoFrames": 240, "advancedFrames": 240,
            "distinctImages": 31, "targetFps": 60.0, "elapsedMs": 242.0, "frameTimesMs": [1.0] * 240,
            "videoModes": [[320, 240, 2]],
            "options": {"pcsx_rearmed_bios": "HLE", "pcsx_rearmed_region": "NTSC",
                        "pcsx_rearmed_drc": "enabled", "pcsx_rearmed_frameskip_type": "disabled"}}


class BenchmarkResultTests(unittest.TestCase):
    def test_generated_content_is_deterministic_and_has_a_bounded_executable_layout(self):
        payload = retro_workload.generated_ps1_exe()
        self.assertEqual(payload[:8], b"PS-X EXE")
        self.assertEqual(len(payload), 12288)
        entry, gp, text, size = struct.unpack_from("<IIII", payload, 0x10)
        self.assertEqual((entry, gp, text, size), (0x80010000, 0, 0x80010000, len(payload) - 2048))
        self.assertEqual(hashlib.sha256(payload).hexdigest(), "129ed607f7d4680820e72d7f529f4b54fc4257fb18aa717c3bb59a33ddac0e8f")
        self.assertEqual(payload, retro_workload.generated_ps1_exe())

    def test_result_requires_real_workload_progress_and_retains_its_narrow_scope(self):
        result = benchmark.summarize_worker(worker_result())
        self.assertEqual(result["status"], "within-budget")
        self.assertEqual(result["p95FrameMs"], 1)
        self.assertFalse(result["desktopRenderingMeasured"])
        self.assertEqual(result["gameCompatibility"], "unknown")
        self.assertNotIn("frameTimesMs", result)
        limited = worker_result()
        limited.update(elapsedMs=7200, frameTimesMs=[30.] * 240)
        self.assertEqual(benchmark.summarize_worker(limited)["status"], "limited")
        invalid = [("advancedFrames", 0), ("videoFrames", 0), ("distinctImages", 1),
                   ("coreSha256", "unreviewed"), ("workloadSha256", "other-content"),
                   ("elapsedMs", float("nan")), ("frameTimesMs", [float("inf")] * 240),
                   ("videoModes", [[1920, 1080, 1]]), ("frameTimesMs", [1.0] * 239)]
        for key, value in invalid:
            with self.subTest(key=key):
                data = worker_result()
                data[key] = value
                with self.assertRaises(ValueError):
                    benchmark.summarize_worker(data)

    def test_saved_results_reject_arbitrary_fields_and_changed_core_or_settings(self):
        result = benchmark.summarize_worker(worker_result())
        self.assertEqual(benchmark._stored_result(result), result)
        for field, value in (("extra", "/home/private/data"), ("coreSha256", "0" * 64),
                             ("throughputFps", 0), ("coreLibraryVersion", "/private/path")):
            with self.subTest(field=field):
                changed = {**result, field: value}
                self.assertIsNone(benchmark._stored_result(changed))
        changed = copy.deepcopy(result)
        changed["settings"]["bios"] = "/private/BIOS"
        self.assertIsNone(benchmark._stored_result(changed))

    def test_measurement_only_attaches_to_the_current_device_package_and_core_scope(self):
        report = {"systems": [{"catalog": "retroarch", "resultKey": "a" * 24,
                                "status": "untested", "performanceMeasured": False}]}
        job = {"status": "complete", "scopeKey": "a" * 24, "result": benchmark.summarize_worker(worker_result())}
        measured = benchmark.attach_benchmark(copy.deepcopy(report), job)
        self.assertTrue(measured["systems"][0]["performanceMeasured"])
        self.assertEqual(measured["systems"][0]["status"], "measured")
        job["scopeKey"] = "b" * 24
        self.assertEqual(benchmark.attach_benchmark(copy.deepcopy(report), job), report)
        job["scopeKey"] = "a" * 24
        job["result"]["coreSha256"] = "0" * 64
        self.assertEqual(benchmark.attach_benchmark(copy.deepcopy(report), job), report)

    def test_device_fingerprint_ignores_free_memory_display_and_uuid_noise_but_tracks_driver_changes(self):
        first = "display: :0\nOpenGL renderer string: Test GPU\nOpenGL version string: 4.6 Mesa 1\nAvailable memory: 1000 MB\n"
        second = first.replace(":0", ":1").replace("1000 MB", "900 MB")
        vk1 = "deviceName = Test GPU\ndriverInfo = Driver 1\ndeviceUUID = a\n"
        vk2 = vk1.replace("UUID = a", "UUID = b")
        self.assertEqual(retro_device._graphics_identity(first, vk1), retro_device._graphics_identity(second, vk2))
        self.assertNotEqual(retro_device._graphics_identity(first, vk1), retro_device._graphics_identity(first.replace("Mesa 1", "Mesa 2"), vk1))


@unittest.skipUnless(sys.platform == "linux", "Linux process-group and private-mode integration")
class BenchmarkJobTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.manager = benchmark.RetroBenchmark(self.root / "state/result.json")
        self.addCleanup(self.manager.close)
        self.core = patch.object(retro_games, "load_ps1_core_payload", return_value=b"reviewed fixture")
        self.core.start()
        self.addCleanup(self.core.stop)

    def command(self, source):
        return patch.object(self.manager, "_command", return_value=[sys.executable, "-c", source])

    def wait_process(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if self.manager.process is not None:
                return self.manager.process
            time.sleep(.01)
        self.fail("Worker process did not start")

    def join(self):
        self.manager.worker.join(timeout=5)
        self.assertFalse(self.manager.worker.is_alive())
        return self.manager.snapshot()

    def test_real_subprocess_completion_private_restart_and_result_removal_preserve_other_state(self):
        sentinel = self.root / "unrelated-save.srm"
        sentinel.write_bytes(b"preserved")
        with self.command("print(" + repr(json.dumps(worker_result())) + ")"):
            job = self.manager.start(self.root, "a" * 24)
            state = self.join()
        self.assertEqual(state["status"], "complete")
        self.assertEqual(self.manager.path.stat().st_mode & 0o777, 0o600)
        self.assertLess(self.manager.path.stat().st_size, benchmark.MAX_RESULT_BYTES)
        restored = benchmark.RetroBenchmark(self.manager.path)
        self.assertEqual(restored.snapshot(), state)
        with self.assertRaises(benchmark.BenchmarkError):
            restored.clear("stale-job")
        self.assertEqual(restored.clear(job["jobId"]), {"status": "idle"})
        self.assertNotIn("throughputFps", self.manager.path.read_text())
        self.assertEqual(sentinel.read_bytes(), b"preserved")

    def test_concurrent_and_stale_requests_cannot_replace_or_cancel_a_running_job(self):
        with self.command("import time; time.sleep(60)"):
            job = self.manager.start(self.root, "a" * 24)
            process = self.wait_process()
            with self.assertRaises(benchmark.BenchmarkError) as busy:
                self.manager.start(self.root, "b" * 24)
            self.assertEqual(busy.exception.code, "busy")
            with self.assertRaises(benchmark.BenchmarkError):
                self.manager.cancel("stale-job")
            self.assertIsNone(process.poll())
            self.manager.cancel(job["jobId"])
            state = self.join()
        self.assertEqual((state["status"], state["error"]), ("canceled", "canceled"))
        self.assertNotIn("result", state)
        self.assertIsNotNone(process.returncode)

    def test_wall_limit_kills_the_owned_process_group_and_rejects_unvalidated_output(self):
        child_file = self.root / "child.pid"
        source = ("import os,time,pathlib; child=os.fork(); "
                  f"pathlib.Path({str(child_file)!r}).write_text(str(child)) if child else None; time.sleep(60)")
        with self.command(source), patch.object(benchmark, "TIMEOUT_SECONDS", 1):
            self.manager.start(self.root, "a" * 24)
            state = self.join()
        self.assertEqual(state["error"], "timeout")
        child = int(child_file.read_text())
        info = Path(f"/proc/{child}/stat")
        if info.exists():
            text = info.read_text()
            self.assertEqual(text[text.rfind(")") + 2:].split()[0], "Z")
        with self.command("print('not JSON')"):
            self.manager.start(self.root, "a" * 24)
            state = self.join()
        self.assertEqual(state["error"], "failed")

    def test_crashed_server_state_is_interrupted_without_replaying_the_worker(self):
        job = {"jobId": "a" * 16, "scopeKey": "b" * 24, "startedAt": "2026-11-05T10:00:00+00:00", "status": "running"}
        self.manager.path.parent.mkdir(parents=True, exist_ok=True)
        self.manager.path.write_text(json.dumps({"format": 1, "job": job}))
        restored = benchmark.RetroBenchmark(self.manager.path)
        self.assertEqual((restored.snapshot()["status"], restored.snapshot()["error"]), ("error", "interrupted"))
        self.assertIsNone(restored.worker)

    def test_failed_private_write_does_not_create_a_phantom_job_or_claim_removal(self):
        with patch.object(self.manager, "_save", side_effect=OSError("state unavailable")):
            with self.assertRaises(OSError):
                self.manager.start(self.root, "a" * 24)
        self.assertEqual(self.manager.snapshot(), {"status": "idle"})
        self.assertIsNone(self.manager.worker)
        with patch.object(benchmark.threading.Thread, "start", side_effect=RuntimeError("no threads")):
            with self.assertRaises(benchmark.BenchmarkError):
                self.manager.start(self.root, "a" * 24)
        self.assertEqual(self.manager.snapshot(), {"status": "idle"})
        self.assertIsNone(self.manager.worker)
        with self.command("print(" + repr(json.dumps(worker_result())) + ")"):
            job = self.manager.start(self.root, "a" * 24)
            completed = self.join()
        with patch.object(self.manager, "_save", side_effect=OSError("state unavailable")):
            with self.assertRaises(OSError):
                self.manager.clear(job["jobId"])
        self.assertEqual(self.manager.snapshot(), completed)
        self.assertEqual(benchmark.RetroBenchmark(self.manager.path).snapshot(), completed)

    def test_closed_manager_refuses_late_start_requests(self):
        self.manager.close()
        with self.assertRaises(benchmark.BenchmarkError) as error:
            self.manager.start(self.root, "a" * 24)
        self.assertEqual(error.exception.code, "unavailable")
        self.assertIsNone(self.manager.worker)

    def test_parent_death_stops_the_resource_limited_worker(self):
        ready = self.root / "worker.pid"
        source_root = str(Path(benchmark.__file__).parent)
        child = (f"import sys,os,pathlib,time; sys.path.insert(0,{source_root!r}); "
                 "from retro_benchmark_worker import limits; limits(os.getppid()); "
                 f"pathlib.Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)")
        parent = subprocess.Popen([sys.executable, "-c",
                                   "import subprocess,sys; subprocess.Popen([sys.executable,'-c'," + repr(child) + "]).wait()"],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        worker_pid, worker_identity = None, None
        try:
            deadline = time.monotonic() + 4
            while not ready.exists() and time.monotonic() < deadline:
                self.assertIsNone(parent.poll())
                time.sleep(.01)
            worker_pid = int(ready.read_text())
            identity = Path(f"/proc/{worker_pid}/stat").read_text()
            worker_identity = identity[identity.rfind(")") + 2:].split()[19]
            parent.kill()
            parent.wait(timeout=2)
            info = Path(f"/proc/{worker_pid}/stat")
            deadline = time.monotonic() + 2
            while info.exists() and time.monotonic() < deadline:
                text = info.read_text()
                if text[text.rfind(")") + 2:].split()[0] == "Z":
                    break
                time.sleep(.01)
            else:
                self.assertFalse(info.exists(), "Benchmark child survived its server")
        finally:
            if parent.poll() is None:
                parent.kill()
                parent.wait(timeout=2)
            if worker_pid:
                try:
                    identity = Path(f"/proc/{worker_pid}/stat").read_text()
                    fields = identity[identity.rfind(")") + 2:].split()
                    if fields[0] != "Z" and fields[19] == worker_identity:
                        os.kill(worker_pid, 9)
                except (OSError, ProcessLookupError):
                    pass


if __name__ == "__main__":
    unittest.main()
