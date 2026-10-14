"""Synthetic production SQLite tests: one-shot safe manual reconciliation and requeues."""
import json
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import safe_release_rollout as r


def fixture(root):
    path=root/'provisioning.db'
    with sqlite3.connect(path) as db:
        db.executescript("""
        CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,source TEXT,
          source_key TEXT,segment_type TEXT,status TEXT,season INTEGER,episode INTEGER,
          media_type TEXT,title TEXT,start_ms INTEGER,end_ms INTEGER,
          duration_ms INTEGER,disabled INTEGER,device_id INTEGER,customer_id INTEGER);
        CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,
          source_key TEXT,media_type TEXT,season INTEGER,episode INTEGER,title TEXT,
          duration_ms INTEGER,stream_id TEXT,extension TEXT);
        CREATE TABLE devices(id INTEGER PRIMARY KEY,customer_id INTEGER,enabled INTEGER);
        CREATE TABLE customers(id INTEGER PRIMARY KEY,enabled INTEGER);
        CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,customer_id INTEGER,config_json TEXT);
        CREATE TABLE skip_jobs(id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,
          attempts INTEGER,updated_at TEXT,detail TEXT);
        CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
        CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER);
        CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT);
        CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER);
        CREATE TABLE skip_presence(playlist_id INTEGER,expires_at INTEGER);
        INSERT INTO devices VALUES(99,12,1),(55,20,1);
        INSERT INTO customers VALUES(12,1),(20,1);
        INSERT INTO customer_playlists VALUES(8,12,'{}');
        INSERT INTO skip_analysis_sources VALUES(8,1);
        INSERT INTO skip_auto_settings VALUES(8,1);
        """)
        for i in (1,2,3,4):
            db.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?)',
                ('a-'+str(i),8,'series','episode',1,i,'MobLand',2400000,str(i),'mkv'))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (101,'a-1','device','series','intro','pending',1,1,
             'episode','MobLand',30000,60000,2400000,0,99,12))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (102,'a-2','device','series','outro','pending',1,2,
             'episode','MobLand',2300000,2390000,2400000,0,99,12))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (2282,'a-3','device','series','intro','pending',1,3,
             'episode','MobLand',30000,60000,2400000,0,99,12))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (104,'a-4','device','series','intro','pending',1,4,
             'episode','MobLand',30000,60000,2400000,0,55,12))
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (201,'a-4','audio_repetition','series','outro','pending',1,4,
             'episode','MobLand',2330000,2390000,2400000,0,None,None))
        db.execute('INSERT INTO skip_auto_evidence VALUES(201,?)',
                   (json.dumps({'episcene_required':True}),))
        db.execute("INSERT INTO skip_jobs VALUES(501,'a-4','review',3,'2026-10-14','')")

    return path


def connect(path):
    c=sqlite3.connect(path)
    c.row_factory=sqlite3.Row
    return c


class SafeRelease(unittest.TestCase):
    def test_reports_all_reason_codes_without_writing_source(self):
        with tempfile.TemporaryDirectory() as td:
            path=fixture(Path(td))
            before=path.read_bytes()
            with connect(path) as con:
                result=r.run(con,apply=False,validate=lambda row:True)
            self.assertEqual(result['old_manual_pending'],4)
            self.assertEqual(result['eligible_exact_manual_marks'],2)
            self.assertEqual(result['excluded']['KNOWN_INVALID_REFERENCE'],1)
            self.assertEqual(result['excluded']['MISSING_CURRENT_DEVICE_OWNERSHIP'],1)
            self.assertEqual(before,path.read_bytes())

    def test_reconciles_only_owned_manual_then_reruns_unchanged_gates(self):
        with tempfile.TemporaryDirectory() as td:
            path=fixture(Path(td))
            approved=[];wake=[]
            def accept(con):
                self.assertEqual(con.execute("SELECT status FROM skip_records WHERE id=201").fetchone()[0],"pending")
                return 0  # actual production function is imported, never bypassed
            def review(con,marker,action,start,end,disabled,wake=False):
                approved.append(marker['id'])
                con.execute("UPDATE skip_records SET status='approved' WHERE id=?",(marker['id'],))
            modules={
                'skip_markers':types.SimpleNamespace(review_record=review,
                    wake_reference_jobs=lambda con,k,s:wake.append((k,s))),
                'skip_release':types.SimpleNamespace(accept_pending=accept,enabled=lambda con,id:True),
            }
            with mock.patch.dict(sys.modules,modules):
                with connect(path) as con:
                    result=r.run(con,apply=True,validate=lambda row:True)
                    con.commit()
            self.assertEqual(approved,[101,102])
            self.assertEqual(wake,[('series',1)])
            self.assertEqual(result['old_manual_exact_source_approved'],2)
            self.assertEqual(result['machine_approved_by_existing_all_gates'],0)
            self.assertEqual(result['visual_jobs_requeued'],1)
            with connect(path) as con:
                self.assertEqual(con.execute("SELECT status FROM skip_records WHERE id=201").fetchone()[0],'pending')
                self.assertEqual(con.execute("SELECT status FROM skip_records WHERE id=2282").fetchone()[0],'pending')
                self.assertEqual(con.execute("SELECT status FROM skip_jobs WHERE id=501").fetchone()[0],'queued')
                self.assertEqual(con.execute("SELECT COUNT(*) FROM episcene_safe_release_retries").fetchone()[0],1)

    def test_no_approval_when_exact_provider_file_not_verified(self):
        with tempfile.TemporaryDirectory() as td:
            path=fixture(Path(td))
            with connect(path) as con:
                result=r.run(con,apply=False,validate=lambda row:False)
            self.assertEqual(result['eligible_exact_manual_marks'],0)
            self.assertEqual(result['excluded']['UNVERIFIED_PROVIDER_ASSET'],2)

if __name__=='__main__':unittest.main(verbosity=2)
