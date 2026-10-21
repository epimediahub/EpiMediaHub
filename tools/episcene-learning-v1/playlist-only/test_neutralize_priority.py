#!/usr/bin/env python3
"""No production credentials/source required for deterministic patch regression."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest import mock
import neutralize_priority as p

SQL="SELECT j.id FROM skip_jobs j LEFT JOIN skip_language_priority l USING(asset_key) WHERE COALESCE(l.priority,2)=? ORDER BY COALESCE(l.priority,2),j.id"

def sample():
    return '\n'.join([
        'def language_stage(con):',
        '    return con.execute("SELECT MIN(COALESCE(l.priority,2)) FROM skip_language_priority l").fetchone()[0]',
        'def request_series(con):',
        '    return 33',
        'def requests(con,stage):',
        '    return con.execute('+repr(SQL)+',(stage,)).fetchall()',
        'def should_pause(con):',
        '    return con.execute('+repr(SQL)+',(2,)).fetchall()',
        'def select_job(con,stage):',
        '    return con.execute('+repr(SQL)+',(stage,)).fetchall()',
        'def lane_stage(con,playlist_id):',
        '    return 0',
        'def untouched():',
        '    return "MUST STAY EXACT"',
        ''])

class NeutralizePriorityTests(unittest.TestCase):
    def test_scheduler_no_language_stage_or_rank_filter(self):
        patched, changed=p.rewrite('skip_schedule.py',sample())
        ast.parse(patched)
        self.assertEqual(set(changed),{'language_stage','lane_stage','requests','select_job','should_pause'})
        self.assertNotIn('COALESCE(l.priority,2)',patched)
        self.assertIn('(0+2)=?',patched)
        self.assertIn('ORDER BY (0+2),j.id',patched)
        namespace={}
        exec(patched,namespace)
        self.assertEqual(namespace['language_stage'](None),2)
        self.assertEqual(namespace['lane_stage'](None,8),2)
        self.assertEqual(namespace['untouched'](),'MUST STAY EXACT')

    def test_priority_source_wrapper_uses_no_preferred_screen(self):
        before='def preferred_keys(con,playlist_id,stage=None):\n    return [42]\n' + \
               'def source_stage(con,playlist_id,fallback):\n    return 0\n'
        result,_=p.rewrite('skip_source_preferences.py',before)
        namespace={}
        exec(result,namespace)
        self.assertEqual(namespace['preferred_keys'](None,8),[])
        self.assertEqual(namespace['source_stage'](None,8,2),2)

    def test_automation_sql_and_catalogue_setters(self):
        auto='def discover_one():\n    sql="ORDER BY COALESCE(l.priority,1)"\n    return sql\n' + \
             'def refresh_online_one():\n    sql="COALESCE(lang.priority,1)"\n    return sql\n'
        result,_=p.rewrite('skip_automation.py',auto)
        self.assertNotIn('priority,1)',result)
        cat='def language_priority(row):\n    return 0\n' + \
            'def step():\n    return "ORDER BY COALESCE(l.priority,2)"\n' + \
            'def set_asset_language(con,asset_key,priority):\n    return priority\n' + \
            'def set_series_language(con,playlist_id,series_id,priority):\n    return priority\n'
        result,_=p.rewrite('skip_catalogue.py',cat)
        scope={}
        exec(result,scope)
        self.assertEqual(scope['language_priority']({}),2)
        self.assertEqual(scope['set_asset_language'](None,'x',0),2)
        self.assertEqual(scope['set_series_language'](None,8,'x',0),2)

    def test_surprise_code_fails_without_change(self):
        with self.assertRaises(p.UnexpectedLiveCode):
            p.rewrite('skip_schedule.py','def unrelated():\n    return 0\n')
        with self.assertRaises(p.UnexpectedLiveCode):
            p.rewrite('skip_automation.py','def discover_one():\n    return 1\ndef refresh_online_one():\n    return 1\n')

    def test_sha_gate_prevents_unreviewed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp)
            for name in p.BASELINE:
                (folder/name).write_text('def arbitrary(): pass\n')
            with self.assertRaisesRegex(p.UnexpectedLiveCode,'DRIFT'):
                p.patch_known_files(folder,verify_sha=True)

if __name__=='__main__':
    unittest.main()
