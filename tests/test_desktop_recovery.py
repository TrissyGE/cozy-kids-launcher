import json
from pathlib import Path
import signal
import sys
import tempfile
import types
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts/linux"))
sys.path.insert(0, str(ROOT / "src"))
import app_display
import desktop_recovery
import process_state


class DesktopRecoveryProbeTests(unittest.TestCase):
    def test_failed_fault_observation_resumes_only_fixture_supervisor(self):
        display = mock.Mock()
        with mock.patch.object(app_display, "X11Fullscreen", return_value=display), \
                mock.patch.object(process_state, "process_start_time", return_value=456), \
                mock.patch.object(desktop_recovery.smoke, "wait_until", side_effect=[1000, TimeoutError("observation")]), \
                mock.patch.object(desktop_recovery.subprocess, "run"), \
                mock.patch.object(desktop_recovery.os, "kill") as kill:
            with self.assertRaisesRegex(TimeoutError, "observation"):
                desktop_recovery.recover_fullscreen(123)
        self.assertEqual(kill.call_args_list, [mock.call(123, signal.SIGSTOP), mock.call(123, signal.SIGCONT)])
        display.close.assert_called_once()

    def test_failed_resize_restores_original_output_and_keeps_evidence(self):
        layout = "Screen 0: current 1280 x 800\nVirtual1 connected primary 1280x800+0+0\n  800x600 60.00\n"
        reader = mock.Mock()
        with tempfile.TemporaryDirectory() as directory, \
                mock.patch.dict(sys.modules, {"overlay": types.SimpleNamespace(X11WindowRaiser=lambda: reader)}), \
                mock.patch.object(desktop_recovery.subprocess, "check_output", return_value=layout), \
                mock.patch.object(desktop_recovery, "window_geometry", return_value={"X": 1100, "Y": 700}), \
                mock.patch.object(desktop_recovery.subprocess, "run", side_effect=[None, OSError("resize failed"), None]) as run:
            with self.assertRaisesRegex(OSError, "resize failed"):
                desktop_recovery.resize_x11(1000, Path(directory))
            self.assertEqual(run.call_args.args[0], ["xrandr", "--fb", "1280x800", "--output", "Virtual1",
                                                    "--mode", "1280x800", "--pos", "0x0", "--primary"])
            evidence = json.loads((Path(directory) / "display-recovery.json").read_text())
            self.assertEqual(evidence["original"], layout)
            self.assertEqual(evidence["displacedOverlay"]["X"], 1100)
        reader.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
