"""Synthetic negative-control selection and audio cache key isolation tests."""
import unittest

from fingerprint_shadow_replay_v3 import (
    audio_cache_key, unrelated_control_cohort, playlist_summary_lines,
)


class FingerprintV3SafetyTests(unittest.TestCase):
    def test_same_asset_intro_outro_do_not_share_cache(self):
        intro={"playlist_id":8,"asset_key":"some-asset","segment_type":"intro"}
        outro={**intro,"segment_type":"outro"}
        self.assertNotEqual(audio_cache_key(intro), audio_cache_key(outro))
        self.assertNotEqual(audio_cache_key(intro),
                            audio_cache_key({**intro,"playlist_id":10}))

    def test_controls_are_only_unrelated_series_same_playlist_kind(self):
        target={"playlist_id":8,"source_key":"series-a","segment_type":"intro"}
        self.assertTrue(unrelated_control_cohort(
            target,(8,"series-b",1,"intro")))
        self.assertFalse(unrelated_control_cohort(
            target,(8,"series-a",1,"intro")))
        self.assertFalse(unrelated_control_cohort(
            target,(10,"series-b",1,"intro")))
        self.assertFalse(unrelated_control_cohort(
            target,(8,"series-b",1,"outro")))

    def test_negative_control_count_is_not_release_authorization(self):
        from collections import Counter
        records=Counter({
            (8,"NEGATIVE_CONTROL_POSSIBLE_FALSE_MATCH"):2,
            (8,"THREE_OR_MORE_PEER_PROOFS"):1,
            (10,"NEGATIVE_CONTROL_CHECKED"):3
        })
        summary=playlist_summary_lines(records,8)
        self.assertIn("  NEGATIVE_CONTROL_POSSIBLE_FALSE_MATCH: 2",summary)
        self.assertNotIn("  NEGATIVE_CONTROL_CHECKED: 3",summary)
        self.assertTrue(all("APPROVED" not in x for x in summary))


if __name__=="__main__":
    unittest.main()
