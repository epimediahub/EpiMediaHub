"""Synthetic read-only regressions for the external marker series report."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from report_trusted_marker_series import accepted_entries, canonical_match, series_matches


class TrustedSeriesReportTests(unittest.TestCase):
    def test_cache_report_keeps_only_accepted_source_markers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.db"
            with sqlite3.connect(path) as db:
                db.execute("""CREATE TABLE trusted_external_cache(
                    identity TEXT,response TEXT,expires_at INT)""")
                db.execute("INSERT INTO trusted_external_cache VALUES(?,?,?)", (
                    json.dumps(["tt0903747", 0, 1396, "default", 1, 1, 2700000]),
                    json.dumps({"trusted_segments": [
                        {"segment_type":"intro","source":"introdb","trusted":True,
                         "start_ms":10000,"end_ms":60000},
                        {"segment_type":"outro","source":"theintrodb","trusted":True,
                         "start_ms":2600000,"end_ms":2690000},
                        {"segment_type":"intro","source":"bogus","trusted":True,
                         "start_ms":10000,"end_ms":60000},
                        {"segment_type":"recap","source":"introdb","trusted":False,
                         "start_ms":0,"end_ms":30000}]}), 9999999999))
                db.execute("INSERT INTO trusted_external_cache VALUES(?,?,?)", (
                    json.dumps(["tt0903747", 0, 1396, "aired", 1, 2, 2700000]),
                    json.dumps({"trusted_segments":[{
                        "segment_type":"intro","source":"introdb","trusted":True,
                        "start_ms":0,"end_ms":50000}]}), 9999999999))
            with sqlite3.connect("file:"+str(path)+"?mode=ro",uri=True) as conn:
                conn.row_factory=sqlite3.Row
                count, data=accepted_entries(conn)
            self.assertEqual(count,2)
            self.assertEqual(len(data),1)
            self.assertEqual({m["source"] for m in data[0]["segments"]},
                             {"introdb","theintrodb"})

    def test_titles_only_from_canonical_id_and_matching_cut(self):
        with tempfile.TemporaryDirectory() as tmp:
            dbp = Path(tmp)/"prod.db"
            with sqlite3.connect(dbp) as db:
                db.execute("""CREATE TABLE skip_assets(
                    asset_key TEXT, playlist_id INT, title TEXT, season INT,
                    episode INT, duration_ms INT)""")
                db.execute("""CREATE TABLE skip_records(
                    asset_key TEXT, imdb_id TEXT, tmdb_id INT, status TEXT)""")
                db.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?)",[
                    ("a",8,"Breaking Bad 4K",1,1,2700000),
                    ("b",10,"Breaking Bad Best",1,1,2700500),
                    ("different",8,"Wrong cut",1,1,2600000),
                    ("customer",44,"Customer should not appear",1,1,2700000),
                    ("wrong-id",10,"Wrong ID",1,1,2700000)])
                db.executemany("INSERT INTO skip_records VALUES(?,?,?,?)",[
                    ("a","tt0903747",1396,"approved"),
                    ("b","tt0903747",1396,"approved"),
                    ("different","tt0903747",1396,"approved"),
                    ("customer","tt0903747",1396,"approved"),
                    ("wrong-id","tt0000001",1396,"approved")])
            items=[{"ids":{"imdb_id":"tt0903747","tvdb_id":0,"tmdb_id":1396},
                    "season":1,"episode":1,"duration":2700000,
                    "segments":[],"expires":9999999999}]
            with sqlite3.connect("file:"+str(dbp)+"?mode=ro",uri=True) as conn:
                conn.row_factory=sqlite3.Row
                linked=series_matches(conn,items)
            self.assertEqual(linked[0],{
                ("4K ANALYSE","Breaking Bad 4K"),
                ("THE BEST","Breaking Bad Best")})
            self.assertFalse(canonical_match({"imdb_id":"tt0000001","tmdb_id":1396},
                                             items[0]["ids"]))


if __name__=="__main__":
    unittest.main()
