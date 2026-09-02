import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import media_state


def media_id(number):
    return f"{number:024x}"


class MediaStateTests(unittest.TestCase):
    def test_favorites_and_recents_stay_separate_per_profile(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state" / "media.json"
            first = media_id(1)
            second = media_id(2)

            media_state.set_media_favorite(path, "default", first, True)
            media_state.set_media_favorite(path, "alex", second, True)
            media_state.record_media_play(path, "default", first)
            media_state.record_media_play(path, "default", second)
            media_state.record_media_play(path, "default", first)

            self.assertEqual(
                media_state.media_state_payload(path, "default"),
                {"favoriteIds": [first], "recentIds": [first, second]},
            )
            self.assertEqual(
                media_state.media_state_payload(path, "alex"),
                {"favoriteIds": [second], "recentIds": []},
            )
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(document["mediaStateVersion"], 1)
            self.assertNotIn("path", path.read_text(encoding="utf-8").casefold())
            if os.name == "posix":
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
                self.assertEqual(stat.S_IMODE(path.parent.stat().st_mode), 0o700)

    def test_state_is_bounded_deduplicated_and_filtered_to_the_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "media.json"
            document = {
                "mediaStateVersion": 1,
                "profiles": {
                    "default": {
                        "favorites": [
                            media_id(index)
                            for index in range(media_state.MAX_MEDIA_FAVORITES + 5)
                        ],
                        "recents": [
                            media_id(index)
                            for index in range(media_state.MAX_MEDIA_RECENTS + 5)
                        ] + [media_id(1), "../../secret"],
                    }
                },
            }
            path.write_text(json.dumps(document), encoding="utf-8")

            payload = media_state.media_state_payload(
                path,
                "default",
                available_ids=[media_id(1), media_id(3)],
            )

            self.assertEqual(payload["favoriteIds"], [media_id(1), media_id(3)])
            self.assertEqual(payload["recentIds"], [media_id(1), media_id(3)])

    def test_updates_are_idempotent_and_apply_collection_limits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "media.json"
            for index in range(media_state.MAX_MEDIA_RECENTS + 5):
                media_state.record_media_play(path, "default", media_id(index))
            for index in range(media_state.MAX_MEDIA_FAVORITES + 5):
                media_state.set_media_favorite(path, "default", media_id(index), True)
            media_state.set_media_favorite(path, "default", media_id(204), False)
            media_state.set_media_favorite(path, "default", media_id(204), False)

            payload = media_state.media_state_payload(path, "default")

            self.assertEqual(len(payload["recentIds"]), media_state.MAX_MEDIA_RECENTS)
            self.assertEqual(payload["recentIds"][0], media_id(54))
            self.assertEqual(len(payload["favoriteIds"]), media_state.MAX_MEDIA_FAVORITES - 1)
            self.assertNotIn(media_id(204), payload["favoriteIds"])

            for index in range(media_state.MAX_MEDIA_STATE_PROFILES + 1):
                media_state.record_media_play(path, f"child-{index}", media_id(index))
            document = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(
                len(document["profiles"]),
                media_state.MAX_MEDIA_STATE_PROFILES,
            )
            self.assertIn(
                f"child-{media_state.MAX_MEDIA_STATE_PROFILES}",
                document["profiles"],
            )

    def test_corrupt_state_and_invalid_mutations_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "media.json"
            path.write_text("not json", encoding="utf-8")
            self.assertEqual(
                media_state.media_state_payload(path, "default"),
                {"favoriteIds": [], "recentIds": []},
            )
            with self.assertRaisesRegex(ValueError, "profileId"):
                media_state.media_state_payload(path, "bad profile")
            with self.assertRaisesRegex(ValueError, "mediaId"):
                media_state.record_media_play(path, "default", "../video")
            with self.assertRaisesRegex(ValueError, "boolean"):
                media_state.set_media_favorite(path, "default", media_id(1), 1)

            path.write_bytes(b" " * (media_state.MAX_MEDIA_STATE_BYTES + 1))
            self.assertEqual(
                media_state.media_state_payload(path, "default"),
                {"favoriteIds": [], "recentIds": []},
            )

    def test_profile_removal_deletes_only_matching_media_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "media.json"
            media_state.record_media_play(path, "default", media_id(1))
            media_state.record_media_play(path, "alex", media_id(2))

            media_state.remove_profile_media_state(path, "alex")
            media_state.remove_profile_media_state(path, "alex")

            self.assertEqual(
                media_state.media_state_payload(path, "default")["recentIds"],
                [media_id(1)],
            )
            self.assertEqual(
                media_state.media_state_payload(path, "alex")["recentIds"],
                [],
            )


if __name__ == "__main__":
    unittest.main()
