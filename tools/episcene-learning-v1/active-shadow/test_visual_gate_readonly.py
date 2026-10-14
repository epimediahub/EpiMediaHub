#!/usr/bin/env python3
"""No-secret, read-only visual-gate regression fixtures."""
import sqlite3
import unittest

import visual_gate_readonly as mod


def fixture():
    db=sqlite3.connect(':memory:');shadow=sqlite3.connect(':memory:')
    db.execute("""CREATE TABLE skip_assets(
        asset_key TEXT PRIMARY KEY,playlist_id INTEGER,title TEXT,source_key TEXT,
        season INTEGER,episode INTEGER,stream_id INTEGER,extension TEXT,
        duration_ms INTEGER,updated_at TEXT)""")
    db.execute("""CREATE TABLE skip_records(
        id INTEGER PRIMARY KEY,asset_key TEXT,start_ms INTEGER,end_ms INTEGER,
        source TEXT,segment_type TEXT,status TEXT)""")
    db.execute("""CREATE TABLE skip_scene_windows(
        id INTEGER PRIMARY KEY,asset_key TEXT,kind TEXT,offset_ms INTEGER,
        length_ms INTEGER,duration_ms INTEGER,created_at INTEGER)""")
    db.execute("""CREATE TABLE skip_scene_window_versions(
        window_id INTEGER PRIMARY KEY,version TEXT)""")
    shadow.execute("""CREATE TABLE shadow_outro_models(series TEXT,season INTEGER,
        playlist_id INTEGER,shift_ms INTEGER,reference_episodes INTEGER,
        mad_ms INTEGER,status TEXT,publish_allowed INTEGER)""")
    shadow.execute("""CREATE TABLE shadow_outro_candidates(
        auto_marker_id INTEGER,asset_key TEXT,series TEXT,season INTEGER,episode INTEGER,
        playlist_id INTEGER,original_start_ms INTEGER,suggested_start_ms INTEGER,
        end_ms INTEGER,offset_ms INTEGER,status TEXT)""")
    db.execute("INSERT INTO skip_assets VALUES('a',8,'MobLand','thebest',1,8,801,'mp4',2400000,'2026-10-14')")
    db.execute("INSERT INTO skip_records VALUES(2020,'a',2350133,2390000,'audio_repetition','outro','pending')")
    db.execute("INSERT INTO skip_records VALUES(1970,'earlier',3512323,3554000,'device','outro','pending')")
    db.execute("INSERT INTO skip_records VALUES(1315,'earlier',3547378,3589000,'audio_repetition','outro','pending')")
    shadow.execute("INSERT INTO shadow_outro_models VALUES('mobland',1,8,35133,5,668,'shadow_only',0)")
    shadow.execute("INSERT INTO shadow_outro_candidates VALUES(2020,'a','mobland',1,8,8,2350133,2315000,2390000,35133,'SHADOW_REVIEW_ONLY')")
    return db,shadow


class VisualGateTest(unittest.TestCase):
    def test_no_frames_does_not_imply_visual_review(self):
        db,shadow=fixture()
        with db,shadow:
            status=mod.inspect(db,shadow)
            self.assertEqual(status['candidate_count'],1)
            self.assertTrue(status['candidates'][0]['needs_new_visual_evidence'])
            self.assertFalse(status['candidates'][0]['eligible_for_automatic_release'])
            self.assertEqual(status['independent_episode_one_check']['status'],'SAME_ASSET_CANDIDATE')
            self.assertAlmostEqual(status['independent_episode_one_check']['difference_from_round_model_seconds'],-.078,places=3)

    def test_only_exact_revision_window_counts_as_coverage(self):
        db,shadow=fixture()
        with db,shadow:
            db.row_factory=sqlite3.Row
            asset=dict(db.execute("SELECT * FROM skip_assets WHERE asset_key='a'").fetchone())
            db.execute("INSERT INTO skip_scene_windows VALUES(1,'a','outro',2300000,80000,2400000,1760460000)")
            db.execute("INSERT INTO skip_scene_window_versions VALUES(1,?)",(mod.asset_version(asset),))
            ok=mod.inspect(db,shadow)
            self.assertTrue(ok['candidates'][0]['earlier_boundary_covered_by_valid_cache'])
            self.assertTrue(ok['candidates'][0]['original_boundary_covered_by_valid_cache'])
            db.execute("UPDATE skip_assets SET updated_at='2026-10-15' WHERE asset_key='a'")
            stale=mod.inspect(db,shadow)
            self.assertFalse(stale['candidates'][0]['earlier_boundary_covered_by_valid_cache'])
            self.assertEqual(stale['candidates'][0]['unverified_or_stale_windows'],1)

    def test_different_assets_do_not_count_as_prior_confirmation(self):
        db,shadow=fixture()
        with db,shadow:
            db.execute("UPDATE skip_records SET asset_key='different' WHERE id=1315")
            status=mod.inspect(db,shadow)
            self.assertEqual(status['independent_episode_one_check']['status'],'NOT_TESTABLE')
            self.assertEqual(status['new_auto_approvals'],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
