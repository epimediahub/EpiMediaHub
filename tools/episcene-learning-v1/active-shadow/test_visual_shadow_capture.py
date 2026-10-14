#!/usr/bin/env python3
"""Unit tests: original analyzer SQLite never modified, one 40s window per run."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import visual_shadow_capture as m


def fixture(root):
    source=root/'analyzer.sqlite3'; shadow=root/'shadow.sqlite3'; output=root/'frames.sqlite3'
    with sqlite3.connect(source) as db:
        db.executescript("""
          CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,
          source_key TEXT,title TEXT,media_type TEXT,duration_ms INTEGER,
          season INTEGER,episode INTEGER,stream_id INTEGER,extension TEXT,
          updated_at TEXT,content_version TEXT,etag TEXT);
          CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,
          source TEXT,status TEXT,disabled INTEGER,segment_type TEXT,
          start_ms INTEGER,end_ms INTEGER);
        """)
        for i in range(5):
            asset='mob-'+str(i+2)
            db.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (asset,8,'mobland-key','MobLand','episode',2400000,1,i+2,30+i,'mp4',
                        '2026-10-14',None,None))
            db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?)",
                       (2300+i,asset,'device','pending',0,'outro',2300000,2390000))
        db.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   ('mob-9',8,'mobland-key','MobLand','episode',2400000,1,9,50,'mp4','2026-10-14',None,None))
        db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?)",
                   (1359,'mob-9','audio_repetition','pending',0,'outro',2340000,2390000))
    with sqlite3.connect(shadow) as db:
        db.executescript("""
          CREATE TABLE shadow_outro_models(series TEXT,season INTEGER,playlist_id INTEGER,
          shift_ms INTEGER,reference_episodes INTEGER,status TEXT,publish_allowed INTEGER,source_key TEXT);
          CREATE TABLE owner_attested_round40(marker_id INTEGER,asset_key TEXT,kind TEXT,
          start_ms INTEGER,end_ms INTEGER,playlist_id INTEGER,title TEXT,season INTEGER,episode INTEGER);
          CREATE TABLE shadow_outro_candidates(auto_marker_id INTEGER,asset_key TEXT,
          suggested_start_ms INTEGER,end_ms INTEGER,playlist_id INTEGER,series TEXT,season INTEGER,
          episode INTEGER,status TEXT);
        """)
        db.execute("INSERT INTO shadow_outro_models VALUES('mobland',1,8,35133,5,'shadow_only',0,'mobland-key')")
        for i in range(5):
            db.execute("INSERT INTO owner_attested_round40 VALUES(?,?,?,?,?,?,?,?,?)",
                       (2300+i,'mob-'+str(i+2),'outro',2300000,2390000,8,'mobland',1,i+2))
        db.execute("""INSERT INTO shadow_outro_candidates
                      VALUES(1359,'mob-9',2304867,2390000,8,'mobland',1,9,'SHADOW_REVIEW_ONLY')""")
    return source,shadow,output


class ShadowCaptureSafety(unittest.TestCase):
    def test_only_one_window_per_run_and_production_db_immutable(self):
        with tempfile.TemporaryDirectory() as folder:
            src,shadow,out=fixture(Path(folder))
            before=src.read_bytes()
            calls=[]
            def fake(task,db_factory):
                calls.append(task['record_id'])
                return [[1,2,3,4] for _ in range(80)]
            m.run(src,shadow,out,fetcher=fake)
            self.assertEqual(len(calls),1)
            self.assertEqual(src.read_bytes(),before)
            m.run(src,shadow,out,fetcher=fake)
            self.assertEqual(len(calls),2)
            self.assertNotEqual(calls[0],calls[1])
            with sqlite3.connect(out) as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM frames').fetchone()[0],2)
                self.assertEqual(con.execute("SELECT COUNT(*) FROM frames WHERE status='SHADOW_ONLY'").fetchone()[0],2)
            self.assertEqual(src.read_bytes(),before)

    def test_stale_candidate_cannot_reuse_wrong_asset_revision(self):
        with tempfile.TemporaryDirectory() as folder:
            src,shadow,out=fixture(Path(folder))
            with sqlite3.connect(src) as con:
                con.execute("UPDATE skip_records SET start_ms=start_ms+10000 WHERE id=1359")
            with sqlite3.connect(src.resolve().as_uri()+'?mode=ro',uri=True) as db, \
                 sqlite3.connect(shadow.resolve().as_uri()+'?mode=ro',uri=True) as sh:
                ids={x['record_id'] for x in m.prepare(db,sh)}
            self.assertNotIn(1359,ids)

    def test_disabled_source_record_not_sampled(self):
        with tempfile.TemporaryDirectory() as folder:
            src,shadow,_=fixture(Path(folder))
            with sqlite3.connect(src) as con:
                con.execute("UPDATE skip_records SET disabled=1 WHERE id=2300")
            with sqlite3.connect(src.resolve().as_uri()+'?mode=ro',uri=True) as db, \
                 sqlite3.connect(shadow.resolve().as_uri()+'?mode=ro',uri=True) as sh:
                ids={x['record_id'] for x in m.prepare(db,sh)}
            self.assertNotIn(2300,ids)


if __name__=='__main__': unittest.main(verbosity=2)
