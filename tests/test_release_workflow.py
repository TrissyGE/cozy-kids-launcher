import getpass
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class StableMainReleaseContractTests(unittest.TestCase):
    def test_ci_runs_for_the_development_branch(self):
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("branches: [main, develop]", workflow)

    def test_release_is_published_before_main_is_promoted(self):
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        publish = 'gh release edit "$GITHUB_REF_NAME" --draft=false'
        promote = 'git push "git@github.com:$GITHUB_REPOSITORY.git" "$GITHUB_SHA:refs/heads/main"'
        self.assertIn(publish, workflow)
        self.assertIn(promote, workflow)
        self.assertLess(workflow.index(publish), workflow.index(promote))
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("group: stable-release-promotion", workflow)
        self.assertIn("secrets.RELEASE_DEPLOY_KEY", workflow)
        self.assertIn('git ls-remote "git@github.com:$GITHUB_REPOSITORY.git"', workflow)

    def test_stable_main_check_compares_commit_with_latest_release_tag(self):
        workflow = (
            REPOSITORY_ROOT / ".github" / "workflows" / "stable-main.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("releases/latest", workflow)
        self.assertIn('release_sha="$(git rev-parse "$tag^{commit}")"', workflow)
        self.assertIn('main_sha="$(git rev-parse HEAD)"', workflow)
        self.assertIn('[[ "$main_sha" != "$release_sha" ]]', workflow)

    def test_local_release_gate_refuses_main(self):
        deploy = (REPOSITORY_ROOT / "scripts" / "deploy.sh").read_text(encoding="utf-8")
        self.assertIn('[[ "$CURRENT_BRANCH" != "main" ]]', deploy)
        self.assertIn("main is the stable legacy-updater channel", deploy)

    def test_standalone_installer_can_extract_without_unzip(self):
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("command -v unzip", installer)
        self.assertIn('python3 -m zipfile -e "$TMP_DIR/repo.zip" "$TMP_DIR/"', installer)

    def test_new_installations_start_with_a_versioned_config(self):
        installer = (REPOSITORY_ROOT / "scripts" / "install.sh").read_text(
            encoding="utf-8"
        )
        example = json.loads(
            (REPOSITORY_ROOT / "examples" / "config.example.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertIn('"configVersion": 1', installer)
        self.assertEqual(example["configVersion"], 1)

    @unittest.skipUnless(os.name == "posix", "Installer smoke test requires Linux")
    def test_isolated_installer_writes_the_current_config_schema(self):
        with tempfile.TemporaryDirectory() as home:
            subprocess.run(
                [
                    "bash",
                    str(REPOSITORY_ROOT / "scripts" / "install.sh"),
                    "--user",
                    getpass.getuser(),
                    "--home",
                    home,
                    "--lang",
                    "en",
                    "--launch-mode",
                    "window",
                    "--skip-browser-check",
                    "--force",
                ],
                cwd=REPOSITORY_ROOT,
                check=True,
                stdout=subprocess.DEVNULL,
            )
            installed = json.loads(
                (
                    Path(home)
                    / ".config"
                    / "cozy-kids-launcher"
                    / "config.json"
                ).read_text(encoding="utf-8")
            )
            config_path = (
                Path(home)
                / ".config"
                / "cozy-kids-launcher"
                / "config.json"
            )
            backup_root = (
                Path(home)
                / ".local"
                / "share"
                / "cozy-kids-launcher-backups"
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "app_detection.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "config_store.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "config_validation.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "backup_store.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "lifecycle_state.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "parent_auth.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "runtime_diagnostics.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "process_state.py"
                ).is_file()
            )
            self.assertTrue(
                (
                    Path(home)
                    / ".local"
                    / "share"
                    / "cozy-kids-launcher"
                    / "process_supervisor.py"
                ).is_file()
            )
            self.assertEqual(config_path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backup_root.stat().st_mode & 0o777, 0o700)
            self.assertEqual(len(list(backup_root.iterdir())), 1)
        self.assertEqual(installed["configVersion"], 1)


if __name__ == "__main__":
    unittest.main()
