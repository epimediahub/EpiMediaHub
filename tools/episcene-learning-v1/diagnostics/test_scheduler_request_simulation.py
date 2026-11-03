"""Small offline regression checks for guarded EpiScene scheduler simulation."""
import ast
import sqlite3
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch
import scheduler_request_simulation as sim

EXAMPLE = '''def select_job(con, playlist_id, excluded=(), *, stage=None, parallel=False):
    best=con.execute("SELECT asset_key, source_key FROM jobs WHERE playlist_id=? ORDER BY id LIMIT 1",(playlist_id,)).fetchone()
    request=next((r for r in requests(con, stage) if r["playlist_id"]==playlist_id),None)
    if request:
        best=con.execute("SELECT asset_key, source_key FROM jobs WHERE asset_key=?",(request["reference_asset"],)).fetchone()
    return best, ""
'''

def db():
    con=sqlite3.connect(':memory:')
    con.row_factory=sqlite3.Row
    con.execute('CREATE TABLE jobs(id INTEGER,playlist_id INTEGER,asset_key TEXT,source_key TEXT)')
    con.executemany('INSERT INTO jobs VALUES(?,?,?,?)',
                    [(1,8,'other','series_other'),(2,8,'canary','series_canary')])
    return con


class SchedulerSimulationTests(TestCase):
    def test_request_override_is_not_applied_to_live_db(self):
        fn=ast.parse(EXAMPLE).body[0]
        con=db()
        con.execute('PRAGMA query_only=ON')
        base=sim.simulation_fn(fn,lambda _con,_stage: [])
        requested=sim.simulation_fn(fn,lambda _con,_stage:[{
            'playlist_id':8,'reference_asset':'canary'}])
        first,_=base(con,8,stage=2,parallel=True)
        second,_=requested(con,8,stage=2,parallel=True)
        self.assertEqual(first['asset_key'],'other')
        self.assertEqual(second['asset_key'],'canary')
        self.assertEqual(con.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],2)
        con.close()

    def test_rejects_mutating_selector(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'skip_schedule.py'
            target.write_text(EXAMPLE.replace('SELECT asset_key, source_key',
                                              'UPDATE jobs SET source_key=source_key'))
            with patch.object(sim,'APP',target):
                with self.assertRaisesRegex(RuntimeError,'Unexpected SQL'):
                    sim.load_selector()

    def test_rejects_side_effect_import(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'skip_schedule.py'
            target.write_text(EXAMPLE.replace('    best=', '    import os\n    best=',1))
            with patch.object(sim,'APP',target):
                with self.assertRaisesRegex(RuntimeError,'unsupported import'):
                    sim.load_selector()


if __name__=='__main__':
    main()
