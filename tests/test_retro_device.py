from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import json
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import retro_device
import retro_games


class RetroDeviceTests(unittest.TestCase):
    def report(self, *, arch="x86_64", flags=None, memory=16, gl="", vk="", extensions="", version="1.0", catalog=None, core_ready=False):
        def output(command):
            if command[0] == "glxinfo":
                return gl if "-B" in command else extensions
            if command[0] == "vulkaninfo":
                return vk
            return version
        with patch.object(retro_device.platform, "machine", return_value=arch), \
                patch.object(retro_device, "_cpu_flags", return_value=flags), \
                patch.object(retro_device, "_memory_gib", return_value=memory), \
                patch.object(retro_device, "_graphics_output", side_effect=output), \
                patch.object(retro_device, "read_os_release", return_value={"ID": "ubuntu"}), \
                patch.object(retro_device, "detect_native_provider", return_value="apt"):
            return retro_device.retro_device_report(catalog or [], core_ready=core_ready)

    def test_data_registry_contains_review_dates_and_primary_https_sources(self):
        self.assertRegex(retro_device.REQUIREMENTS["reviewed"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(len(retro_device.SYSTEMS), 8)
        for system in retro_device.SYSTEMS:
            self.assertTrue(system.sources)
            for source in system.sources:
                self.assertEqual(urlparse(source["url"]).scheme, "https")
                self.assertTrue(source["name"])

    def test_architecture_limits_apply_to_the_reviewed_build_and_leave_rpcs3_arm_unknown(self):
        rows = {row["system"]: row for row in self.report(arch="aarch64")["systems"]}
        self.assertEqual(rows["PlayStation"]["status"], "incompatible")
        self.assertEqual(rows["PlayStation 2"]["status"], "incompatible")
        self.assertEqual(rows["PlayStation 3"]["status"], "untested")
        rows = {row["system"]: row for row in self.report(arch="i686")["systems"]}
        self.assertEqual(rows["Wii U"]["status"], "incompatible")
        self.assertEqual(rows["GameCube / Wii"]["status"], "incompatible")

    def test_opengl_extensions_and_vulkan_alternative_are_reported_independently(self):
        gl = "OpenGL core profile version string: 3.3 Mesa\n"
        def ps2(report):
            return next(row for row in report["systems"] if row["system"] == "PlayStation 2")
        row = ps2(self.report(flags={"sse4_1"}, gl=gl, extensions="OpenGL extensions:\n GL_ARB_copy_image\n"))
        self.assertEqual((row["status"], row["reason"]), ("limited", "graphics"))
        self.assertEqual(next(check for check in row["checks"] if check["kind"] == "extensions")["status"], "fail")
        vk = "GPU0:\n apiVersion = 1.1.0\n deviceType = PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU\n"
        row = ps2(self.report(flags={"sse4_1"}, gl=gl, vk=vk, extensions="OpenGL extensions:\n GL_ARB_copy_image\n"))
        self.assertEqual(row["status"], "untested")
        self.assertFalse(row["performanceMeasured"])

    def test_scope_changes_for_driver_package_and_extension_changes_without_family_data(self):
        catalog = [{"id": "mgba-qt", "retroEmulator": True, "installed": True, "package": "mgba-qt"}]
        first = self.report(catalog=catalog)
        same = self.report(catalog=catalog)
        changed = self.report(catalog=catalog, version="2.0")
        self.assertEqual(first["deviceKey"], same["deviceKey"])
        self.assertEqual(first["systems"][0]["resultKey"], same["systems"][0]["resultKey"])
        self.assertNotEqual(first["systems"][0]["resultKey"], changed["systems"][0]["resultKey"])
        self.assertEqual(first["systems"][0]["version"], "1.0")
        with patch.object(retro_device, "_cpu_identity", return_value={"models": [("model name", "another CPU")], "cpus": 8, "kernel": "new"}):
            cpu = self.report(catalog=catalog)
        self.assertNotEqual(first["deviceKey"], cpu["deviceKey"])
        graphics = self.report(gl="OpenGL core profile version string: 4.6 Mesa\n")
        self.assertNotEqual(first["deviceKey"], graphics["deviceKey"])
        self.assertNotIn(str(Path.home()), json.dumps(first))
        self.assertRegex(first["checkedAt"], r"^\d{4}-\d{2}-\d{2}T")
        with patch.dict(retro_device.REQUIREMENTS, {"revision": "changed-rules"}):
            rules = self.report(catalog=catalog)
        self.assertNotEqual(first["systems"][0]["resultKey"], rules["systems"][0]["resultKey"])
        catalog = [{"id": "retroarch", "retroEmulator": True, "installed": True, "package": "retroarch"}]
        core_before = self.report(catalog=catalog, core_ready=True)["systems"][2]
        with patch.object(retro_games, "PS1_CORE_SHA256", "0" * 64):
            core_after = self.report(catalog=catalog, core_ready=True)["systems"][2]
        self.assertNotEqual(core_before["resultKey"], core_after["resultKey"])

    def test_oversized_or_failed_probe_is_unknown(self):
        with patch.object(retro_device.shutil, "which", return_value="/usr/bin/glxinfo"), \
                patch.object(retro_device.subprocess, "run") as run:
            run.return_value.stdout = "a" * (128 * 1024 + 1)
            self.assertEqual(retro_device._graphics_output(("glxinfo",)), "")
            run.side_effect = retro_device.subprocess.TimeoutExpired("glxinfo", 2)
            self.assertEqual(retro_device._graphics_output(("glxinfo",)), "")
            self.assertEqual(run.call_args.kwargs["timeout"], 2)

    def test_unusable_version_output_is_not_exposed(self):
        catalog = [{"id": "mgba-qt", "retroEmulator": True, "installed": True, "package": "mgba-qt"}]
        report = self.report(catalog=catalog, version="/home/private/config\n")
        self.assertEqual(report["systems"][0]["version"], "")
        self.assertNotIn("/home/private", json.dumps(report))

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
