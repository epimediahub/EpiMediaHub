"""Offline tests for cached-only EpiScene visual detector probes.

All datasets are synthetic; no provider requests, real assets, marker writes.
"""
import sqlite3
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock
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


class ExplicitVisualImportTests(unittest.TestCase):
    MODULE_ALIAS='episcene_offline_visual_probe_private'

    def tearDown(self):
        sys.modules.pop(self.MODULE_ALIAS,None)

    def test_explicit_import_ignores_previously_cached_skip_visual(self):
        with TemporaryDirectory() as folder:
            source=Path(folder)/'skip_visual.py'
            source.write_text(
                "POLICY='episcene_visual_v1'\ndef detect(*args,**kwargs):\n    return {'status':'NO_MATCH'}\n"
            )
            fake=object()
            with mock.patch.dict(sys.modules,{'skip_visual':fake}):
                actual=probe.load_compute_visual(Path(folder))
                self.assertEqual(actual.__file__,str(source))
                self.assertEqual(actual.POLICY,'episcene_visual_v1')
                self.assertIs(sys.modules['skip_visual'],fake)
                self.assertIsNot(actual,fake)

    def test_unknown_local_policy_is_rejected_and_alias_cleared(self):
        with TemporaryDirectory() as folder:
            source=Path(folder)/'skip_visual.py'
            source.write_text(
                "POLICY='old_visual_policy'\ndef detect(*args,**kwargs):\n    return {}\n"
            )
            with self.assertRaisesRegex(RuntimeError,'Unexpected local visual policy'):
                probe.load_compute_visual(Path(folder))
            self.assertNotIn(self.MODULE_ALIAS,sys.modules)

    def test_symlinked_visual_module_is_rejected(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            real=root/'actual.py'
            real.write_text("POLICY='episcene_visual_v1'\ndef detect(*a,**k): return {}\n")
            (root/'skip_visual.py').symlink_to(real)
            with self.assertRaisesRegex(RuntimeError,'symlink'):
                probe.load_compute_visual(root)
            self.assertNotIn(self.MODULE_ALIAS,sys.modules)



class VisualTraceSafetyTests(unittest.TestCase):
    def test_trace_rejects_unknown_visual_without_running_detector(self):
        v=FakeVisual({'status':'AUTO_CONFIRMED'})
        with self.assertRaisesRegex(RuntimeError,'Visual pair candidate function unavailable'):
            probe.trace_local_visual(v, (1,1), [(2,2)], 'intro', {})
        self.assertEqual(v.calls,[])

    def test_trace_rejects_unverified_line_mapping(self):
        class FakeLocalVisual:
            __file__=__file__
            @staticmethod
            def _pair_candidates(*args):
                return []
            @staticmethod
            def detect(*args,**kwargs):
                return {'status':'NO_MATCH'}
        with self.assertRaisesRegex(RuntimeError,'Visual algorithm changed'):
            probe.trace_local_visual(FakeLocalVisual,(1,1),[(2,2)],'intro',{})



class WindowCaptureCoverageTests(unittest.TestCase):
    def _conn(self,offset,length):
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.execute("CREATE TABLE skip_assets (asset_key TEXT,duration_ms INTEGER)")
        c.execute("INSERT INTO skip_assets VALUES('x',3600000)")
        c.execute("""CREATE TABLE skip_scene_windows(
            asset_key TEXT,kind TEXT,duration_ms INTEGER,
            offset_ms INTEGER,length_ms INTEGER,step_ms INTEGER,created_at INTEGER)""")
        c.execute("INSERT INTO skip_scene_windows VALUES('x','intro',3600000,?,?,500,1)",
                  (offset,length))
        c.commit()
        return c

    def test_full_audio_marker_coverage(self):
        c=self._conn(0,100000)
        self.assertEqual(probe.capture_span_profile(c,{'asset_key':'x','segment_type':'intro',
                         'start_ms':25000,'end_ms':60000}),
                         'OWN_WINDOW_COVERS_ENTIRE_AUDIO_MARKER')
        c.close()

    def test_partial_audio_marker_coverage(self):
        c=self._conn(0,35000)
        self.assertEqual(probe.capture_span_profile(c,{'asset_key':'x','segment_type':'intro',
                         'start_ms':25000,'end_ms':60000}),
                         'OWN_WINDOW_ENDS_BEFORE_AUDIO_MARKER')
        c.close()

    def test_window_shorter_than_fifteen_seconds(self):
        c=self._conn(0,10000)
        self.assertEqual(probe.capture_span_profile(c,{'asset_key':'x','segment_type':'intro',
                         'start_ms':1000,'end_ms':8000}),
                         'CACHE_WINDOW_SHORTER_THAN_15S')
        c.close()

    def test_missing_window_is_reported_without_write(self):
        c=self._conn(0,100000)
        c.execute("DELETE FROM skip_scene_windows")
        c.execute("PRAGMA query_only=ON")
        self.assertEqual(probe.capture_span_profile(c,{'asset_key':'x','segment_type':'intro',
                         'start_ms':5000,'end_ms':55000}),
                         'OWN_VISUAL_WINDOW_MISSING')
        c.close()


class GapDirectionTests(unittest.TestCase):
    def _conn(self,offset,length):
        c=sqlite3.connect(':memory:')
        c.row_factory=sqlite3.Row
        c.execute('CREATE TABLE skip_assets(asset_key TEXT,duration_ms INTEGER)')
        c.execute("INSERT INTO skip_assets VALUES('ep',3600000)")
        c.execute('''CREATE TABLE skip_scene_windows(
          asset_key TEXT,kind TEXT,duration_ms INTEGER,offset_ms INTEGER,
          length_ms INTEGER,created_at INTEGER)''')
        c.execute("INSERT INTO skip_scene_windows VALUES('ep','outro',3600000,?,?,1)",
                  (offset,length))
        return c
    def test_window_before_audio_marker(self):
        c=self._conn(2000000,40000)
        row={'asset_key':'ep','segment_type':'outro',
             'start_ms':2600000,'end_ms':2660000}
        self.assertEqual(probe.gap_direction_bucket(c,row),
                         'WINDOW_BEFORE_AUDIO_GAP_OVER_5MIN')
        c.close()
    def test_window_after_audio_marker(self):
        c=self._conn(2800000,40000)
        row={'asset_key':'ep','segment_type':'outro',
             'start_ms':2600000,'end_ms':2660000}
        self.assertEqual(probe.gap_direction_bucket(c,row),
                         'WINDOW_AFTER_AUDIO_GAP_1_TO_5MIN')
        c.close()
    def test_window_overlap_audio_marker(self):
        c=self._conn(2580000,80000)
        row={'asset_key':'ep','segment_type':'outro',
             'start_ms':2600000,'end_ms':2660000}
        self.assertEqual(probe.gap_direction_bucket(c,row),
                         'WINDOW_OVERLAPS_AUDIO')
        c.close()

if __name__=='__main__':
    unittest.main()
