import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "project_checks", Path(__file__).resolve().parents[1] / "scripts" / "check.py"
)
checks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checks)


class ProjectChecksTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("bash"), "Shell validation needs bash")
    def test_new_files_are_checked_including_the_second_shell_script(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src" / "nested").mkdir(parents=True)
            (root / "scripts").mkdir()
            (root / "scripts" / "a.sh").write_text("true\n", encoding="utf-8")
            second = root / "scripts" / "z.sh"
            second.write_text("if true; then\n", encoding="utf-8")
            with self.assertRaises(checks.subprocess.CalledProcessError):
                checks.validate_sources(root)
            second.write_text("true\n", encoding="utf-8")
            new_module = root / "src" / "nested" / "new.py"
            new_module.write_text("if broken\n", encoding="utf-8")
            with self.assertRaises(SyntaxError):
                checks.validate_sources(root)
            # Compilation must not execute a module or require its dependencies.
            new_module.write_text("raise RuntimeError('do not execute')\n", encoding="utf-8")
            new_data = root / "src" / "nested" / "new.json"
            new_data.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "new.json"):
                checks.validate_sources(root)
            new_data.write_text("{}", encoding="utf-8")
            checks.validate_sources(root)
