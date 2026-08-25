import unittest
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class StableMainReleaseContractTests(unittest.TestCase):
    def test_release_is_published_before_main_is_promoted(self):
        workflow = (REPOSITORY_ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8"
        )
        publish = 'gh release edit "$GITHUB_REF_NAME" --draft=false'
        promote = 'git push origin "$GITHUB_SHA:refs/heads/main"'
        self.assertIn(publish, workflow)
        self.assertIn(promote, workflow)
        self.assertLess(workflow.index(publish), workflow.index(promote))
        self.assertIn("git merge-base --is-ancestor", workflow)
        self.assertIn("group: stable-release-promotion", workflow)

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


if __name__ == "__main__":
    unittest.main()
