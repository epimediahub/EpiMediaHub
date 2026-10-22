"""Private read-only lookup canary checks, entirely synthetic."""
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from canary_trusted_lookup import canary
from test_production_lookup_cache import make_cache


class CanaryTests(unittest.TestCase):
    def test_canary_reports_counts_and_preserves_source(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            prod=root/"provisioning.db"
            cache=root/"trusted-sources.sqlite3"
            with sqlite3.connect(prod) as db:
                db.execute("""CREATE TABLE skip_assets(
                    playlist_id INT, asset_key TEXT, source_key TEXT,
                    season INT, episode INT, duration_ms INT)""")
                db.execute("""CREATE TABLE skip_records(
                    id INT, asset_key TEXT, status TEXT,
                    imdb_id TEXT, tmdb_id INT)""")
                db.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?)", [
                    (8,"e1","src1",1,1,2700000),
                    (10,"e2","src2",1,1,2700000),
                    (55,"customer","cust",1,1,2700000)])
                db.executemany("INSERT INTO skip_records VALUES(?,?,?,?,?)", [
                    (1,"e1","approved","tt0903747",1396),
                    (2,"e2","approved","tt0903747",1396),
                    (3,"customer","approved","tt0903747",1396)])
            make_cache(cache)
            before=prod.read_bytes(),cache.read_bytes()
            result=canary(prod=prod,cache=cache,private=root)
            self.assertEqual(result["status"],"SHADOW_CHECK_COMPLETE")
            self.assertEqual(result["episodes_evaluated"],2)
            self.assertEqual(result["episodes_with_trusted_segments"],2)
            self.assertEqual(result["external_segments_ready"],4)
            self.assertFalse(result["customer_lookup_proven"])
            self.assertEqual((prod.read_bytes(),cache.read_bytes()),before)

    def test_missing_live_cache_safe_stop(self):
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)
            result=canary(prod=p/"no.db",cache=p/"no_cache",private=p)
            self.assertEqual(result["status"],"STOP_REQUIRED_INPUT_MISSING")
            self.assertEqual(result["external_network_calls"],0)


if __name__ == "__main__":
    unittest.main()
