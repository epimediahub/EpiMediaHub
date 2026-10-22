"""Synthetic EpiScene external marker API read-model regression tests."""
from __future__ import annotations
from contextlib import contextmanager
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import native_external_markers as external


class FakeDatabase:
    def execute(self, query):
        assert "SELECT COUNT(*) FROM trusted_external_cache" in query
        return [(3,)]


class FakeReport:
    @staticmethod
    @contextmanager
    def ro(_path):
        yield FakeDatabase()

    @staticmethod
    def accepted_entries(_db):
        return 3, [
            {"season":1,"episode":3,"expires":500,
             "segments":[
                {"source":"introdb","segment_type":"intro",
                 "start_ms":1000,"end_ms":35000},
                {"source":"theintrodb","segment_type":"outro",
                 "start_ms":2400000,"end_ms":2490000}]},
            {"season":2,"episode":1,"expires":20,
             "segments":[{"source":"introdb","segment_type":"recap",
                          "start_ms":0,"end_ms":50000}]},
        ]

    @staticmethod
    def series_matches(_db, _entries):
        return {
            0: {("4K ANALYSE","Berlin"),("THE BEST","Berlino")},
            1: {("4K ANALYSE","Different")}
        }


class TestExternalMarkers(unittest.TestCase):
    def invoke(self, **kwargs):
        with (mock.patch.object(external, "_report_module", return_value=FakeReport),
              mock.patch.object(external.time, "time", return_value=100)):
            return external.list_external_markers(Path("/nonexistent/prod.db"), **kwargs)

    def test_no_guest_or_customer_playlist_filter_allowed(self):
        with self.assertRaises(ValueError):
            self.invoke(playlist="44")
        with self.assertRaises(ValueError):
            self.invoke(source="wrong")
        with self.assertRaises(ValueError):
            self.invoke(page="0")
        with self.assertRaises(ValueError):
            self.invoke(q="a"*81)

    def test_listing_reconciles_title_and_two_lanes_only(self):
        result=self.invoke(state="active")
        self.assertEqual(result["scope"],"analysis_playlists_only")
        self.assertTrue(result["read_only"])
        self.assertEqual(result["total"],4)
        self.assertEqual(result["source_counts"],{"introdb":2,"theintrodb":2})
        self.assertEqual({r["playlist_id"] for r in result["markers"]},{"8","10"})
        self.assertTrue(all(r["cache_status"]=="active" for r in result["markers"]))
        self.assertEqual(result["page"],1)

    def test_source_query_expiry_and_playlist_filters(self):
        result=self.invoke(playlist="10",source="theintrodb",q="berlino",state="active")
        self.assertEqual(result["total"],1)
        self.assertEqual(result["markers"][0]["kind"],"outro")
        result=self.invoke(state="expired")
        self.assertEqual(result["total"],1)
        self.assertEqual(result["markers"][0]["title"],"Different")

    def test_missing_report_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(external,"TRUSTED_BRIDGE",Path(temp)):
                with self.assertRaises(external.ExternalMarkerUnavailable):
                    external._report_module()


if __name__=="__main__":
    unittest.main()
