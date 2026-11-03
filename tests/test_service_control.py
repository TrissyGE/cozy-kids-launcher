from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import service_control


class UserServiceTests(unittest.TestCase):
    def test_graphical_environment_is_scoped_to_the_service(self):
        with self.assertRaisesRegex(ValueError, "graphical desktop"):
            service_control.session_environment({})
        with self.assertRaisesRegex(ValueError, "XAUTHORITY"):
            service_control.session_environment({"DISPLAY": ":1", "XAUTHORITY": "a\nb"})
        text = service_control.session_environment({
            "WAYLAND_DISPLAY": "wayland-0", "XAUTHORITY": '/tmp/a "quoted" path',
            "UNRELATED_SECRET": "excluded",
        })
        self.assertIn('WAYLAND_DISPLAY="wayland-0"\n', text)
        self.assertIn('DISPLAY=""\n', text)
        self.assertIn('XAUTHORITY="/tmp/a \\"quoted\\" path"\n', text)
        self.assertNotIn("UNRELATED_SECRET", text)

    def test_failed_enable_does_not_redirect_existing_desktop_launches(self):
        with tempfile.TemporaryDirectory() as directory:
            service = service_control.UserService(Path(directory), {})
            service.app_root.mkdir(parents=True)
            (service.app_root / service_control.UNIT).write_text("[Service]\n", encoding="utf-8")
            with patch.object(service_control, "systemctl", side_effect=RuntimeError("No user bus")):
                with self.assertRaisesRegex(RuntimeError, "No user bus"):
                    service.enable()
            self.assertFalse(service.marker.exists())
            self.assertFalse(service.unit_path.exists())

    def test_existing_custom_service_is_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            service = service_control.UserService(Path(directory), {})
            service.app_root.mkdir(parents=True)
            (service.app_root / service_control.UNIT).write_text("[Service]\n", encoding="utf-8")
            service.unit_path.parent.mkdir(parents=True)
            service.unit_path.write_text("# locally configured\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                service.enable()
            self.assertEqual(service.unit_path.read_text(encoding="utf-8"), "# locally configured\n")
            self.assertFalse(service.marker.exists())
