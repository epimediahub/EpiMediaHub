"""Existing player response must be preserved when external trust is unusable."""
import copy
import unittest
from unittest.mock import patch

from lookup_augmentation import append_trusted_to_existing_lookup as merge

CANONICAL = {
    "playlist_id": 44, "asset_key": "ep1", "season": 1, "episode": 1,
    "duration_ms": 2700000, "imdb_id": "tt0903747", "tmdb_id": 1396,
}
EXTERNAL = {
    "trusted_segments": [
        {"segment_type": "intro", "start_ms": 10000, "end_ms": 60000,
         "source": "introdb", "trusted": True},
        {"segment_type": "outro", "start_ms": 2500000, "end_ms": 2700000,
         "source": "theintrodb", "trusted": True},
    ],
    "conflicts": [], "cached": True,
}


def attempt(original, *, authorize=None, canonical=None, result=None):
    with patch("lookup_augmentation.resolve_external", return_value=result or EXTERNAL) as fetch:
        out = merge(original, playlist_id=44, asset_key="ep1",
                    authorized=authorize or (lambda *_: True),
                    canonical_episode=canonical or (lambda *_: CANONICAL))
    return out, fetch


class LookupAugmentationTests(unittest.TestCase):
    def test_adds_both_trusted_sources_without_changing_original_response(self):
        original = {"source_key": "source", "asset_key": "ep1",
                    "duration_ms": 2700000, "segments": [], "extra": {"x": 1}}
        copy_before = copy.deepcopy(original)
        result, fetched = attempt(original)
        self.assertEqual(original, copy_before)
        self.assertEqual(result["extra"], {"x": 1})
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual({x["source"] for x in result["segments"]},
                         {"introdb", "theintrodb"})
        self.assertTrue(all(x["auto_seek"] is False for x in result["segments"]))
        self.assertTrue(fetched.call_args.kwargs["offline"])

    def test_existing_approved_intro_has_priority(self):
        original = {"segments": [{"segment_type": "intro",
                    "start_ms": 9000, "end_ms": 65000, "source": "episcene"}]}
        result, _ = attempt(original)
        self.assertEqual(len(result["segments"]), 2)
        self.assertEqual(result["segments"][0]["source"], "episcene")
        self.assertEqual(result["segments"][1]["segment_type"], "outro")

    def test_existing_error_and_permissions_not_bypassed(self):
        for response in ({"error": "unauthorized", "segments": []},
                         {"success": False, "segments": []},
                         {"no_segments_key": True},
                         {"segments": "wrong"}):
            result, fetched = attempt(response)
            self.assertEqual(result, response)
            fetched.assert_not_called()
        response = {"segments": []}
        result, fetched = attempt(response, authorize=lambda *_: False)
        self.assertEqual(result, response)
        fetched.assert_not_called()

    def test_existing_unknown_marker_contract_is_untouched(self):
        for marker in ({"start": 1000, "end": 60000, "type": "intro"},
                       {"start_ms": -1, "end_ms": 60000, "segment_type": "intro"},
                       {"start_ms": 1000, "end_ms": 60000, "segment_type": "other"}):
            response = {"segments": [marker]}
            value, _ = attempt(response)
            self.assertEqual(value, response)

    def test_blocks_stale_and_source_conflicts(self):
        response = {"segments": []}
        value, _ = attempt(response, result=dict(EXTERNAL, stale=True))
        self.assertEqual(value, response)
        value, _ = attempt(response, result=dict(EXTERNAL, conflicts=["intro"]))
        self.assertEqual([x["segment_type"] for x in value["segments"]], ["outro"])

    def test_no_external_network_or_fabricated_identity(self):
        response = {"segments": []}
        value, fetched = attempt(response, canonical=lambda *_: None)
        self.assertEqual(value, response)
        fetched.assert_not_called()
        value, fetched = attempt(response, canonical=lambda *_:
                                dict(CANONICAL, imdb_id="", tmdb_id=0))
        self.assertEqual(value, response)
        fetched.assert_not_called()

    def test_overlap_blocks_unverified_cross_type_skip(self):
        response = {"segments": [{"segment_type": "recap",
                    "start_ms": 0, "end_ms": 35000}]}
        value, _ = attempt(response)
        self.assertEqual({x["segment_type"] for x in value["segments"]},
                         {"recap", "outro"})
        self.assertEqual(len(value["segments"]), 2)


if __name__ == "__main__":
    unittest.main()
