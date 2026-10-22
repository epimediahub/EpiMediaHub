import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from audit_knowledge_first_live import inspect

class Stub:
    def decide(self,db,job):
        with db() as conn:
            assert conn.execute('SELECT 1 FROM skip_assets WHERE asset_key=?',
                                (job['asset_key'],)).fetchone()
        return {'intro':'introdb','outro':'own'}.get(job['kind'])

class AuditTests(unittest.TestCase):
    def test_no_customer_rows_or_sqlite_writes(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            db=root/'provisioning.db'
            worker=root/'skip_analysis_worker.py'
            helper=root/'episcene_knowledge_first_runtime.py'
            worker.write_text('_epi_kf_install(_epi_sys.modules[__name__])')
            helper.write_text('def decide(*args): return None')
            with sqlite3.connect(db) as conn:
                conn.executescript('''
                    CREATE TABLE skip_assets(asset_key TEXT, playlist_id INT, media_type TEXT);
                    CREATE TABLE skip_jobs(id INT,asset_key TEXT,status TEXT);
                ''')
                conn.executemany('INSERT INTO skip_assets VALUES(?,?,?)',[
                    ('for8',8,'episode'),('for10',10,'episode'),('PRIVATE_CUSTOMER_ASSET_SENTINEL',55,'episode')])
                conn.executemany('INSERT INTO skip_jobs VALUES(?,?,?)',[
                    (1,'for8','queued'),(2,'for10','queued'),(3,'PRIVATE_CUSTOMER_ASSET_SENTINEL','queued')])
            old=db.read_bytes()
            with patch('audit_knowledge_first_live._load_helper',return_value=Stub()):
                result=inspect(db=db,worker=worker,helper=helper)
            self.assertEqual(result['status'],'PREVIEW_COMPLETE')
            self.assertEqual(result['per_playlist']['8']['episodes_sampled'],1)
            self.assertEqual(result['per_playlist']['10']['episodes_sampled'],1)
            self.assertEqual(result['per_playlist']['8']['eligible_preview_by_kind']['intro']['introdb'],1)
            self.assertEqual(result['per_playlist']['10']['eligible_preview_by_kind']['outro']['own'],1)
            self.assertEqual(db.read_bytes(),old)
            self.assertNotIn('PRIVATE_CUSTOMER_ASSET_SENTINEL',str(result))
            self.assertNotIn('for8',str(result))

    def test_missing_original_hook_fails_before_any_reads(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            db=root/'database'
            worker=root/'worker'
            helper=root/'helper'
            db.write_bytes(b'x')
            worker.write_text('def main(): pass')
            helper.write_text('# omitted')
            self.assertEqual(inspect(db=db,worker=worker,helper=helper)['status'],
                             'STOP_WORKER_HOOK_ABSENT')

if __name__=='__main__':
    unittest.main()
