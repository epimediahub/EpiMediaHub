"""Tests for trusted external background prefetch using synthetic analysis DB."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from trusted_external_sync import catalog_batch, sync
from test_trusted_external import fake_fetch

class TrustedPrefetchTests(unittest.TestCase):
    def test_reads_only_analysis_ids_with_real_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            catalog, cache = root/"catalog.sqlite3", root/"trusted.sqlite3"
            with sqlite3.connect(catalog) as db:
                db.execute("""CREATE TABLE skip_assets(
                    asset_key TEXT,playlist_id INT,season INT,episode INT,
                    duration_ms INT,imdb_id TEXT,tvdb_id INT)""")
                db.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)",[
                    ("s01",8,1,1,2700000,"tt0903747",81189),
                    ("s02",10,1,1,2700000,"tt0903747",81189),
                    ("private-should-not-read",44,1,1,2700000,"tt0903747",81189)])
            before = catalog.read_bytes()
            calls = []
            def fetched(url):
                calls.append(url)
                return fake_fetch(url)
            report=sync(catalog,cache,fetch=fetched,limit=1)
            self.assertEqual(report["analysed"],1)
            self.assertEqual(report["trusted_segments"],3)
            report=sync(catalog,cache,fetch=fetched,limit=1)
            self.assertEqual(report["analysed"],1)
            self.assertEqual(report["trusted_segments"],3)
            self.assertEqual(len(calls),2) # same identity across providers -> cached
            self.assertEqual(catalog.read_bytes(),before)
            self.assertTrue(report["no_customer_playlists_scanned"])
            self.assertTrue(report["no_ip_streams_opened"])

    def test_missing_ids_safe_stop(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            dbp, cache = root/"catalog.sqlite3", root/"trusted.sqlite3"
            with sqlite3.connect(dbp) as db:
                db.execute("""CREATE TABLE skip_assets(
                    asset_key TEXT,playlist_id INT,season INT,episode INT,
                    duration_ms INT)""")
            report = sync(dbp,cache,fetch=lambda _url:self.fail("Must not fetch"))
            self.assertEqual(report["status"],"missing_canonical_external_ids")
            self.assertFalse(cache.exists())

    def test_cursor_wraps_and_reuses_cache(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            dbp, cache=root/"catalog.sqlite3",root/"cache.sqlite3"
            with sqlite3.connect(dbp) as db:
                db.execute("""CREATE TABLE skip_assets(
                    asset_key TEXT,playlist_id INT,season INT,episode INT,
                    duration_ms INT,imdb_id TEXT)""")
                db.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?)",
                           ("only",8,1,1,2700000,"tt0903747"))
            r=sync(dbp,cache,fetch=fake_fetch,limit=1)
            self.assertEqual(r["analysed"],1)
            r=sync(dbp,cache,fetch=lambda _url:self.fail("Should be cached"),limit=1)
            self.assertEqual(r["analysed"],1)

if __name__=="__main__":
    unittest.main()
