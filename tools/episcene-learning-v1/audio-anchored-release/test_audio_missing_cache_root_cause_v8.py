"""Synthetic, read-only V8 cache absence diagnostic tests."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from audio_missing_cache_root_cause_v8 import (
    window_reason, evidence_window_counts, installed_retention_mode,
)


def database():
    con=sqlite3.connect(":memory:")
    con.execute("""CREATE TABLE skip_auto_windows
        (asset_key TEXT,kind TEXT,duration_ms INTEGER)""")
    con.execute("""CREATE TABLE skip_assets
        (asset_key TEXT,playlist_id INTEGER,source_key TEXT,season INTEGER,
         episode INTEGER)""")
    con.execute("INSERT INTO skip_assets VALUES ('a',8,'show',1,1)")
    return con


def row(**overrides):
    base=dict(asset_key="a",playlist_id=8,source_key="show",
              season=1,episode=1,segment_type="intro",asset_duration_ms=2400000)
    base.update(overrides)
    return base


class CacheMissingTests(unittest.TestCase):
    def test_no_cache_row_is_not_claimed_deleted(self):
        with database() as con:
            self.assertEqual(window_reason(con,row()),
                             "NO_STORED_CACHE_FOR_EPISODE_SEGMENT")

    def test_wrong_duration_is_different_failure(self):
        with database() as con:
            con.execute("INSERT INTO skip_auto_windows VALUES ('a','intro',2200000)")
            self.assertEqual(window_reason(con,row()),
                             "SAME_ASSET_AND_KIND_BUT_OLD_DURATION")

    def test_other_segment_is_not_a_matching_window(self):
        with database() as con:
            con.execute("INSERT INTO skip_auto_windows VALUES ('a','outro',2400000)")
            self.assertEqual(window_reason(con,row()),
                             "SAME_ASSET_ONLY_OTHER_SEGMENT_TYPE")

    def test_other_episode_asset_version_is_not_promoted(self):
        with database() as con:
            con.execute("INSERT INTO skip_assets VALUES ('b',8,'show',1,1)")
            con.execute("INSERT INTO skip_auto_windows VALUES ('b','intro',2400000)")
            self.assertEqual(window_reason(con,row()),
                             "SAME_EPISODE_OTHER_ASSET_VERSION_HAS_CACHE")

    def test_exact_match_is_reported_not_silent(self):
        with database() as con:
            con.execute("INSERT INTO skip_auto_windows VALUES ('a','intro',2400000)")
            self.assertEqual(window_reason(con,row()),
                             "EXACT_CACHE_EXISTS_UNEXPECTED")

    def test_evidence_pointer_categories_are_nonidentifying(self):
        inputs=[
          {"origin":"server","asset_key":"a"},
          {"origin":"server","asset_key":"another-key"},
          {"origin":"client","asset_key":"a"},
          {"origin":"server"},
        ]
        result=evidence_window_counts({
          "asset_key":"a","evidence_json":json.dumps({"windows":inputs})
        })
        self.assertEqual(result["EVIDENCE_HAS_OWN_SERVER_WINDOW_POINTER"],1)
        self.assertEqual(result["EVIDENCE_HAS_OTHER_SERVER_WINDOW_POINTER"],1)
        self.assertEqual(result["EVIDENCE_NON_SERVER_WINDOW"],1)
        self.assertEqual(result["EVIDENCE_SERVER_POINTER_MISSING_ASSET"],1)
        self.assertNotIn("another-key",str(result))

    def test_installed_prune_mode_by_bounded_source_signature(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"skip_automation.py"
            p.write_text("def episcene_prune_audio_window_cache(con): pass")
            self.assertEqual(installed_retention_mode(p),
                             "PINNED_CACHE_RETENTION_HELPER_PRESENT")
            p.write_text("DELETE FROM skip_auto_windows WHERE rowid NOT IN\nLIMIT 256")
            self.assertEqual(installed_retention_mode(p),
                             "LEGACY_256_ROW_PRUNER_PRESENT")
            p.write_text("def current(): pass")
            self.assertEqual(installed_retention_mode(p),
                             "UNKNOWN_RETENTION_LOGIC")


if __name__=="__main__":
    unittest.main()
