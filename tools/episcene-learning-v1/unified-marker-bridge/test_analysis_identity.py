"""Realistic identity-table fixture tests for EpiScene trusted source prefetch."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from analysis_identity import catalog_batch
from bridge import Episode
from trusted_external_sync import sync


def make_database(path):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE skip_assets(
            asset_key TEXT, source_key TEXT, playlist_id INTEGER,
            season INTEGER,episode INTEGER,duration_ms INTEGER,title TEXT)""")
        db.execute("""CREATE TABLE skip_records(
            id INTEGER,asset_key TEXT,status TEXT,imdb_id TEXT,tmdb_id INTEGER)""")
        db.execute("""CREATE TABLE skip_identities(
            source_key TEXT, imdb_id TEXT,tmdb_id INTEGER)""")
        db.execute("""CREATE TABLE skip_auto_identities(
            asset_key TEXT, imdb_id TEXT,tmdb_id INTEGER)""")


class AnalysisIdentityTests(unittest.TestCase):
    def test_existing_skip_records_join_and_no_customer_data(self):
        with tempfile.TemporaryDirectory() as td:
            dbp, cache = Path(td)/"original.db", Path(td)/"cache.db"
            make_database(dbp)
            with sqlite3.connect(dbp) as db:
                db.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)", [
                    ("s01","series-a",8,1,1,2700000,"Example"),
                    ("s10","series-b",10,1,1,2700000,"Example"),
                    ("private","series-c",44,1,1,2700000,"Customer")])
                db.executemany("INSERT INTO skip_records VALUES(?,?,?,?,?)", [
                    (1,"s01","approved","tt0903747",1396),
                    (2,"s10","approved","tt0903747",1396),
                    (3,"private","approved","tt0903747",1396)])
            before=dbp.read_bytes()
            rows,status,meta=catalog_batch(dbp,cache,limit=40)
            self.assertEqual(status,"ok")
            self.assertEqual(meta["candidates"],2)
            self.assertEqual({r["playlist_id"] for r in rows},{8,10})
            self.assertEqual({r["tmdb_id"] for r in rows},{1396})
            self.assertEqual({r["imdb_id"] for r in rows},{"tt0903747"})
            self.assertEqual(dbp.read_bytes(),before)

    def test_series_source_key_and_asset_key_are_exact(self):
        with tempfile.TemporaryDirectory() as td:
            dbp,cache=Path(td)/"original.db",Path(td)/"private.db"
            make_database(dbp)
            with sqlite3.connect(dbp) as db:
                db.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)",
                           ("a1","series-id-1",8,2,3,2660000,"Other title"))
                db.execute("INSERT INTO skip_identities VALUES(?,?,?)",
                           ("series-id-1","tt0903747",1396))
                db.execute("INSERT INTO skip_auto_identities VALUES(?,?,?)",
                           ("a1","tt0903747",1396))
            rows,status,meta=catalog_batch(dbp,cache)
            self.assertEqual((status,len(rows),meta["conflicts"]),("ok",1,0))
            self.assertEqual((rows[0]["season"],rows[0]["episode"]),(2,3))

    def test_conflicts_fail_closed_and_advance_cursor(self):
        with tempfile.TemporaryDirectory() as td:
            dbp,cache=Path(td)/"original.db",Path(td)/"private.db"
            make_database(dbp)
            with sqlite3.connect(dbp) as db:
                db.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)",[
                    ("a","series-a",8,1,1,2700000,"A"),
                    ("b","series-b",8,1,1,2700000,"B")])
                db.execute("INSERT INTO skip_identities VALUES(?,?,?)",
                           ("series-a","tt0903747",1396))
                db.execute("INSERT INTO skip_auto_identities VALUES(?,?,?)",
                           ("a","tt0903747",9999))
                db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?)",
                           (1,"b","approved","tt0903747",1396))
            rows,status,meta=catalog_batch(dbp,cache,limit=1)
            self.assertEqual(rows,[])
            self.assertEqual(meta["conflicts"],1)
            # Full sync must move past conflicted chunk instead of looping.
            first=sync(dbp,cache,limit=1,
                       fetch=lambda _: self.fail("No lookup for conflict"))
            self.assertEqual(first["identity_conflicts_skipped"],1)
            urls=[]
            def fetch(url):
                urls.append(url)
                if "introdb.app" in url:
                    return {"status":"ok","data":{
                        "intro":{"start_ms":1000,"end_ms":50000}}}
                return {"status":"ok","data":{
                    "kind":"media","intro":[{"start_ms":1000,"end_ms":50000}]}}
            second=sync(dbp,cache,limit=1,fetch=fetch)
            self.assertEqual(second["analysed"],1)
            self.assertEqual(len(urls),2)

    def test_tmdb_without_imdb_uses_theintrodb_v4(self):
        with tempfile.TemporaryDirectory() as td:
            dbp,cache=Path(td)/"original.db",Path(td)/"private.db"
            make_database(dbp)
            with sqlite3.connect(dbp) as db:
                db.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)",
                           ("a","series-a",10,1,1,2700000,"title"))
                db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?)",
                           (1,"a","approved",None,1396))
            urls=[]
            def fetch(url):
                urls.append(url)
                return {"status":"ok","data":{"kind":"media","tmdb_id":1396,
                    "intro":[{"start_ms":1000,"end_ms":60000}]}}
            result=sync(dbp,cache,fetch=fetch)
            self.assertEqual(result["analysed"],1)
            self.assertEqual(result["trusted_segments"],1)
            self.assertEqual(len(urls),1)
            self.assertEqual(urlparse(urls[0]).path,"/v4/media")
            self.assertEqual(parse_qs(urlparse(urls[0]).query)["tmdb_id"],["1396"])

    def test_rejected_record_not_used_as_identity(self):
        with tempfile.TemporaryDirectory() as td:
            dbp,cache=Path(td)/"original.db",Path(td)/"private.db"
            make_database(dbp)
            with sqlite3.connect(dbp) as db:
                db.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)",
                           ("a","series-a",8,1,1,2700000,"title"))
                db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?)",
                           (1,"a","rejected","tt0903747",1396))
            rows,status,_=catalog_batch(dbp,cache)
            self.assertEqual(rows,[])
            self.assertEqual(status,"no_episodes_with_identifiers")

    def test_missing_all_identity_tables_still_blocks(self):
        with tempfile.TemporaryDirectory() as td:
            dbp,cache=Path(td)/"original.db",Path(td)/"private.db"
            with sqlite3.connect(dbp) as db:
                db.execute("""CREATE TABLE skip_assets(asset_key TEXT,playlist_id INT,
                  season INT,episode INT,duration_ms INT)""")
            rows,status,_=catalog_batch(dbp,cache)
            self.assertEqual(rows,[])
            self.assertEqual(status,"missing_canonical_external_ids")
            self.assertFalse(cache.exists())

if __name__=="__main__":
    unittest.main()
