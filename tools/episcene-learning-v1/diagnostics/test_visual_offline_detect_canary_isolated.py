"""Offline tests for cached-only EpiScene visual detector probes.

All datasets are synthetic; no provider requests, real assets, marker writes.
"""
import sqlite3
import unittest
import visual_offline_detect_canary_isolated as probe

def fixture():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.executescript("""
        CREATE TABLE skip_assets(
          asset_key TEXT PRIMARY KEY,source_key TEXT,season INTEGER,episode INTEGER,
          duration_ms INTEGER);
        CREATE TABLE skip_scene_windows(
          id INTEGER PRIMARY KEY,asset_key TEXT,kind TEXT,duration_ms INTEGER,
          created_at INTEGER);
    """)
    c.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?)",[
        ('own','show',1,1,3600000),('peer2','show',1,2,3600000),
        ('peer3','show',1,3,3600000),('other','other_show',1,3,3600000),
    ])
    c.executemany("INSERT INTO skip_scene_windows VALUES(?,?,?,?,?)",[
        (1,'own','intro',3600000,100),
        (2,'peer2','intro',3600000,100),
        (3,'peer3','intro',3600000,100),
        (4,'other','intro',3600000,100),
    ])
    c.commit()
    return c

ROW={'asset_key':'own','segment_type':'intro','start_ms':2000,'end_ms':50000}

class FakeScene:
    @staticmethod
    def _cached_rows(con,asset,kind):
        return con.execute(
            "SELECT * FROM skip_scene_windows WHERE kind=? ORDER BY id",
            (kind,)).fetchall()
    @staticmethod
    def _human_markers(con,peer,kind):
        return []
    @staticmethod
    def _window(cache,asset,trusted=()):
        return (cache['id'],asset['episode'])

class FakeVisual:
    def __init__(self,value):
        self.value=value
        self.calls=[]
    def detect(self,own,partners,kind,busy=None,cache=None):
        self.calls.append((own,partners,kind))
        return self.value

class OfflineVisualTests(unittest.TestCase):
    def test_no_match_and_self_and_cross_series_filtered(self):
        c=fixture(); v=FakeVisual({'status':'NO_MATCH'})
        self.assertEqual(probe.offline_detect_from_cache(c,FakeScene,v,ROW),
                         'LOCAL_NO_MATCH')
        self.assertEqual(len(v.calls),1)
        self.assertEqual(len(v.calls[0][1]),2)
        c.close()

    def test_review_still_review(self):
        c=fixture()
        v=FakeVisual({'status':'REVIEW','ambiguous':True})
        self.assertEqual(probe.offline_detect_from_cache(c,FakeScene,v,ROW),
                         'LOCAL_REVIEW_AMBIGUOUS')
        c.close()

    def test_offline_confirmation_does_not_approve(self):
        c=fixture()
        v=FakeVisual({'status':'AUTO_CONFIRMED','start_ms':2000,'end_ms':50000})
        self.assertEqual(probe.offline_detect_from_cache(c,FakeScene,v,ROW),
                         'LOCAL_AUTO_CONFIRMED_ALIGNED_NOT_RELEASED')
        self.assertEqual(c.execute('SELECT COUNT(*) FROM skip_scene_windows').fetchone()[0],4)
        c.close()

    def test_mismatched_boundaries_not_released(self):
        c=fixture()
        v=FakeVisual({'status':'AUTO_CONFIRMED','start_ms':7000,'end_ms':50000})
        self.assertEqual(probe.offline_detect_from_cache(c,FakeScene,v,ROW),
                         'LOCAL_AUTO_CONFIRMED_BOUNDARIES_DIFFER_NOT_RELEASED')
        c.close()

    def test_missing_own_window_does_not_call_visual(self):
        c=fixture()
        c.execute("DELETE FROM skip_scene_windows WHERE asset_key='own'")
        v=FakeVisual({'status':'AUTO_CONFIRMED'})
        self.assertEqual(probe.offline_detect_from_cache(c,FakeScene,v,ROW),
                         'OWN_WINDOW_MISSING')
        self.assertEqual(v.calls,[])
        c.close()

if __name__=='__main__':
    unittest.main()
