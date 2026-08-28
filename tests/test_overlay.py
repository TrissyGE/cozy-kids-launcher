import importlib.util
import sys
import unittest
from pathlib import Path


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


class OverlayWindowHintTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
