"""Synthetic tests: old authenticated user marks can be independent audio references."""
import json
import random
import sqlite3
import unittest

from authenticated_feedback_reference_bank import VerifiedReference
from fingerprint_cohort_v2 import decode
from verified_feedback_audio_peers import (
    reference_index, trusted_peers_for_target, compare_authenticated_mark,
    peer_record_for_cache, anchor_is_blocked,
)


def user_ref(**changes):
    d=dict(playlist_id=8,asset_key="other-episode",source_key="seriesA",
           season=13,episode=4,kind="intro",start_ms=45000,end_ms=72000,
           duration_ms=2400000,provenance="device_authenticated_direct")
    d.update(changes)
    return VerifiedReference(**d)


def target(**changes):
    d=dict(playlist_id=8,asset_key="target-episode",source_key="seriesA",
           season=13,episode=5,segment_type="intro",start_ms=120000,end_ms=147000)
    d.update(changes)
    return d


class VerifiedPeerTests(unittest.TestCase):
    def test_ref_from_any_old_approved_episode_is_indexed(self):
        refs=[user_ref(episode=x,asset_key=f"ep-{x}") for x in range(1,25)]
        groups=reference_index(refs)
        self.assertEqual(len(list(trusted_peers_for_target(groups,target()))),23)
        self.assertEqual(len(reference_index([user_ref(playlist_id=77)])),0)

    def test_cross_playlist_other_season_or_series_rejected(self):
        refs=[user_ref(),user_ref(playlist_id=10,asset_key="other"),
              user_ref(season=14,asset_key="another"),
              user_ref(source_key="different",asset_key="other2"),
              user_ref(episode=5,asset_key="target-episode")]
        options=list(trusted_peers_for_target(reference_index(refs),target()))
        self.assertEqual(len(options),1)
        self.assertEqual(options[0].episode,4)

    def test_actual_shifted_audio_matches_old_user_marker(self):
        rng=random.Random(166)
        common=[rng.getrandbits(32) for _ in range(210)]
        t=decode(json.dumps(common),step_ms=123.81,offset_ms=120000)
        prefix=[rng.getrandbits(32) for _ in range(100)]
        ref=decode(json.dumps(prefix+common),step_ms=123.81,offset_ms=32619)
        verified=user_ref(start_ms=45000,end_ms=72000)
        result=compare_authenticated_mark(target(),verified,t,ref)
        self.assertIsNotNone(result)
        self.assertGreaterEqual(result.frame_ratio,.9)
        self.assertEqual(peer_record_for_cache(verified)["asset_key"],"other-episode")

    def test_audio_outside_human_mark_does_not_count(self):
        rng=random.Random(211)
        words=[rng.getrandbits(32) for _ in range(210)]
        a=decode(json.dumps(words),step_ms=123.81,offset_ms=100000)
        b=decode(json.dumps(words),step_ms=123.81,offset_ms=600000)
        self.assertIsNone(compare_authenticated_mark(
            target(start_ms=100000,end_ms=130000),
            user_ref(start_ms=45000,end_ms=72000),a,b))

    def test_new_series_or_source_cannot_inherit_user_marks(self):
        rng=random.Random(1)
        words=[rng.getrandbits(32) for _ in range(210)]
        a=decode(json.dumps(words),step_ms=123.81,offset_ms=120000)
        b=decode(json.dumps(words),step_ms=123.81,offset_ms=45000)
        self.assertIsNone(compare_authenticated_mark(
            target(),user_ref(source_key="different"),a,b))

    def test_rejected_user_asset_cannot_be_used_as_anchor(self):
        with sqlite3.connect(":memory:") as c:
            c.execute("CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER)")
            c.execute("CREATE TABLE skip_records(asset_key TEXT,segment_type TEXT,status TEXT,duration_ms INTEGER)")
            ref=user_ref()
            self.assertFalse(anchor_is_blocked(c,ref))
            c.execute("INSERT INTO skip_records VALUES(?,?,?,?)",
                      ("other-episode","intro","rejected",2400000))
            self.assertTrue(anchor_is_blocked(c,ref))
            c.execute("DELETE FROM skip_records")
            c.execute("INSERT INTO skip_auto_blocks VALUES(?,?,?)",
                      ("other-episode","intro",2400000))
            self.assertTrue(anchor_is_blocked(c,ref))


if __name__=="__main__":
    unittest.main()
