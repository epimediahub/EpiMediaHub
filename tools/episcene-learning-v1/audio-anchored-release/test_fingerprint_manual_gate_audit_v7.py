"""Bounded synthetic regression tests for exact manual-reference gate reasons."""
from dataclasses import dataclass
import sqlite3
import unittest
from unittest.mock import patch

import fingerprint_manual_gate_audit_v7 as v7

@dataclass(frozen=True)
class Ref:
    asset_key: str
    episode: int
    playlist_id: int = 8
    source_key: str = 'series-a'
    season: int = 1
    kind: str = 'intro'


class OriginalGatesTest(unittest.TestCase):
    def test_gates_explain_all_failures_in_original_order(self):
        class Release:
            @staticmethod
            def enabled(con,pid):return True
            @staticmethod
            def scene_release_ready(con,r):return False
            @staticmethod
            def current_reference(con,r):return False
            @staticmethod
            def reviewed_release_ready(r):return True
            @staticmethod
            def detector_release_ready(con,r):return False
        with sqlite3.connect(":memory:") as con:
            got=v7.strict_original_gate_failures(con,Release(),{"playlist_id":8})
            self.assertEqual(got,["visual","reference","detector"])
            self.assertFalse(con.in_transaction)

    def test_gate_exceptions_fail_closed(self):
        class Release:
            @staticmethod
            def enabled(con,pid):raise ValueError("hidden provider path")
            @staticmethod
            def scene_release_ready(con,r):return False
            @staticmethod
            def current_reference(con,r):return True
            @staticmethod
            def reviewed_release_ready(r):return True
            @staticmethod
            def detector_release_ready(con,r):return True
        with sqlite3.connect(":memory:") as con:
            got=v7.strict_original_gate_failures(con,Release(),{"playlist_id":8})
            self.assertEqual(got,["enabled_error","visual"])
            self.assertTrue(all("provider" not in x for x in got))


class HistoricCohortFunnelTests(unittest.TestCase):
    def test_every_pending_target_is_classified_without_visual_only_filter(self):
        key=(8,"series-a",1,"intro")
        targets=[{
            "playlist_id":8,"source_key":"series-a","season":1,
            "segment_type":"intro","asset_key":f"target-{i}",
            "episode":i,"status":"pending",
        } for i in range(1,17)]
        index={key:[Ref("human-a",90)]}
        with sqlite3.connect(":memory:") as con:
            with patch.object(v7,"audio_confirmed",return_value=True), \
                 patch.object(v7,"is_protected",return_value=False), \
                 patch.object(v7,"strict_original_gate_failures",return_value=["reference"]), \
                 patch.object(v7,"safe_title",return_value="Marked Series"), \
                 patch.object(v7,"anchor_is_blocked",return_value=False), \
                 patch.object(v7,"cached",return_value=None):
                report,total=v7.manually_marked_cohort_funnel(
                    con,object(),{key:targets},index,{"asset_key"})
        self.assertEqual(len(report),1)
        self.assertEqual(total["pending_audio_confirmed"],16)
        self.assertEqual(total["failed_reference"],16)
        self.assertEqual(total["target_has_independent_manual_reference"],16)
        self.assertEqual(total["target_cache_missing_or_invalid"],16)
        self.assertEqual(total["target_with_verified_manual_audio_match"],0)

    def test_protected_records_are_not_read_for_audio(self):
        key=(8,"series-a",1,"intro")
        row={"playlist_id":8,"source_key":"series-a","season":1,
             "segment_type":"intro","asset_key":"asset","episode":1,
             "status":"pending"}
        with sqlite3.connect(":memory:") as con:
            with patch.object(v7,"audio_confirmed",return_value=True), \
                 patch.object(v7,"is_protected",return_value=True), \
                 patch.object(v7,"safe_title",return_value="Marked Series"), \
                 patch.object(v7,"cached") as cached:
                results,total=v7.manually_marked_cohort_funnel(
                    con,object(),{key:[row]},{key:[Ref("human",2)]},{"asset_key"})
                cached.assert_not_called()
        self.assertEqual(total["protected_by_prior_marker_or_correction"],1)
        self.assertEqual(total["target_with_verified_manual_audio_match"],0)

    def test_no_production_approvals_in_report_keys(self):
        key=(8,"series-a",1,"intro")
        with sqlite3.connect(":memory:") as con:
            result,counts=v7.manually_marked_cohort_funnel(
                con,object(),{key:[]},{key:[Ref("human",1)]},{"asset_key"})
        self.assertEqual(result,[])
        self.assertNotIn("APPROVED",str(counts).upper())


if __name__=="__main__":
    unittest.main()
