#!/usr/bin/env python3
"""Privacy and read-only regression tests for EpiScene dominant failure audit."""
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from private_failure_reason import job_stats, categories, source_refs

class FailureReasonTest(unittest.TestCase):
    def setup_fixture(self,root):
        dbpath=root/'p.sqlite3'
        conn=sqlite3.connect(dbpath)
        conn.executescript("""
        CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER);
        CREATE TABLE skip_jobs(asset_key TEXT,status TEXT,detail TEXT);
        """)
        for key,playlist,detail in (
            ('key-secret-1',10,'worker unable to continue token=PRIVATE-123'),
            ('key-secret-2',10,'worker unable to continue token=PRIVATE-123'),
            ('key-secret-3',10,'ffmpeg decoder failed with private url'),
            ('key-secret-4',8,'no reference found'),
            ('key-secret-5',88,'unauthorized on private playlist'),
        ):
            conn.execute('INSERT INTO skip_assets VALUES (?,?)',(key,playlist))
            conn.execute('INSERT INTO skip_jobs VALUES (?,?,?)',(key,'failed',detail))
        conn.commit()
        conn.close()
        (root/'skip_analysis_worker.py').write_text("""
def _process_one():
    return 'worker unable to continue token=PRIVATE-123'
""")

        return dbpath

    def test_private_counts_and_worker_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            dbpath=self.setup_fixture(root)
            with sqlite3.connect(dbpath.resolve().as_uri()+'?mode=ro',uri=True) as db:
                result=job_stats(db,source_directory=root)
            best=result['jobs']['10']['failed']
            self.assertEqual(best['total'],3)
            self.assertEqual(best['most_common_pattern_repetitions'],2)
            self.assertEqual(best['different_detail_patterns'],2)
            self.assertEqual(best['dominant_detail_clues'],['NO_KNOWN_CLUE'])
            self.assertEqual(best['dominant_detail_exact_match_in_worker_literals'][0]['locations'][0]['function'],'_process_one')
            self.assertEqual(result['jobs']['8']['failed']['dominant_detail_clues'],['NO_REFERENCE_OR_MATCH'])
            out=json.dumps(result)
            for secret in ('key-secret','token=','PRIVATE-123','private url','unable to continue'):
                self.assertNotIn(secret,out)
            with sqlite3.connect(dbpath) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM skip_jobs').fetchone()[0],5)

    def test_does_not_allow_arbitrary_raw_reason(self):
        self.assertEqual(categories('https://provider/?token=SECRET-NAME'),['NO_KNOWN_CLUE'])
        self.assertIn('EXPLICIT_TIMEOUT',categories('deadline exceeded'))
        self.assertEqual(source_refs('def test():\n x="repeated"\n','repeated')[0]['function'],'test')

    def test_unexpected_schema_fails_closed(self):
        with sqlite3.connect(':memory:') as db:
            with self.assertRaises(RuntimeError):
                job_stats(db,source_directory=Path('/tmp'))

if __name__=='__main__':unittest.main()
