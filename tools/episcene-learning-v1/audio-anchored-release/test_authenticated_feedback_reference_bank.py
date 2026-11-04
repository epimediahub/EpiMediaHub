"""Offline tests: preserve historical trusted user marks, reject revoked/weak claims."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

from authenticated_feedback_reference_bank import run,select_references


def fixtures(root):
    fb=Path(root)/"feedback.sqlite3"
    prod=Path(root)/"provisioning.db"
    with sqlite3.connect(fb) as c:
        c.execute("""CREATE TABLE feedback_versions(
          marker_id INTEGER,asset_key TEXT,playlist_id INTEGER,season INTEGER,
          episode INTEGER,kind TEXT,decision TEXT,active INTEGER,
          start_ms INTEGER,end_ms INTEGER,provenance TEXT,reviewed_at TEXT)""")
    with sqlite3.connect(prod) as c:
        c.execute("""CREATE TABLE skip_assets(
          asset_key TEXT,playlist_id INTEGER,source_key TEXT,
          season INTEGER,episode INTEGER,media_type TEXT,duration_ms INTEGER)""")
        c.execute("""CREATE TABLE skip_auto_windows(
          asset_key TEXT,kind TEXT,duration_ms INTEGER)""")
    return fb,prod


def add_asset(prod,key,playlist=8,series="seriesA",season=1,episode=1):
    with sqlite3.connect(prod) as c:
        c.execute("INSERT INTO skip_assets VALUES (?,?,?,?,?,?,?)",
                  (key,playlist,series,season,episode,"episode",2_400_000))
        c.execute("INSERT INTO skip_auto_windows VALUES (?,?,?)",
                  (key,"intro",2_400_000))


def feedback(fb,key,marker_id=1,playlist=8,season=1,episode=1,
             kind="intro",decision="positive",active=1,start=40000,end=66000,
             provenance="device_authenticated_direct",reviewed="2026-10-25T12:00:00Z"):
    with sqlite3.connect(fb) as c:
        c.execute("INSERT INTO feedback_versions VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                  (marker_id,key,playlist,season,episode,kind,decision,active,
                   start,end,provenance,reviewed))


class VerifiedHistoryTests(unittest.TestCase):
    def test_all_distinct_historical_series_are_counted(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            for i in range(1,35):
                key=f"source-{i}"
                add_asset(prod,key,series=f"series-{i}",episode=i)
                feedback(fb,key,marker_id=i,episode=i)
            result=run(fb,prod)
            self.assertEqual(result["direct_user_reference_groups"],34)
            self.assertEqual(result["distinct_series_by_group"]["4K ANALYSE"],34)
            self.assertEqual(result["analysis_reference_cache"]["cache_present"],34)
            self.assertEqual(result["automatic_approvals_performed"],0)
            self.assertFalse(result["ready_for_automatic_release"])

    def test_old_revocation_and_active_negative_are_vetoed(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a")
            feedback(fb,"a",marker_id=1,active=0)
            self.assertEqual(run(fb,prod)["authenticated_reference_groups"],0)
            feedback(fb,"a",marker_id=2,active=1)
            feedback(fb,"a",marker_id=3,decision="negative",active=1)
            result=run(fb,prod)
            self.assertEqual(result["suppressed_active_negative_groups"],1)
            self.assertEqual(result["authenticated_reference_groups"],0)

    def test_conflicting_active_user_positions_excluded(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a")
            feedback(fb,"a")
            feedback(fb,"a",marker_id=2,start=50000,end=76000)
            result=run(fb,prod)
            self.assertEqual(result["suppressed_conflicting_positive_groups"],1)
            self.assertEqual(result["authenticated_reference_groups"],0)

    def test_unverified_conflicting_positive_is_still_a_veto(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a")
            feedback(fb,"a",marker_id=1)
            feedback(fb,"a",marker_id=2,start=90000,end=120000,
                     provenance="unverified_source_status")
            result=run(fb,prod)
            self.assertEqual(result["authenticated_reference_groups"],0)
            self.assertEqual(result["suppressed_conflicting_positive_groups"],1)

    def test_unproven_source_device_claim_does_not_count(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a")
            feedback(fb,"a",provenance="unverified_source_status")
            result=run(fb,prod)
            self.assertEqual(result["unauthenticated_positive_rows"],1)
            self.assertEqual(result["authenticated_reference_groups"],0)

    def test_admin_reviewed_not_mislabeled_as_user(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a",playlist=10)
            feedback(fb,"a",playlist=10,provenance="admin_reviewed_machine")
            result=run(fb,prod)
            self.assertEqual(result["admin_reviewed_reference_groups"],1)
            self.assertEqual(result.get("direct_user_reference_groups",0),0)
            self.assertEqual(result["by_playlist_group"]["THE BEST"],1)

    def test_valid_main_playlist_marker_not_silently_copied(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a",playlist=77)
            feedback(fb,"a",playlist=77)
            result=run(fb,prod)
            self.assertEqual(result["other_playlist_reference_groups_identity_required"],1)
            self.assertEqual(result["by_playlist_group"]["OTHER_PLAYLISTS"],1)
            self.assertFalse(result["ready_for_automatic_release"])

    def test_wrong_episode_asset_version_or_invalid_bound_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a")
            feedback(fb,"a",episode=2)
            result=run(fb,prod)
            self.assertEqual(result["rejected_identity_or_bounds"],1)
            with sqlite3.connect(fb) as c:c.execute("DELETE FROM feedback_versions")
            feedback(fb,"a",end=2_500_000)
            result=run(fb,prod)
            self.assertEqual(result["rejected_identity_or_bounds"],1)

    def test_duplicate_matching_positive_marks_are_one_reference(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            add_asset(prod,"a")
            feedback(fb,"a",marker_id=1)
            feedback(fb,"a",marker_id=2)
            result=run(fb,prod)
            self.assertEqual(result["authenticated_reference_groups"],1)
            self.assertEqual(result["direct_user_reference_groups"],1)

    def test_missing_feedback_does_not_masquerade_as_zero(self):
        with tempfile.TemporaryDirectory() as d:
            _,prod=fixtures(d)
            with self.assertRaisesRegex(RuntimeError,"STOP_SOURCE_MISSING"):
                run(Path(d)/"does_not_exist.sqlite3",prod)

    def test_missing_schema_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            fb,prod=fixtures(d)
            with sqlite3.connect(fb) as c:
                c.execute("DROP TABLE feedback_versions")
            with self.assertRaisesRegex(RuntimeError,"STOP_UNRECOGNIZED"):
                run(fb,prod)


if __name__=="__main__":
    unittest.main()
