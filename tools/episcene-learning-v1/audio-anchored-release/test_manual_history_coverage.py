"""Offline tests of historic-user-marker coverage explanations."""
import sqlite3
import unittest

from authenticated_feedback_reference_bank import VerifiedReference
from fingerprint_manual_reference_shadow_v5 import (
    historical_reference_scope, authenticated_series_overview,
)


def ref(playlist=8, source="series-a", season=1, episode=1, kind="intro",
        provenance="device_authenticated_direct"):
    return VerifiedReference(
        playlist_id=playlist,asset_key=f"asset-{playlist}-{source}-{season}-{episode}-{kind}",
        source_key=source,season=season,episode=episode,kind=kind,
        start_ms=30000,end_ms=60000,duration_ms=2400000,provenance=provenance)


def target():
    return dict(playlist_id=8,source_key="series-a",season=2,
                episode=5,segment_type="intro")


class HistoryScopeTests(unittest.TestCase):
    def test_count_only_strict_current_season_kind_and_other_episode(self):
        refs=[
            ref(season=1,episode=1),
            ref(season=2,episode=3),
            ref(season=2,episode=4),
            ref(season=2,episode=5),
            ref(season=2,episode=6,kind="outro"),
            ref(season=2,episode=7,provenance="admin_reviewed_machine"),
            ref(playlist=10,season=2,episode=3),
            ref(source="different",season=2,episode=9),
        ]
        actual=historical_reference_scope(refs,target())
        self.assertEqual(actual,{
            "same_series_all_seasons":5,
            "same_series_same_season":4,
            "same_series_same_season_same_kind":3,
            "independent_episode_refs":2,
        })

    def test_missing_current_cohort_reports_zero_without_implicit_transfer(self):
        refs=[ref(playlist=10,season=2,episode=4),
              ref(source="different",season=2,episode=4)]
        self.assertEqual(
            historical_reference_scope(refs,target())["independent_episode_refs"],0)

    def test_distinct_historic_series_are_reported_with_safe_titles(self):
        db=sqlite3.connect(":memory:")
        db.execute("CREATE TABLE skip_assets(asset_key TEXT,title TEXT)")
        a=ref()
        b=ref(source="series-b",episode=2)
        db.executemany("INSERT INTO skip_assets VALUES(?,?)",[
            (a.asset_key,"Navy CIS"),(b.asset_key,"https://secret-provider/key")
        ])
        rows=authenticated_series_overview([a,b],db,{"asset_key","title"})
        self.assertEqual(len(rows),2)
        self.assertTrue(any(x[0]=="Navy CIS" for x in rows))
        self.assertFalse(any("secret-provider" in x[0] for x in rows))
        self.assertTrue(any(x[0].startswith("Serie ") for x in rows))
        db.close()


if __name__=="__main__":
    unittest.main()
