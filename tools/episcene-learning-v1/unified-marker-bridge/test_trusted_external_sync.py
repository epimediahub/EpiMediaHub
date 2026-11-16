"""Tests for trusted external background prefetch using synthetic analysis DB."""
import gzip
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from catalogue_sources import CatalogueSources, load_introdb_export
from trusted_external_sync import catalog_batch, scan_catalogue, sync
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


class CatalogueSourcesTests(unittest.TestCase):
    def test_snapshot_uses_one_day_and_reuses_the_cached_pair(self):
        downloads = []

        def download(url):
            downloads.append(url)
            if url.endswith("segmentless.csv.gz"):
                csv = "imdb_id,is_movie,season,episode,segment,updated_at\n"
                csv += "tt0903747,f,1,1,recap,2026-11-16\n"
            else:
                csv = "imdb_id,is_movie,season,episode,segment,start_ms,end_ms\n"
                csv += "tt0903747,f,1,1,intro,10000,30000\n"
                csv += "tt0000001,t,0,0,outro,50000,60000\n"
            return gzip.compress(csv.encode())

        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "introdb.zip"
            index = load_introdb_export(path, download=download)
            self.assertEqual(index, {("tt0903747", 1, 1): {
                "intro": {"start_ms": 10000, "end_ms": 30000}, "no_recap": True}})
            self.assertEqual(len(downloads), 2)
            self.assertEqual(downloads[0].rsplit("/", 1)[0],
                             downloads[1].rsplit("/", 1)[0])
            reused = load_introdb_export(path, download=lambda _: self.fail("reused bundle"))
            self.assertEqual(reused, index)

    def make_catalogue(self, path):
        with sqlite3.connect(path) as db:
            db.execute("""CREATE TABLE skip_assets(
                asset_key TEXT,playlist_id INT,season INT,episode INT,
                duration_ms INT,imdb_id TEXT,tvdb_id INT)""")
            db.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)", [
                ("a", 8, 1, 1, 2700000, "tt0903747", 81189),
                ("b", 10, 1, 2, 2700000, "tt0903747", 81189),
                ("c", 8, 2, 1, 2700000, "tt0903747", 81189),
                ("d", 8, 3, 1, 2700000, "tt0903747", 81189),
            ])

    def test_iterates_catalogue_and_only_requests_details_for_covered_episode(self):
        calls = []

        def fetched(url):
            self.assertIn("api.theintrodb.org", url)
            calls.append(url)
            if "duration_ms=" not in url:
                return {"status": "ok", "data": {"type": "tv", "tvdb_id": 81189,
                    "episodes": [{"season": 1, "episode": 1, "intro_accepted_count": 0,
                                  "recap_accepted_count": 0, "credits_accepted_count": 1}]}}
            self.assertIn("duration_ms=2700000", url)
            self.assertIn("season=1&episode=1", url)
            return {"status": "ok", "data": {"tvdb_id": 81189, "season": 1, "episode": 1,
                    "group_duration_ms": 2700000, "credits": [{"start_ms": 2500000, "end_ms": None}]}}

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prod, cache = root / "prod.sqlite3", root / "cache.sqlite3"
            self.make_catalogue(prod)
            before = prod.read_bytes()
            transport = CatalogueSources(cache, fetch=fetched, introdb_loader=lambda _: {
                ("tt0903747", 2, 1): {"intro": {"start_ms": 10000, "end_ms": 35000}}
            })
            report = scan_catalogue(prod, cache, limit=1, batches=6, transport=transport)
            self.assertEqual(report["analysed"], 4)
            self.assertEqual(report["markers_by_source"], {"introdb": 1, "theintrodb": 1})
            self.assertEqual(len(calls), 2)
            self.assertEqual(prod.read_bytes(), before)
            with sqlite3.connect(cache) as db:
                cached = [json.loads(row[0]) for row in db.execute(
                    "SELECT response FROM trusted_external_cache")]
            self.assertEqual(len(cached), 4)

    def test_rate_limit_keeps_the_incomplete_batch_available_for_retry(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            prod, cache = root / "prod.sqlite3", root / "cache.sqlite3"
            self.make_catalogue(prod)
            first = CatalogueSources(cache, fetch=lambda _: {"status": "rate_limited"},
                                     introdb_loader=lambda _: {})
            blocked = scan_catalogue(prod, cache, limit=1, batches=5, transport=first)
            self.assertEqual(blocked["status"], "theintrodb_paused")
            with sqlite3.connect(cache) as db:
                self.assertFalse(db.execute("SELECT 1 FROM trusted_source_balanced_cursor").fetchone())
                self.assertFalse(db.execute("SELECT 1 FROM trusted_external_cache").fetchone())
            second = CatalogueSources(cache, fetch=fake_fetch, introdb_loader=lambda _: {})
            retried = scan_catalogue(prod, cache, limit=1, batches=1, transport=second)
            self.assertEqual(retried["analysed"], 1)
            self.assertEqual(retried["markers_by_source"]["theintrodb"], 2)


if __name__=="__main__":
    unittest.main()
