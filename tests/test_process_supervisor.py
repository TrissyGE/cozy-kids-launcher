import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import process_state
import process_supervisor
import activity_store


def wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.05)
    return None


class OwnershipSourceTests(unittest.TestCase):
    def test_overlay_and_server_never_guess_processes_by_command_name(self):
        overlay = (SOURCE_ROOT / "overlay.py").read_text(encoding="utf-8")
        server = (SOURCE_ROOT / "server.py").read_text(encoding="utf-8")

        self.assertNotIn("pgrep", overlay)
        self.assertNotIn("pgrep", server)
        self.assertNotIn("getactivewindow", overlay)
        self.assertIn("TILE_PROCESS_PIDFILE", overlay)
        self.assertIn("launch_owned_tile", server)


@unittest.skipUnless(os.name == "posix", "Linux process supervision required")
class ProcessSupervisorTests(unittest.TestCase):
    def test_termination_follows_forks_without_touching_same_command_elsewhere(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            record_path = root / "tile-process.pid"
            child_info_path = root / "children.json"
            child_script = root / "forking-app.py"
            child_script.write_text(
                "import json, os, signal, subprocess, sys\n"
                "grandchild = subprocess.Popen([\n"
                "    sys.executable, '-c',\n"
                "    'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)',\n"
                "])\n"
                "with open(sys.argv[1], 'w', encoding='utf-8') as handle:\n"
                "    json.dump({'parent': os.getpid(), 'grandchild': grandchild.pid}, handle)\n",
                encoding="utf-8",
            )
            unrelated = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    "import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(30)",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            supervisor = subprocess.Popen(
                [
                    sys.executable,
                    str(SOURCE_ROOT / "process_supervisor.py"),
                    "--record",
                    str(record_path),
                    "--marker",
                    str(SOURCE_ROOT / "process_supervisor.py"),
                    "--",
                    sys.executable,
                    str(child_script),
                    str(child_info_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            child_identities = {}
            try:
                record = wait_until(
                    lambda: process_state.owned_process(
                        str(record_path),
                        "tile-process",
                        str(SOURCE_ROOT / "process_supervisor.py"),
                    )
                )
                self.assertIsNotNone(record)
                self.assertTrue(wait_until(child_info_path.is_file))
                child_info = json.loads(child_info_path.read_text(encoding="utf-8"))
                child_identities = {
                    pid: process_state.process_start_time(pid)
                    for pid in child_info.values()
                }
                grandchild_start = process_state.process_start_time(
                    child_info["grandchild"]
                )
                unrelated_start = process_state.process_start_time(unrelated.pid)

                owned = wait_until(
                    lambda: child_info["grandchild"]
                    in process_supervisor.owned_processes(supervisor.pid)
                )
                self.assertTrue(owned)
                self.assertTrue(
                    process_state.terminate_owned_process(
                        str(record_path),
                        "tile-process",
                        str(SOURCE_ROOT / "process_supervisor.py"),
                        timeout=3,
                    )
                )
                supervisor.wait(timeout=5)

                self.assertNotEqual(
                    process_state.process_start_time(child_info["grandchild"]),
                    grandchild_start,
                )
                self.assertEqual(
                    process_state.process_start_time(unrelated.pid),
                    unrelated_start,
                )
                self.assertFalse(record_path.exists())
            finally:
                if supervisor.poll() is None:
                    supervisor.terminate()
                    try:
                        supervisor.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        supervisor.kill()
                        supervisor.wait(timeout=5)
                for pid, start_time in child_identities.items():
                    if process_state.process_start_time(pid) == start_time:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                if unrelated.poll() is None:
                    unrelated.kill()
                unrelated.wait(timeout=5)

    def test_supervisor_removes_record_after_a_normal_exit(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            record_path = Path(temp_dir) / "tile-process.pid"
            activity_path = Path(temp_dir) / "activity.json"
            supervisor = subprocess.Popen(
                [
                    sys.executable,
                    str(SOURCE_ROOT / "process_supervisor.py"),
                    "--record",
                    str(record_path),
                    "--marker",
                    str(SOURCE_ROOT / "process_supervisor.py"),
                    "--activity-file",
                    str(activity_path),
                    "--activity-profile",
                    "default",
                    "--activity-tile",
                    "paint",
                    "--",
                    sys.executable,
                    "-c",
                    "pass",
                ],
                start_new_session=True,
            )

            self.assertEqual(supervisor.wait(timeout=5), 0)
            self.assertFalse(record_path.exists())
            records = activity_store.read_activity(activity_path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]["profileId"], "default")
            self.assertEqual(records[0]["tileId"], "paint")


if __name__ == "__main__":
    unittest.main()
