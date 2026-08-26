import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import process_state


@unittest.skipUnless(os.name == "posix", "Linux /proc process records required")
class ProcessStateTests(unittest.TestCase):
    def test_live_record_contains_kernel_identity_and_private_permissions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "cache" / "server.pid"

            record = process_state.write_process_record(
                str(path),
                os.getpid(),
                "server",
            )

            self.assertEqual(record["pid"], os.getpid())
            self.assertGreater(record["startTime"], 0)
            self.assertTrue(process_state.owned_process_alive(str(path), "server"))
            self.assertFalse(process_state.owned_process_alive(str(path), "browser"))
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)

    def test_forged_or_reused_pid_is_never_signalled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "browser.pid"
            record = process_state.write_process_record(
                str(path),
                os.getpid(),
                "browser",
            )
            record["startTime"] += 1
            path.write_text(json.dumps(record), encoding="utf-8")

            with mock.patch.object(process_state.os, "kill") as kill:
                terminated = process_state.terminate_owned_process(
                    str(path),
                    "browser",
                    timeout=0,
                )

            self.assertFalse(terminated)
            kill.assert_not_called()
            self.assertFalse(path.exists())

    def test_owner_marker_must_match_the_process_command(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "server.pid"
            with self.assertRaisesRegex(ProcessLookupError, "owner marker"):
                process_state.write_process_record(
                    str(path),
                    os.getpid(),
                    "server",
                    marker="/definitely/not/in/the/current/command",
                )
            self.assertFalse(path.exists())

    def test_owned_child_can_be_terminated_without_pid_guessing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "browser.pid"
            child = subprocess.Popen(
                [sys.executable, "-c", "import time; time.sleep(30)"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                process_state.write_process_record(
                    str(path),
                    child.pid,
                    "browser",
                )
                self.assertTrue(
                    process_state.terminate_owned_process(
                        str(path),
                        "browser",
                        timeout=1,
                    )
                )
                child.wait(timeout=5)
                self.assertFalse(path.exists())
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)


if __name__ == "__main__":
    unittest.main()
