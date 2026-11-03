from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import retro_device


class RetroDeviceTests(unittest.TestCase):
    def test_software_graphics_versions_are_not_used_as_gpu_capability(self):
        self.assertEqual(retro_device._opengl_version(
            "OpenGL renderer string: llvmpipe\nOpenGL core profile version string: 4.5\n"
        ), ())
        self.assertEqual(retro_device._opengl_version(
            "OpenGL core profile version string: 4.6 (Core Profile) Mesa\n"
        ), (4, 6))
        self.assertEqual(retro_device._vulkan_version(
            "GPU0:\n apiVersion = 1.4.0\n deviceType = PHYSICAL_DEVICE_TYPE_CPU\n"
            "GPU1:\n apiVersion = 1.2.4\n deviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU\n"
        ), (1, 2))

    def test_known_incompatibility_is_distinct_from_unmeasured_performance_and_install_route(self):
        with patch.object(retro_device.platform, "machine", return_value="x86_64"), \
                patch.object(retro_device, "_cpu_flags", return_value={"ssse3"}), \
                patch.object(retro_device, "_memory_gib", return_value=2.0), \
                patch.object(retro_device, "_graphics_output", return_value=""), \
                patch.object(retro_device, "read_os_release", return_value={"ID": "ubuntu"}), \
                patch.object(retro_device, "detect_native_provider", return_value="apt"):
            report = retro_device.retro_device_report(
                [{"id": "retroarch", "retroEmulator": True, "installed": True, "package": "retroarch"}],
                core_ready=False,
            )
        rows = {row["system"]: row for row in report["systems"]}
        self.assertEqual((rows["PlayStation"]["status"], rows["PlayStation"]["route"]), ("untested", "available"))
        self.assertEqual((rows["PlayStation 2"]["status"], rows["PlayStation 2"]["reason"]), ("incompatible", "cpu"))
        self.assertEqual((rows["Wii U"]["status"], rows["Wii U"]["reason"]), ("limited", "memory"))
        self.assertEqual(rows["PlayStation 3"]["route"], "unavailable")
        self.assertEqual(report["vulkan"], "")

    def test_missing_gpu_probe_does_not_rule_out_alternative_renderer(self):
        cemu = next(system for system in retro_device.SYSTEMS if system.emulator == "Cemu")
        self.assertEqual(retro_device._compatibility(cemu, "x86_64", None, 8, (4, 1), ()),
                         ("untested", "performance"))
        self.assertEqual(retro_device._compatibility(cemu, "x86_64", None, 8, (4, 1), (1, 1)),
                         ("limited", "graphics"))
