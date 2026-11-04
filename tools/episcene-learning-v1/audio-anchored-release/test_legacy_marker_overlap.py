"""Synthetic provenance reconciliation: overlap is NOT an approval."""
import sqlite3
import unittest
from authenticated_feedback_reference_bank import VerifiedReference
from legacy_marker_overlap import audit_overlap


def signed(asset="a",start=40000,end=60000):
    return VerifiedReference(playlist_id=8,asset_key=asset,source_key="s",
                             season=1,episode=1,kind="intro",
                             start_ms=start,end_ms=end,duration_ms=2400000,
                             provenance="device_authenticated_direct")


def setup():
    c=sqlite3.connect(":memory:")
    c.execute("""CREATE TABLE skip_assets(
        asset_key TEXT,playlist_id INTEGER,source_key TEXT,season INTEGER,
        episode INTEGER,duration_ms INTEGER)""")
    c.execute("""CREATE TABLE skip_records(
        id INTEGER,asset_key TEXT,segment_type TEXT,start_ms INTEGER,
        end_ms INTEGER,duration_ms INTEGER,disabled INTEGER,source TEXT,status TEXT)""")
    for i in "abcde":
        c.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?)",
                  (i,8,"s",1,1,2400000))
    c.executemany("INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?)",[
        (1,"a","intro",40000,60000,2400000,0,"device","approved"),
        (2,"b","intro",40000,60000,2400000,0,"device","approved"),
        (3,"c","intro",40600,60700,2400000,0,"device","approved"),
        (4,"d","intro",40000,60000,2400000,1,"device","approved"),
        (5,"e","intro",40000,60000,2400000,0,"audio","approved"),
    ])
    return c


class LegacyOverlapTests(unittest.TestCase):
    def test_exact_near_and_unauthenticated_are_separate(self):
        with setup() as c:
            result=audit_overlap(c,[signed("a"),signed("c")])
            self.assertEqual(result["legacy_approved_device_rows"],4)
            self.assertEqual(result["signed_feedback_exact_bounds"],1)
            self.assertEqual(result["signed_feedback_within_1500ms"],1)
            self.assertEqual(result["without_matching_signed_asset_reference"],1)
            self.assertEqual(result["disabled_or_revoked_legacy_rows"],1)
            self.assertTrue(result["all_unmatched_legacy_rows_are_held_not_promoted"])

    def test_signed_asset_with_different_bounds_is_not_trusted(self):
        with setup() as c:
            result=audit_overlap(c,[signed("a",start=90000,end=120000)])
            self.assertEqual(result["signed_asset_but_different_boundaries"],1)
            self.assertEqual(result["without_matching_signed_asset_reference"],2)

    def test_deleted_old_asset_is_reported_separately(self):
        with setup() as c:
            c.execute("INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?)",
                      (9,"deleted-old-asset","intro",10000,30000,2400000,0,
                       "device","approved"))
            result=audit_overlap(c,[signed("a"),signed("c")])
            self.assertEqual(result["total_legacy_device_approved_rows_all_assets"],5)
            self.assertEqual(result["legacy_approved_rows_without_current_asset"],1)
            self.assertEqual(result["legacy_rows_not_in_joined_inventory"],1)
            self.assertEqual(result["signed_feedback_exact_bounds"],1)

    def test_no_signed_history_does_not_claim_zero_legacy(self):
        with setup() as c:
            result=audit_overlap(c,[])
            self.assertEqual(result["legacy_approved_device_rows"],4)
            self.assertEqual(result["without_matching_signed_asset_reference"],3)
            self.assertEqual(result["distinct_series_needing_provenance_review"],1)


if __name__=="__main__":
    unittest.main()
