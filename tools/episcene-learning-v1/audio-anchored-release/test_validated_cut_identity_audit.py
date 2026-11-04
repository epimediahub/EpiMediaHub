"""Synthetic safety tests for the three confirmed playback marker identity audit."""
from __future__ import annotations
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from validated_cut_identity_audit import run, compare, content_window_identical, show_name

def make_db(path):
    with sqlite3.connect(path) as c:
        c.executescript("""
          CREATE TABLE skip_assets(
            asset_key TEXT,playlist_id INTEGER,source_key TEXT,duration_ms INTEGER,
            season INTEGER,episode INTEGER,media_type TEXT,series_title TEXT);
          CREATE TABLE skip_records(
            asset_key TEXT,segment_type TEXT,start_ms INTEGER,end_ms INTEGER,
            duration_ms INTEGER,status TEXT);
          CREATE TABLE skip_auto_windows(
            asset_key TEXT,kind TEXT,duration_ms INTEGER,offset_ms INTEGER,
            step_ms REAL,words_json TEXT,length_ms INTEGER,created_at TEXT);
        """)
        c.execute("INSERT INTO skip_assets VALUES (?,?,?,?,?,?,?,?)",
                  ("analysisA",8,"source1",2400000,13,4,"episode","Navy CIS"))
        c.execute("INSERT INTO skip_records VALUES (?,?,?,?,?,?)",
                  ("analysisA","intro",133000,161000,2400000,"pending"))
        return c

def push_cache(c,key):
    c.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?,?)",
              (key,"intro",2400000,50000,123.81,
               json.dumps([x*7919 for x in range(260)]),32200,"2026-11-04"))

class IdentityAuditTests(unittest.TestCase):
    def test_titles_only_locate_candidates(self):
        self.assertTrue(show_name("Navy CIS","Navy CIS"))
        self.assertTrue(show_name("One Piece","One Piece - All'arrembaggio!"))
        self.assertFalse(show_name("Navy CIS","Different Show"))

    def test_no_other_playlist_evidence_does_not_claim_verified(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.db"
            make_db(p)
            with sqlite3.connect(p) as c:
                push_cache(c,"analysisA")
            original=p.read_bytes()
            report=run(p)
            self.assertEqual(p.read_bytes(),original)
            item=report["Navy CIS S13 E4 intro"]
            self.assertEqual(item["result"],"NO_OTHER_PLAYLIST_ASSET_IN_THIS_DB")
            self.assertEqual(item["matching_analysis_marker_rows"],1)
            self.assertEqual(item["analysis_audio_windows_available"],1)
            self.assertFalse(item["playback_to_analysis_fully_verified"])

    def test_title_and_duration_not_content_proof(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.db"
            make_db(p)
            with sqlite3.connect(p) as c:
                c.execute("INSERT INTO skip_assets VALUES (?,?,?,?,?,?,?,?)",
                          ("mainB",55,"source2",2400000,13,4,"episode","Navy CIS"))
                push_cache(c,"analysisA")
            report=run(p)["Navy CIS S13 E4 intro"]
            self.assertEqual(report["other_playlist_candidate_count"],1)
            self.assertIn("SAME_TITLE_EPISODE_AND_DURATION_ONLY",
                          report["evidence_comparisons"])
            self.assertFalse(report["playback_to_analysis_fully_verified"])

    def test_equal_fingerprint_window_still_not_full_cut_approval(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"test.db"
            make_db(p)
            with sqlite3.connect(p) as c:
                c.execute("INSERT INTO skip_assets VALUES (?,?,?,?,?,?,?,?)",
                          ("mainB",55,"source1",2400000,13,4,"episode","Navy CIS"))
                push_cache(c,"analysisA")
                push_cache(c,"mainB")
            report=run(p)["Navy CIS S13 E4 intro"]
            self.assertIn("MATCHING_SOURCE_AND_CACHED_AUDIO_WINDOW",
                          report["evidence_comparisons"])
            self.assertFalse(report["playback_to_analysis_fully_verified"])

    def test_windows_must_include_all_words(self):
        left={"words_json":"[1,2,3]","step_ms":123.81,
              "offset_ms":0,"length_ms":1234}
        right=left.copy()
        self.assertFalse(content_window_identical(left,right))
        left["words_json"]=json.dumps(list(range(190)))
        right=left.copy()
        self.assertTrue(content_window_identical(left,right))
        right["offset_ms"]=400
        self.assertFalse(content_window_identical(left,right))

if __name__=="__main__":
    unittest.main()
