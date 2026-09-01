import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import activity_store


class ActivityStoreTests(unittest.TestCase):
    def test_records_are_private_bounded_and_summarized_without_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "private" / "activity.json"
            for index in range(activity_store.MAX_ACTIVITY_RECORDS + 5):
                activity_store.record_activity(
                    path,
                    "default",
                    f"tile-{index}",
                    2_000_000 + index,
                    ended_at=2_000_060 + index,
                )

            payload = activity_store.activity_payload(path, now=2_001_100)
            stored = json.loads(path.read_text(encoding="utf-8"))

            self.assertEqual(payload["recordCount"], activity_store.MAX_ACTIVITY_RECORDS)
            self.assertEqual(payload["totalDurationSeconds"], 60_000)
            self.assertEqual(payload["records"][0]["tileId"], "tile-1004")
            self.assertNotIn("label", json.dumps(stored))
            if os.name == "posix":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_invalid_expired_and_future_records_are_ignored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "activity.json"
            now = 20_000_000
            path.write_text(json.dumps({
                "activityVersion": 1,
                "records": [
                    {"profileId": "default", "tileId": "ok", "startedAt": now - 30, "durationSeconds": 20},
                    {"profileId": "bad id", "tileId": "bad", "startedAt": now, "durationSeconds": 1},
                    {"profileId": "default", "tileId": "old", "startedAt": now - activity_store.MAX_ACTIVITY_AGE_SECONDS - 1, "durationSeconds": 1},
                    {"profileId": "default", "tileId": "future", "startedAt": now + 301, "durationSeconds": 1},
                    {"profileId": "default", "tileId": "long", "startedAt": now, "durationSeconds": activity_store.MAX_ACTIVITY_DURATION_SECONDS + 1},
                ],
            }), encoding="utf-8")

            self.assertEqual(
                activity_store.read_activity(path, now=now),
                [{"profileId": "default", "tileId": "ok", "startedAt": now - 30, "durationSeconds": 20}],
            )

    def test_clear_suppresses_an_in_progress_record_started_before_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "activity.json"
            activity_store.record_activity(path, "default", "old", 90, ended_at=100)
            activity_store.clear_activity(path, now=120)

            self.assertFalse(
                activity_store.record_activity(path, "default", "running", 110, ended_at=130)
            )
            self.assertTrue(
                activity_store.record_activity(path, "default", "new", 121, ended_at=131)
            )
            self.assertEqual(
                [record["tileId"] for record in activity_store.read_activity(path, now=131)],
                ["new"],
            )

    def test_profile_removal_deletes_only_matching_activity(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "activity.json"
            activity_store.record_activity(path, "default", "paint", 100, ended_at=110)
            activity_store.record_activity(path, "child-two", "game", 111, ended_at=121)

            activity_store.remove_profile_activity(path, "child-two", now=130)

            self.assertEqual(
                [record["profileId"] for record in activity_store.read_activity(path, now=130)],
                ["default"],
            )

    def test_embedded_tokens_finish_once_and_replace_stale_sessions(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "activity.json"
            times = iter([100, 110, 120, 130, 140])
            tokens = iter(["a" * 24, "b" * 24])
            sessions = activity_store.EmbeddedActivitySessions(
                path,
                clock=lambda: next(times),
                token_factory=lambda: next(tokens),
            )

            first = sessions.start("default", "paint")
            second = sessions.start("default", "browser")
            self.assertFalse(sessions.finish(first))
            self.assertTrue(sessions.finish(second))
            self.assertFalse(sessions.finish(second))

            records = activity_store.read_activity(path, now=140)
            self.assertEqual(
                [(record["tileId"], record["durationSeconds"]) for record in records],
                [("paint", 20), ("browser", 20)],
            )


if __name__ == "__main__":
    unittest.main()
