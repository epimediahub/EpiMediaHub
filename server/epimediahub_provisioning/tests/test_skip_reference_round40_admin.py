"""Tests for exact owner-attested admin review; no customer/provider data needed."""
import json
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import skip_reference_round40_admin as round40


def fixture(root):
    src=root/'server.sqlite3'
    shadow=root/'owner-shadow.sqlite3'
    with sqlite3.connect(src) as db:
        db.executescript("""
          CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,
              source_key TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER);
          CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,source_key TEXT,
              source TEXT,status TEXT,disabled INTEGER,media_type TEXT,segment_type TEXT,
              title TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER,
              start_ms INTEGER,end_ms INTEGER,created_at TEXT);
        """)
        for i in (1,2,3,4,5):
            db.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?)',
                       ('asset-'+str(i),8,'source-key',1,i,2400000))
            db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                       (2200+i,'asset-'+str(i),'source-key','device','pending',0,
                        'episode','outro','MobLand',1,i,2400000,2300000,2390000,
                        '2026-10-14T15:00:00Z'))
        # Out-of-plan machine marker can NEVER be approved by this batch.
        db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (4000,'asset-5','source-key','audio_repetition','pending',0,
                    'episode','intro','MobLand',1,5,2400000,0,20000,'2026-10-14T14:00:00Z'))
        # Duplicate manual correction makes the first intro/outro non-eligible.
        db.execute("INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                   (2282,'asset-2','source-key','device','pending',0,
                    'episode','outro','MobLand',1,2,2400000,2300001,2390000,'2026-10-14T15:00:00Z'))
    with sqlite3.connect(shadow) as db:
        db.execute("""CREATE TABLE owner_attested_round40(
          marker_id INTEGER PRIMARY KEY,ref TEXT,title TEXT,season INTEGER,episode INTEGER,
          playlist_id INTEGER,asset_key TEXT,kind TEXT,start_ms INTEGER,end_ms INTEGER,
          provenance TEXT,verified_backend INTEGER)""")
        for i in (1,2,3,4,5):
            db.execute('INSERT INTO owner_attested_round40 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                       (2200+i,'REF-'+str(i),'mobland',1,i,8,'asset-'+str(i),'outro',
                        2300000,2390000,'owner_chat_batch_attestation_2026_10_14',0))
        # Asset-unlinked owner sample cannot be approved.
        db.execute('INSERT INTO owner_attested_round40 VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   (2291,'REF-34','bridgerton',1,1,None,'orphan','intro',0,20000,
                    'owner_chat_batch_attestation_2026_10_14',0))
    return src,shadow


def read(src,fn):
    db=sqlite3.connect(src)
    db.row_factory=sqlite3.Row
    try:return fn(db)
    finally:db.close()


class ReferenceBatchTests(unittest.TestCase):
    def test_only_exact_nonconflicting_markers_are_eligible(self):
        with tempfile.TemporaryDirectory() as folder:
            src,shadow=fixture(Path(folder))
            r=read(src,lambda db:round40.preview(db,shadow))
            self.assertEqual([i['id'] for i in r['eligible']],[2201,2203,2204,2205])
            self.assertEqual(len(r['excluded']),2)
            self.assertTrue(any('Andere offene' in x['reason'] for x in r['excluded']))
            self.assertTrue(any('Keine Playlist' in x['reason'] for x in r['excluded']))

    def test_snapshot_change_rejects_everything_atomically(self):
        with tempfile.TemporaryDirectory() as folder:
            src,shadow=fixture(Path(folder))
            r=read(src,lambda db:round40.preview(db,shadow))
            with sqlite3.connect(src) as db:
                db.execute('UPDATE skip_records SET end_ms=end_ms-500 WHERE id=2201')
            with self.assertRaises(ValueError):
                read(src,lambda db:round40.execute(db,r['digest'],len(r['eligible']),shadow))
            with sqlite3.connect(src) as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM skip_records WHERE status='approved'").fetchone()[0],0)

    def test_authenticated_confirm_path_is_limited_to_exact_reviewed_batch(self):
        with tempfile.TemporaryDirectory() as folder:
            src,shadow=fixture(Path(folder))
            p=read(src,lambda db:round40.preview(db,shadow))
            approval_ids=[];wakes=[]
            def approve(con,row,action,start,end,disabled,wake=False):
                self.assertEqual(action,'approve')
                self.assertFalse(disabled)
                self.assertFalse(wake)
                approval_ids.append(row['id'])
                con.execute("UPDATE skip_records SET status='approved' WHERE id=?",(row['id'],))
            fake=types.SimpleNamespace(review_record=approve,wake_reference_jobs=lambda con,k:wakes.append(k))
            with mock.patch.dict('sys.modules',{'skip_markers':fake}):
                db=sqlite3.connect(src); db.row_factory=sqlite3.Row
                try:
                    count=round40.execute(db,p['digest'],len(p['eligible']),shadow)
                    db.commit()
                finally:db.close()
            self.assertEqual(count,4)
            self.assertEqual(approval_ids,[2201,2203,2204,2205])
            self.assertEqual(wakes,['source-key'])
            with sqlite3.connect(src) as db:
                self.assertEqual(db.execute('SELECT status FROM skip_records WHERE id=2282').fetchone()[0],'pending')
                self.assertEqual(db.execute('SELECT status FROM skip_records WHERE id=4000').fetchone()[0],'pending')
                self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_reference_round40_admin_audit').fetchone()[0],1)
            self.assertEqual(len(read(src,lambda db:round40.preview(db,shadow))['eligible']),0)

    def test_wrong_provenance_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            src,shadow=fixture(Path(folder))
            with sqlite3.connect(shadow) as db:
                db.execute("UPDATE owner_attested_round40 SET verified_backend=1 WHERE marker_id=2201")
            r=read(src,lambda db:round40.preview(db,shadow))
            self.assertTrue(r['error'])
            self.assertFalse(r['eligible'])


if __name__=='__main__':unittest.main(verbosity=2)
