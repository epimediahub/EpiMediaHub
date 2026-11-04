"""Regression tests for read-only evidence pin and cache pointer audit."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
import json

from audio_evidence_pin_integrity_v9 import (
    pinned_keys_from_pending,evidence_pointer_availability,retention_status
)


def database():
    con=sqlite3.connect(":memory:")
    con.row_factory=sqlite3.Row
    con.execute("CREATE TABLE skip_records(id INTEGER,segment_type TEXT,status TEXT)")
    con.execute("CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT)")
    con.execute("""CREATE TABLE skip_auto_windows(
        asset_key TEXT,kind TEXT,duration_ms INTEGER,offset_ms INTEGER,
        length_ms INTEGER,step_ms REAL,created_at INTEGER)""")
    return con


class CacheEvidenceTests(unittest.TestCase):
    def test_pending_pins_all_referenced_server_assets_for_segment_kind(self):
        with database() as db:
            db.execute("INSERT INTO skip_records VALUES (1,'intro','pending')")
            db.execute("INSERT INTO skip_records VALUES (2,'outro','pending')")
            db.execute("INSERT INTO skip_records VALUES (3,'intro','approved')")
            db.executemany("INSERT INTO skip_auto_evidence VALUES (?,?)",(
                (1,json.dumps({"windows":[
                    {"origin":"server","asset_key":"own"},
                    {"origin":"server","asset_key":"peer"},
                    {"origin":"device","asset_key":"ignore"}]})),
                (2,json.dumps({"windows":[
                    {"origin":"server","asset_key":"own"}]})),
                (3,json.dumps({"windows":[
                    {"origin":"server","asset_key":"approved-no"}]}))
            ))
            pins,flags=pinned_keys_from_pending(db)
            self.assertEqual(pins,{("own","intro"),("own","outro"),("peer","intro")})
            self.assertNotIn(("approved-no","intro"),pins)

    def test_dangling_pointers_reported_without_reconstruction(self):
        with database() as db:
            db.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?)",
                       ("peer","intro",2400000,12000,40000,123.81,30))
            record={
                "asset_key":"own","segment_type":"intro",
                "evidence_json":json.dumps({"windows":[
                    {"origin":"server","asset_key":"own","duration_ms":2400000},
                    {"origin":"server","asset_key":"peer","duration_ms":2400000,
                     "offset_ms":12000,"length_ms":40000,"step_ms":123.81},
                    {"origin":"server","asset_key":"gone","duration_ms":2400000},
                ]})
            }
            data=evidence_pointer_availability(db,record)
            self.assertEqual(data["OWN_POINTER_CACHE_ROW_MISSING"],1)
            self.assertEqual(data["OTHER_POINTER_CACHE_ROW_MISSING"],1)
            self.assertEqual(data["OTHER_POINTER_CACHE_ROW_PRESENT"],1)
            self.assertEqual(data["OTHER_POINTER_CACHE_METADATA_MATCH"],1)

    def test_metadata_mismatch_is_not_equal_cache(self):
        with database() as db:
            db.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?)",
                       ("same","outro",2200000,1000,30000,123.81,12))
            record={"asset_key":"same","segment_type":"outro",
                    "evidence_json":json.dumps({"windows":[
                        {"origin":"server","asset_key":"same","duration_ms":2400000,
                         "offset_ms":1000,"length_ms":30000,"step_ms":123.81}
                    ]})}
            d=evidence_pointer_availability(db,record)
            self.assertEqual(d["OWN_POINTER_CACHE_METADATA_DIFFERENT"],1)

    def test_helper_presence_without_call_does_not_claim_active_execution(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"source.py"
            p.write_text("def episcene_prune_audio_window_cache(con): pass\n")
            status,checks=retention_status(p,820)
            self.assertEqual(status,"PINNED_CACHE_RETENTION_HELPER_PRESENT")
            self.assertEqual(checks["retention_helper_calls_in_source"],0)
            self.assertEqual(checks["below_8704_cache_cleanup_trigger"],1)
            p.write_text("def episcene_prune_audio_window_cache(con): pass\n"
                         "episcene_prune_audio_window_cache(con)\n")
            _,checks=retention_status(p,820)
            self.assertEqual(checks["retention_helper_calls_in_source"],1)

    def test_no_retention_signature_is_honest(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"src.py"
            p.write_text("def anything(): return None")
            status,checks=retention_status(p,820)
            self.assertEqual(status,"UNKNOWN_RETENTION_LOGIC")
            self.assertFalse(checks)

if __name__=="__main__":
    unittest.main()
