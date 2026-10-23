#!/usr/bin/env python3
"""Offline tests for retiring exactly the obsolete Riverdale analysis edition."""
from pathlib import Path
import sqlite3
import tempfile
import unittest

import retire_stale_riverdale as m

SCHEMA="""
CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY, playlist_id INTEGER,
  season INTEGER, episode INTEGER, media_type TEXT,title TEXT);
CREATE TABLE skip_jobs(id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,
  detail TEXT,updated_at TEXT);
CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,asset_key TEXT,
  series_id TEXT);
CREATE TABLE skip_records(asset_key TEXT,status TEXT,source TEXT);
"""

class RetireTests(unittest.TestCase):
    def fixture(self,path):
        db=sqlite3.connect(path)
        db.row_factory=sqlite3.Row
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO skip_assets VALUES (?,?,?,?,?,?)",[
            ('old_6',10,7,6,'episode','Riverdale'),
            ('old_7',10,7,7,'episode','GER | Riverdale'),
            ('old_done',10,6,1,'episode','Riverdale'),
            ('italian_6',10,7,6,'episode','ITA | Riverdale'),
            ('different',10,1,1,'episode','Berlino'),
            ('another_playlist',8,7,6,'episode','Riverdale')])
        db.executemany("INSERT INTO skip_catalogue_episodes VALUES (?,?,?)",[
            (10,'old_6','777'),(10,'old_7','777'),(10,'old_done','777'),
            (10,'italian_6','888'),(10,'different','999'),
            (8,'another_playlist','777')])
        db.executemany("INSERT INTO skip_jobs VALUES (?,?,?,?,?)",[
            (1,'old_6','failed','Anbieter meldet HTTP 405','2026-10-22'),
            (2,'old_7','queued','','2026-10-22'),
            (3,'old_done','done','verified','2026-10-22'),
            (4,'italian_6','queued','','2026-10-22'),
            (5,'different','failed','different cause','2026-10-22'),
            (6,'another_playlist','failed','HTTP 405','2026-10-22')])
        db.execute("INSERT INTO skip_records VALUES('old_6','approved','device')")
        db.commit()
        return db

    def test_retire_only_old_series_and_keep_marker(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=self.fixture(Path(tmp)/'database.db')
            sid,ids,statuses=m.plan(db)
            self.assertEqual(sid,'777')
            self.assertEqual(ids,[1,2])
            self.assertEqual(statuses['done'],1)
            self.assertEqual(m.apply(db,sid,ids),2)
            self.assertEqual([tuple(row) for row in db.execute(
                'SELECT id,status FROM skip_jobs ORDER BY id')],[
                (1,'disabled'),(2,'disabled'),(3,'done'),(4,'queued'),
                (5,'failed'),(6,'failed')])
            self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_assets').fetchone()[0],6)
            self.assertEqual(m.plan(db)[1],[])

    def test_refuse_ambiguous_series_for_same_asset(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=self.fixture(Path(tmp)/'database.db')
            db.execute("INSERT INTO skip_catalogue_episodes VALUES(10,'old_7','888')")
            with self.assertRaisesRegex(RuntimeError,'MULTIPLE_LANGUAGE_SERIES'):
                m.plan(db)

    def test_refuse_other_title_under_stale_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=self.fixture(Path(tmp)/'database.db')
            db.execute("INSERT INTO skip_catalogue_episodes VALUES(10,'different','777')")
            with self.assertRaisesRegex(RuntimeError,'SHARED_WITH_OTHER_TITLE'):
                m.plan(db)

    def test_backup_is_complete_and_private(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'database.db'
            db=self.fixture(path);db.close()
            old_db,old_folder=m.DB,m.BACKUPS
            try:
                m.DB=path
                m.BACKUPS=Path(tmp)/'backups'
                backup=m.backup()
                self.assertEqual(backup.stat().st_mode & 0o077,0)
                with sqlite3.connect(backup) as con:
                    self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],1)
                    self.assertEqual(con.execute('PRAGMA quick_check').fetchone()[0],'ok')
            finally:
                m.DB,m.BACKUPS=old_db,old_folder

if __name__=='__main__':
    unittest.main()
