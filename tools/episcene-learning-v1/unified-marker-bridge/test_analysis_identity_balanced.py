"""Independent playback-safe trusted-source prefetch lanes, entirely synthetic."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from analysis_identity_balanced import catalog_batch
from trusted_external_sync import sync
from test_trusted_external import fake_fetch


def make_db(path, n8=0, n10=0, n_private=0):
    with sqlite3.connect(path) as db:
        db.execute("""CREATE TABLE skip_assets(
            asset_key TEXT,playlist_id INT,season INT,episode INT,
            duration_ms INT,imdb_id TEXT,tvdb_id INT)""")
        rows=[]
        for pid,count in ((8,n8),(10,n10),(44,n_private)):
            for i in range(count):
                rows.append((f"asset-{pid}-{i:04d}",pid,1,i+1,
                             2700000,"tt0903747",81189))
        db.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)",rows)


class BalancedCatalogTests(unittest.TestCase):
    def test_first_batch_has_both_providers_even_when_4k_has_100(self):
        with tempfile.TemporaryDirectory() as td:
            prod,cache=Path(td)/'prod.sqlite3',Path(td)/'cache.sqlite3'
            make_db(prod,100,20,20)
            original=prod.read_bytes()
            rows,status,meta=catalog_batch(prod,cache,limit=10)
            self.assertEqual(status,'ok')
            self.assertEqual(meta['per_playlist_candidates'],{'8':5,'10':5})
            self.assertEqual([r['playlist_id'] for r in rows].count(8),5)
            self.assertEqual([r['playlist_id'] for r in rows].count(10),5)
            self.assertEqual(prod.read_bytes(),original)
            self.assertFalse(any(r['playlist_id']==44 for r in rows))

    def test_cursors_advance_independently_between_syncs(self):
        with tempfile.TemporaryDirectory() as td:
            prod,cache=Path(td)/'prod.sqlite3',Path(td)/'cache.sqlite3'
            make_db(prod,40,20)
            a=sync(prod,cache,limit=6,fetch=fake_fetch)
            b=sync(prod,cache,limit=6,fetch=fake_fetch)
            self.assertEqual(a['analysis_playlist_candidates'],{'8':3,'10':3})
            self.assertEqual(b['analysis_playlist_candidates'],{'8':3,'10':3})
            with sqlite3.connect(cache) as c:
                last=dict(c.execute("SELECT playlist_id,asset_key "
                                    "FROM trusted_source_balanced_cursor"))
            self.assertEqual(last[8],"asset-8-0005")
            self.assertEqual(last[10],"asset-10-0005")

    def test_single_slot_alternates_between_both_playlists(self):
        with tempfile.TemporaryDirectory() as td:
            prod,cache=Path(td)/'prod.sqlite3',Path(td)/'cache.sqlite3'
            make_db(prod,20,20)
            first=sync(prod,cache,limit=1,fetch=fake_fetch)
            second=sync(prod,cache,limit=1,fetch=fake_fetch)
            self.assertEqual(first['analysis_playlist_candidates'],{'8':1,'10':0})
            self.assertEqual(second['analysis_playlist_candidates'],{'8':0,'10':1})

    def test_spare_quota_returns_to_existing_provider(self):
        with tempfile.TemporaryDirectory() as td:
            prod,cache=Path(td)/'prod.sqlite3',Path(td)/'cache.sqlite3'
            make_db(prod,30,0)
            report=sync(prod,cache,limit=10,fetch=fake_fetch)
            self.assertEqual(report['analysis_playlist_candidates'],{'8':10,'10':0})

    def test_legacy_cursor_progress_retained_and_the_best_starts(self):
        with tempfile.TemporaryDirectory() as td:
            prod,cache=Path(td)/'prod.sqlite3',Path(td)/'cache.sqlite3'
            make_db(prod,20,10)
            with sqlite3.connect(cache) as conn:
                conn.execute("""CREATE TABLE trusted_source_sync_cursor(
                    singleton INT PRIMARY KEY,playlist_id INT,asset_key TEXT)""")
                conn.execute("INSERT INTO trusted_source_sync_cursor VALUES(1,8,'asset-8-0005')")
            rows,status,meta=catalog_batch(prod,cache,limit=4)
            self.assertEqual(status,'ok')
            ids={8:[],10:[]}
            for r in rows:
                ids[r['playlist_id']].append(r['asset_key'])
            self.assertEqual(ids[8],["asset-8-0006","asset-8-0007"])
            self.assertEqual(ids[10],["asset-10-0000","asset-10-0001"])
            self.assertEqual(meta['per_playlist_candidates'],{'8':2,'10':2})


if __name__=='__main__':
    unittest.main()
