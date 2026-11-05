import importlib.util
import queue
import sys
import threading
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
sys.path.insert(0, str(SOURCE_ROOT))
MODULE_PATH = SOURCE_ROOT / "overlay.py"
SPEC = importlib.util.spec_from_file_location("overlay", MODULE_PATH)
overlay = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(overlay)


class FakeWindow:
    def __init__(self, reject_type=False):
        self.calls = []
        self.reject_type = reject_type

    def attributes(self, *args):
        self.calls.append(("attributes", *args))
        if self.reject_type and args == ("-type", "dock"):
            raise overlay.tk.TclError("unsupported window type")

    def lift(self):
        self.calls.append(("lift",))


class FakeX11Function:
    def __init__(self, result=None):
        self.result = result
        self.calls = []
        self.argtypes = None
        self.restype = None

    def __call__(self, *args):
        self.calls.append(args)
        return self.result


class FakeX11Library:
    def __init__(self, display=123):
        self.XOpenDisplay = FakeX11Function(display)
        self.XRaiseWindow = FakeX11Function()
        self.XFlush = FakeX11Function()
        self.XCloseDisplay = FakeX11Function()


class FakeTkWindow:
    _w = "."

    def __init__(self, frame_id, inner_id):
        self.tk = mock.Mock()
        self.tk.call.return_value = frame_id
        self.inner_id = inner_id

    def winfo_id(self):
        return self.inner_id


class OverlayWindowHintTests(unittest.TestCase):
    def test_tile_availability_closes_only_the_matching_owned_tile(self):
        status = {"profileAllowed": True, "blockedTileIds": ["paint"]}
        self.assertTrue(overlay.tile_is_blocked(status, "paint"))
        self.assertFalse(overlay.tile_is_blocked(status, "games"))
        self.assertTrue(
            overlay.tile_is_blocked(
                {"profileAllowed": False, "blockedTileIds": []},
                "games",
            )
        )
        self.assertFalse(overlay.tile_is_blocked({}, ""))

    def test_dock_and_topmost_hints_are_applied_before_lift(self):
        window = FakeWindow()

        overlay.configure_overlay_window(window)

        self.assertEqual(
            window.calls,
            [
                ("attributes", "-type", "dock"),
                ("attributes", "-topmost", True),
                ("lift",),
            ],
        )

    def test_topmost_hint_remains_when_dock_type_is_unsupported(self):
        window = FakeWindow(reject_type=True)

        overlay.configure_overlay_window(window)

        self.assertIn(("attributes", "-topmost", True), window.calls)
        self.assertEqual(window.calls[-1], ("lift",))

    def test_owned_x11_window_is_raised_without_external_commands(self):
        library = FakeX11Library()
        with mock.patch.dict(overlay.os.environ, {"DISPLAY": ":1"}):
            raiser = overlay.X11WindowRaiser(loader=lambda _: library)

        self.assertTrue(raiser.raise_window(0x1234))
        self.assertEqual(library.XOpenDisplay.calls, [(None,)])
        self.assertEqual(
            library.XRaiseWindow.calls[0][0],
            123,
        )
        self.assertEqual(
            library.XRaiseWindow.calls[0][1].value,
            0x1234,
        )
        self.assertEqual(library.XFlush.calls, [(123,)])

        raiser.close()
        self.assertEqual(library.XCloseDisplay.calls, [(123,)])
        self.assertFalse(raiser.display)

    def test_x11_raise_is_disabled_without_an_x_display(self):
        loader = mock.Mock()
        with mock.patch.dict(overlay.os.environ, {}, clear=True):
            raiser = overlay.X11WindowRaiser(loader=loader)

        self.assertFalse(raiser.raise_window(1))
        loader.assert_not_called()

    def test_outer_toplevel_id_is_used_instead_of_the_inner_tk_window(self):
        window = FakeTkWindow("0x1234", 0x1233)

        self.assertEqual(overlay.x11_toplevel_id(window), 0x1234)
        window.tk.call.assert_called_once_with("wm", "frame", ".")


class LauncherFocusTests(unittest.TestCase):
    def test_ewmh_activates_only_the_owned_browser_pid_not_a_matching_title(self):
        listing = mock.Mock(
            returncode=0,
            stdout="0x02 0 999 host Cozy Kids Launcher\n0x03 0 1234 host Launcher\n",
        )
        activated = mock.Mock(returncode=0)
        with mock.patch.object(
            overlay.subprocess,
            "run",
            side_effect=(listing, activated),
        ) as run, mock.patch.object(overlay, "owned_process", return_value={"pid": 1234}):
            overlay.focus_launcher()

        self.assertEqual(
            run.call_args_list,
            [
                mock.call(
                    ["wmctrl", "-lp"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                ),
                mock.call(
                    ["wmctrl", "-i", "-a", "0x03"],
                    timeout=3,
                    check=False,
                ),
            ],
        )

    def test_pid_scoped_xdotool_is_the_x11_fallback(self):
        listing = mock.Mock(returncode=1, stdout="")
        activation = mock.Mock(returncode=0)
        with mock.patch.object(
            overlay.subprocess,
            "run",
            side_effect=(listing, activation),
        ) as run, mock.patch.object(
            overlay,
            "owned_process",
            return_value={"pid": 1234},
        ):
            overlay.focus_launcher()

        self.assertEqual(
            run.call_args_list[1],
            mock.call(
                [
                    "xdotool",
                    "search",
                    "--pid",
                    "1234",
                    "windowactivate",
                ],
                capture_output=True,
                timeout=3,
                check=False,
            ),
        )

    def test_missing_or_changed_owner_never_activates_a_window(self):
        listing = mock.Mock(returncode=0, stdout="0x03 0 1234 host Cozy Kids Launcher\n")
        for ownership in ([None], [{"pid": 1234}, None]):
            with self.subTest(ownership=ownership), \
                    mock.patch.object(overlay, "owned_process", side_effect=ownership), \
                    mock.patch.object(overlay.subprocess, "run", return_value=listing) as run:
                overlay.focus_launcher()
            self.assertLessEqual(run.call_count, 1)


class OverlayResilienceTests(unittest.TestCase):
    def test_randr_results_are_bounded_and_freed(self):
        import ctypes
        reader = object.__new__(overlay.X11WindowRaiser)
        reader.display, reader.library, reader.randr = 123, mock.Mock(), mock.Mock()
        items = (overlay.MonitorInfo * 1)()
        items[0].x, items[0].y = 800, 200
        items[0].width, items[0].height, items[0].primary = 800, 600, 1
        def monitors(_display, _root, active, count):
            self.assertEqual(active, 1)
            ctypes.cast(count, ctypes.POINTER(ctypes.c_int))[0] = 1
            return items
        reader.randr.XRRGetMonitors.side_effect = monitors
        self.assertEqual(reader.monitors(), [(800, 200, 800, 600, True)])
        reader.randr.XRRFreeMonitors.assert_called_once_with(items)
        reader.randr = None
        self.assertEqual(reader.monitors(), [])

    def test_geometry_follows_active_primary_monitor_and_clamps_small_screens(self):
        self.assertEqual(overlay.overlay_geometry(
            [(0, 0, 1920, 1080, False), (1920, 300, 1280, 720, True)], (3200, 1080), True),
            (220, 70, 1944, 324))
        self.assertEqual(overlay.overlay_geometry(
            [(800, 200, 800, 600, True)], (1600, 800), False), (60, 60, 824, 224))
        self.assertEqual(overlay.overlay_geometry([], (100, 80), True), (100, 70, 0, 10))
        self.assertEqual(overlay.overlay_geometry([(0, 0, 0, 0, True)], (800, 600), False), (60, 60, 24, 24))

    def test_display_change_repositions_existing_control_without_recreating_it(self):
        control = object.__new__(overlay.AppOverlay)
        control.root = mock.Mock()
        control.root.winfo_screenwidth.return_value = 1600
        control.root.winfo_screenheight.return_value = 900
        control.root.winfo_rootx.return_value = 24
        control.root.winfo_rooty.return_value = 24
        control.x11_raiser = mock.Mock()
        control.x11_raiser.monitors.side_effect = [
            [(800, 0, 800, 900, True)], [(0, 0, 800, 600, True)], [(0, 0, 800, 600, True)]]
        control.expanded, control.geometry = False, None
        for _ in range(3):
            control.place_control()
        self.assertEqual(control.root.geometry.call_args_list,
                         [mock.call("60x60+824+24"), mock.call("60x60+24+24")])

    def test_readiness_waits_for_visible_close_button(self):
        control = object.__new__(overlay.AppOverlay)
        control.root, control.close_btn = mock.Mock(), mock.Mock()
        control.root.winfo_viewable.return_value = True
        control.close_btn.winfo_viewable.side_effect = [False, True]
        control.close_btn.winfo_width.return_value = 45
        with mock.patch.object(overlay, "write_process_record") as write:
            control.report_ready()
            write.assert_not_called()
            control.root.after.assert_called_once_with(50, control.report_ready)
            control.report_ready()
        self.assertIs(write.call_args.kwargs["ready"], True)

    def test_displaced_control_is_repaired_even_when_monitor_geometry_is_unchanged(self):
        control = object.__new__(overlay.AppOverlay)
        control.root, control.x11_raiser = mock.Mock(), mock.Mock()
        control.root.winfo_screenwidth.return_value = 800
        control.root.winfo_screenheight.return_value = 600
        control.root.winfo_rootx.return_value = 1100
        control.root.winfo_rooty.return_value = 700
        control.x11_raiser.monitors.return_value = [(0, 0, 800, 600, True)]
        control.expanded, control.geometry = False, (60, 60, 24, 24)
        control.place_control()
        control.root.geometry.assert_called_once_with("60x60+24+24")

    def test_slow_status_requests_leave_tk_responsive_and_never_spawn_extra_workers(self):
        control = object.__new__(overlay.AppOverlay)
        control.root = mock.Mock()
        control.timer_results = queue.Queue(maxsize=1)
        control.timer_polling, control.next_timer_poll = False, 0
        entered, release = threading.Event(), threading.Event()
        caller = threading.get_ident()
        workers = []
        def slow_api(_path):
            workers.append(threading.get_ident())
            entered.set()
            release.wait(timeout=3)
            return {}
        try:
            with mock.patch.object(overlay, "api", side_effect=slow_api):
                control.poll_timer()
                self.assertTrue(entered.wait(timeout=1))
                for _ in range(10):
                    control.poll_timer()
                self.assertEqual(len(workers), 1)
                self.assertNotEqual(workers[0], caller)
                self.assertEqual(control.root.after.call_count, 11)
                release.set()
                self.assertEqual(control.timer_results.get(timeout=2), ({}, {}))
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
