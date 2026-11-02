import os
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))
import app_detection


class DesktopEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.entry = self.root / "a desktop.desktop"

    def tearDown(self):
        self.temporary.cleanup()

    def parse(self, fields=None, *, language=None, environ=None):
        values = {"Type": "Application", "Name": "Paint", "Exec": "paint"}
        values.update(fields or {})
        self.entry.write_text("[Desktop Entry]\n" + "\n".join(
            key + "=" + value for key, value in values.items() if value is not None
        ) + "\n", encoding="utf-8")
        return app_detection.parse_desktop_file(self.entry, environ or {}, language=language, which=lambda command: command)

    def test_non_applications_and_unrepresentable_launch_contracts_are_skipped(self):
        for fields in ({"Type": "Link"}, {"Type": "Directory"}, {"Type": None},
                       {"Name": None}, {"Hidden": "true"}, {"NoDisplay": "true"},
                       {"Terminal": "true"}, {"Path": "/a/required/working-directory"}, {"Exec": None}):
            with self.subTest(fields=fields):
                self.assertIsNone(self.parse(fields))

    def test_visibility_flags_are_not_detected_in_comments_or_other_values(self):
        self.assertIsNotNone(self.parse({"Comment": "NoDisplay=true is documentation", "NoDisplay": "false"}))

    def test_desktop_visibility_uses_the_first_matching_current_desktop(self):
        fields = {"OnlyShowIn": "KDE;", "NotShowIn": "GNOME;"}
        self.assertIsNotNone(self.parse(fields, environ={"XDG_CURRENT_DESKTOP": "KDE:GNOME"}))
        self.assertIsNone(self.parse(fields, environ={"XDG_CURRENT_DESKTOP": "GNOME:KDE"}))
        self.assertIsNone(self.parse(fields, environ={"XDG_CURRENT_DESKTOP": "XFCE"}))
        self.assertIsNone(self.parse(fields))
        self.assertIsNotNone(self.parse({"NotShowIn": "GNOME;"}))

    def test_interface_language_and_locale_fallbacks_select_the_right_name(self):
        fields = {"Name[de]": "Malen", "Name[de_AT]": "Zeichnen", "Name[de_AT@formal]": "Zeichenprogramm"}
        for language, expected in (("de", "Malen"), ("de_CH.UTF-8", "Malen"),
                                   ("de_AT.UTF-8", "Zeichnen"), ("de_AT.UTF-8@formal", "Zeichenprogramm"), ("en", "Paint")):
            with self.subTest(language=language):
                self.assertEqual(self.parse(fields, language=language)["name"], expected)
        self.assertEqual(self.parse(fields, environ={"LC_ALL": "de_AT.UTF-8", "LANG": "en_US"})["name"], "Zeichnen")
        self.assertEqual(self.parse(fields, language="en", environ={"LANG": "de_AT.UTF-8"})["name"], "Paint")

    def test_double_quoting_string_escapes_and_literal_percent_round_trip(self):
        result = self.parse({"Exec": r'"/opt/My App/paint" "Cost\\$5" "C:\\\\Kids" "" 50%%'})
        self.assertEqual(shlex.split(result["exec"]), ["/opt/My App/paint", "Cost$5", "C:\\Kids", "", "50%"])

    def test_context_codes_expand_once_into_single_arguments(self):
        name = "Kid's work %U"
        result = self.parse({"Name": name, "Icon": "paint-icon", "Exec": "paint %i --caption=%c %k %U"})
        self.assertEqual(shlex.split(result["exec"]), ["paint", "--icon", "paint-icon", "--caption=" + name, str(self.entry)])
        without_icon = self.parse({"Exec": "paint %i %f %d"})
        self.assertEqual(shlex.split(without_icon["exec"]), ["paint"])

    def test_invalid_or_ambiguous_exec_syntax_is_not_guessed(self):
        for command in ('paint "unterminated', "paint 'single quoted'", "paint x;other", "paint %x",
                        "paint %C", "paint %", "paint %F %U", "paint --files=%F", 'paint "%c"',
                        "VARIABLE=value paint", "", "paint " + "x" * app_detection.MAX_EXEC_CHARS):
            with self.subTest(command=command[:60]):
                self.assertIsNone(self.parse({"Exec": command}))

    def test_explicit_env_launchers_remain_argv_data(self):
        result = self.parse({"Exec": "env EXAMPLE=one paint --file=%f"})
        self.assertEqual(shlex.split(result["exec"]), ["env", "EXAMPLE=one", "paint", "--file="])

    def test_tryexec_and_the_program_require_an_executable_not_just_a_file(self):
        program = self.root / "paint"
        program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.entry.write_text("[Desktop Entry]\nType=Application\nName=Paint\nTryExec=paint\nExec=paint\n", encoding="utf-8")
        environment = {"PATH": str(self.root)}
        self.assertIsNone(app_detection.parse_desktop_file(self.entry, environment))
        program.chmod(0o755)
        self.assertIsNotNone(app_detection.parse_desktop_file(self.entry, environment))
        self.entry.write_text("[Desktop Entry]\nType=Application\nName=Missing\nExec=missing\n", encoding="utf-8")
        self.assertIsNone(app_detection.parse_desktop_file(self.entry, environment))

    def test_missing_main_group_duplicate_keys_bad_encoding_and_large_files_are_skipped(self):
        for contents in (b"Name=Wrong\nExec=paint\n", b"[Desktop Action Other]\nName=Wrong\nExec=paint\n",
                         b"[Desktop Entry]\nType=Application\nName=One\nName=Two\nExec=paint\n", b"\xff",
                         b"x" * (app_detection.MAX_DESKTOP_BYTES + 1)):
            with self.subTest(length=len(contents)):
                self.entry.write_bytes(contents)
                self.assertIsNone(app_detection.parse_desktop_file(self.entry))


class DesktopDirectoryTests(unittest.TestCase):
    def write(self, root, relative, name, command, *, hidden=False):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[Desktop Entry]\nType=Application\nName=" + name + "\nExec=" + command +
                        ("\nHidden=true" if hidden else "") + "\n", encoding="utf-8")

    def test_xdg_roots_preserve_precedence_and_include_flatpak_and_snap_exports(self):
        roots = app_detection._application_directories("/home/test", {
            "XDG_DATA_HOME": "/custom/data", "XDG_DATA_DIRS": "/first:/second:/first:relative",
        })
        self.assertEqual(roots[:3], ["/custom/data/applications", "/first/applications", "/second/applications"])
        self.assertIn("/custom/data/flatpak/exports/share/applications", roots)
        self.assertIn("/var/lib/flatpak/exports/share/applications", roots)
        self.assertIn("/var/lib/snapd/desktop/applications", roots)
        defaults = app_detection._application_directories("/home/test", {"XDG_DATA_HOME": "relative"})
        self.assertEqual(defaults[:3], ["/home/test/.local/share/applications", "/usr/local/share/applications", "/usr/share/applications"])

    def test_nested_ids_overrides_and_duplicate_commands_have_stable_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            user, system = root / "user", root / "system"
            self.write(user, "vendor/app.desktop", "User", "paint --user")
            self.write(system, "vendor-app.desktop", "System", "paint --system")
            self.write(system, "other.desktop", "Same command", "paint --user")
            self.write(system, "different.desktop", "Different", "paint --different")
            apps = app_detection.scan_apps(root, [user, system], environ={}, which=lambda command: command)
            self.assertEqual(apps, [{"name": "User", "exec": "paint --user"}, {"name": "Different", "exec": "paint --different"}])

    def test_flatpak_export_commands_keep_their_exact_argument_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, "org.example.Paint.desktop", "Flatpak Paint",
                       "/usr/bin/flatpak run --branch=stable --command=paint org.example.Paint @@u %U @@")
            result = app_detection.scan_apps(root, [root], which=lambda command: command)
            self.assertEqual(shlex.split(result[0]["exec"]), ["/usr/bin/flatpak", "run", "--branch=stable", "--command=paint", "org.example.Paint", "@@u", "@@"])

    def test_scans_stop_at_the_result_and_file_budgets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.write(root, "a.desktop", "A", "paint --a", hidden=True)
            self.write(root, "b.desktop", "B", "paint --b")
            self.write(root, "c.desktop", "C", "paint --c")
            self.assertEqual(app_detection.scan_apps(root, [root], limit=0), [])
            self.assertEqual(len(app_detection.scan_apps(root, [root], limit=1, which=lambda command: command)), 1)
            with mock.patch.object(app_detection, "MAX_DESKTOP_FILES", 1):
                self.assertEqual(app_detection.scan_apps(root, [root], which=lambda command: command), [])


if __name__ == "__main__":
    unittest.main()
