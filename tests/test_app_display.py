import ctypes
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import app_display
import application_launcher
import process_supervisor
import process_state


class FullscreenPolicyTests(unittest.TestCase):
    def test_launcher_passes_fullscreen_request_and_waits_for_acknowledgement(self):
        launcher = application_launcher.ApplicationLauncher('tile', 'overlay', 'supervisor.py', 'overlay.py')
        with mock.patch.dict(os.environ, {"DISPLAY": ":1", "SDL_VIDEODRIVER": "x11"}), \
                mock.patch.object(application_launcher.os.path, "isfile", return_value=True), \
                mock.patch.object(launcher, "stop_existing_overlay"), \
                mock.patch.object(launcher, "stop_active_tile"), \
                mock.patch.object(launcher, "start_overlay", return_value=True), \
                mock.patch.object(launcher, "_wait_for_owned_process", return_value=True) as wait, \
                mock.patch.object(application_launcher.subprocess, "Popen") as popen:
            launcher.launch_owned_tile(["tuxmath", "--fullscreen"], "local")
        self.assertEqual(popen.call_args.args[0][-4:],
                         ["--managed-fullscreen", "--", "tuxmath", "--fullscreen"])
        self.assertTrue(wait.call_args.kwargs["require_ready"])
        self.assertEqual(wait.call_args.kwargs["timeout"], 30)

    @unittest.skipUnless(os.path.isdir('/proc'), 'Linux process identity required')
    def test_starting_record_remains_owned_and_can_be_marked_ready(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'tile.pid'
            process_state.write_process_record(path, os.getpid(), 'tile-process', ready=False)
            self.assertIs(process_state.owned_process(path, 'tile-process')['ready'], False)
            process_state.write_process_record(path, os.getpid(), 'tile-process', ready=True)
            self.assertIs(process_state.owned_process(path, 'tile-process')['ready'], True)
            with self.assertRaises(ValueError):
                process_state.write_process_record(path, os.getpid(), 'tile-process', ready='yes')

    def test_only_requested_tuxmath_x11_fullscreen_is_adapted(self):
        policy = application_launcher.needs_managed_fullscreen
        self.assertTrue(policy(["tuxmath", "--fullscreen"], {"DISPLAY": ":1"}))
        self.assertTrue(policy(["/usr/games/tuxmath", "--fullscreen", "--nosound"],
                               {"DISPLAY": ":1", "SDL_VIDEODRIVER": "x11"}))
        for command in ([], ["tuxmath"], ["tuxmath", "--windowed"],
                        ["tuxmath", "--fullscreen", "--windowed"], ["other", "--fullscreen"]):
            self.assertFalse(policy(command, {"DISPLAY": ":1"}))
        for environment in ({}, {"WAYLAND_DISPLAY": "wayland-0"},
                            {"DISPLAY": ":1", "SDL_VIDEODRIVER": "wayland"}):
            self.assertFalse(policy(["tuxmath", "--fullscreen"], environment))

    def test_readiness_requires_explicit_fullscreen_acknowledgement(self):
        wait = application_launcher.ApplicationLauncher._wait_for_owned_process
        process = mock.Mock()
        process.poll.return_value = None
        with mock.patch.object(application_launcher, "owned_process",
                               side_effect=[{"ready": False}, {"ready": True}]), \
                mock.patch.object(application_launcher.time, "sleep"):
            self.assertTrue(wait("record", "tile-process", "marker", process, require_ready=True))
        with mock.patch.object(application_launcher, "owned_process", return_value={"pid": 123}):
            self.assertFalse(wait("record", "tile-process", "marker", process,
                                  timeout=0, require_ready=True))


class FullscreenWindowTests(unittest.TestCase):
    def setUp(self):
        self.display = object.__new__(app_display.X11Fullscreen)
        self.display.root = 1
        self.display.requested = set()
        self.display.atom = lambda value: value
        self.properties = {(1, "_NET_CLIENT_LIST"): [10, 20, 30, 40],
                           (10, "_NET_WM_PID"): [999],
                           (20, "_NET_WM_PID"): [123],
                           (20, "_NET_WM_WINDOW_TYPE"): ["_NET_WM_WINDOW_TYPE_DIALOG"],
                           (30, "_NET_WM_PID"): [123], (30, "WM_TRANSIENT_FOR"): [40],
                           (40, "_NET_WM_PID"): [123],
                           (40, "_NET_WM_WINDOW_TYPE"): ["_NET_WM_WINDOW_TYPE_NORMAL"]}
        self.display.values = lambda window, name, _type: self.properties.get((window, name), [])
        self.display.request = mock.Mock(return_value=True)

    def test_only_owned_main_window_is_requested_once_and_then_confirmed(self):
        self.assertFalse(self.display.confirm([123]))
        self.assertFalse(self.display.confirm([123]))
        self.display.request.assert_called_once_with(40)
        self.properties[40, "_NET_WM_STATE"] = ["_NET_WM_STATE_FULLSCREEN"]
        self.assertTrue(self.display.confirm([123]))

    def test_no_acknowledgement_from_unrelated_fullscreen_window_or_exited_owner(self):
        self.properties[10, "_NET_WM_STATE"] = ["_NET_WM_STATE_FULLSCREEN"]
        self.assertFalse(self.display.confirm([]))
        self.display.request.assert_not_called()
        self.properties[40, "_NET_WM_PID"] = []  # destroyed XID or missing identity
        self.assertFalse(self.display.confirm([123]))
        self.display.request.assert_not_called()

    def test_request_uses_ewmh_add_not_toggle_and_only_target_xid(self):
        display = object.__new__(app_display.X11Fullscreen)
        display.display, display.root = 1234, 1
        display.atom = lambda name: {"_NET_WM_STATE": 11, "_NET_WM_STATE_FULLSCREEN": 12}[name]
        display.library = mock.Mock()
        def send(connection, root, propagate, mask, event_pointer):
            event = ctypes.cast(event_pointer, ctypes.POINTER(app_display.XEvent)).contents.client
            self.assertEqual((connection, root, propagate, mask), (1234, 1, 0, (1 << 19) | (1 << 20)))
            self.assertEqual((event.type, event.window, event.message_type, event.format), (33, 40, 11, 32))
            self.assertEqual(list(event.data), [1, 12, 0, 1, 0])
            return 1
        display.library.XSendEvent.side_effect = send
        self.assertTrue(display.request(40))
        display.library.XSync.assert_called_once_with(1234, 0)

    def test_close_releases_connection_and_restores_error_handler_once(self):
        display = object.__new__(app_display.X11Fullscreen)
        display.display, display.previous_handler, display.handler_installed = 1234, 9, True
        display.library = mock.Mock()
        display.close()
        display.close()
        display.library.XCloseDisplay.assert_called_once_with(1234)
        display.library.XSetErrorHandler.assert_called_once_with(9)


class FullscreenStartupTests(unittest.TestCase):
    def test_readiness_is_published_only_after_fullscreen_confirmation(self):
        with mock.patch.object(process_supervisor, "_enable_child_subreaper"), \
                mock.patch.object(process_supervisor.signal, "signal"), \
                mock.patch.object(app_display, "X11Fullscreen"), \
                mock.patch.object(process_supervisor.subprocess, "Popen"), \
                mock.patch.object(process_supervisor, "_reap_children"), \
                mock.patch.object(process_supervisor, "wait_for_fullscreen") as wait, \
                mock.patch.object(process_supervisor, "owned_processes", return_value=[]), \
                mock.patch.object(process_supervisor, "write_process_record") as write, \
                mock.patch.object(process_supervisor, "remove_process_record"):
            def confirm(_display):
                self.assertEqual(write.call_count, 1)
                self.assertIs(write.call_args.kwargs["ready"], False)
            wait.side_effect = confirm
            self.assertEqual(process_supervisor.supervise(
                ["tuxmath", "--fullscreen"], "record", "marker", managed_fullscreen=True), 0)
            self.assertEqual([call.kwargs['ready'] for call in write.call_args_list], [False, True])

    def test_wait_handles_slow_mapping_and_confirms_owned_pids(self):
        display = mock.Mock()
        display.confirm.side_effect = [False, True]
        with mock.patch.object(process_supervisor, "_termination_signal", None), \
                mock.patch.object(process_supervisor, "owned_processes", return_value=[123]), \
                mock.patch.object(process_supervisor.time, "sleep"):
            process_supervisor.wait_for_fullscreen(display)
        self.assertEqual(display.confirm.call_args_list, [mock.call([123]), mock.call([123])])

    def test_timeout_exit_and_shutdown_never_claim_success(self):
        display = mock.Mock()
        with self.assertRaisesRegex(OSError, "did not enter fullscreen"):
            process_supervisor.wait_for_fullscreen(display, timeout=0)
        with mock.patch.object(process_supervisor, "_termination_signal", None), \
                mock.patch.object(process_supervisor, "owned_processes", return_value=[]):
            with self.assertRaisesRegex(OSError, "exited"):
                process_supervisor.wait_for_fullscreen(display)
        with mock.patch.object(process_supervisor, "_termination_signal", 15):
            with self.assertRaisesRegex(OSError, "cancelled"):
                process_supervisor.wait_for_fullscreen(display)
        display.confirm.assert_not_called()

    def test_failed_fullscreen_cleans_owned_children_and_keeps_config_argv_unchanged(self):
        original = ["tuxmath", "--fullscreen", "--nosound"]
        with mock.patch.object(process_supervisor, "_enable_child_subreaper"), \
                mock.patch.object(process_supervisor.signal, "signal"), \
                mock.patch.object(app_display, "X11Fullscreen") as factory, \
                mock.patch.object(process_supervisor.subprocess, "Popen") as popen, \
                mock.patch.object(process_supervisor, "wait_for_fullscreen", side_effect=OSError("timeout")), \
                mock.patch.object(process_supervisor, "owned_processes", return_value=[123]), \
                mock.patch.object(process_supervisor, "terminate_owned_tree") as terminate, \
                mock.patch.object(process_supervisor, "write_process_record") as write, \
                mock.patch.object(process_supervisor, "remove_process_record") as remove:
            with self.assertRaisesRegex(OSError, "timeout"):
                process_supervisor.supervise(original, "record", "marker", managed_fullscreen=True)
            self.assertEqual(popen.call_args.args[0], ["tuxmath", "--windowed", "--nosound"])
            self.assertEqual(popen.call_args.kwargs["env"]["SDL_VIDEODRIVER"], "x11")
            self.assertEqual(write.call_count, 1)
            self.assertIs(write.call_args.kwargs["ready"], False)
            factory.return_value.close.assert_called_once()
            terminate.assert_called_once()
            remove.assert_called_once()
        self.assertEqual(original, ["tuxmath", "--fullscreen", "--nosound"])


if __name__ == "__main__":
    unittest.main()
