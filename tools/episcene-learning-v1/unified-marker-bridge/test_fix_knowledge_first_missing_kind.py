#!/usr/bin/env python3
"""Regression tests for the optional Knowledge First missing-kind fallback."""
from contextlib import contextmanager
import sqlite3
import unittest

import fix_knowledge_first_missing_kind as fix

SOURCE = '''def decide(db, job):
    with db() as con:
        kind = job['kind']
        return 'own' if kind == 'intro' else None

def install(mod):
    decider = decide
    original = mod.analyze
    def wrapped(db, job):
        source = decider(db, job)
        if source == 'own':
            return 'knowledge_used'
        return original(db, job)
    mod.analyze = wrapped
'''

class KnowledgeFirstMissingKindTest(unittest.TestCase):
    def test_sqlite_row_missing_kind_uses_original_analysis(self):
        patch=fix.corrected(SOURCE)
        space={}
        exec(patch,space)
        class Worker:
            def analyze(self,db,job):return 'original_analysis'
        worker=Worker()
        space['install'](worker)
        with sqlite3.connect(':memory:') as conn:
            conn.row_factory=sqlite3.Row
            conn.execute('CREATE TABLE skip_jobs(asset_key TEXT, status TEXT)')
            conn.execute('INSERT INTO skip_jobs VALUES (?,?)',('asset','queued'))
            job=conn.execute('SELECT * FROM skip_jobs').fetchone()
        @contextmanager
        def db():
            yield None
        self.assertEqual(worker.analyze(db,job),'original_analysis')
        self.assertEqual(worker.analyze(db,{'kind':'intro'}),'knowledge_used')
        self.assertEqual(worker.analyze(db,{'kind':'outro'}),'original_analysis')

    def test_idempotent_and_only_changes_decider(self):
        patched=fix.corrected(SOURCE)
        self.assertIsNone(fix.corrected(patched))
        self.assertEqual(SOURCE.split('def install',1)[1],
                         patched.split('def install',1)[1])

    def test_unknown_source_is_rejected(self):
        for code in (
            SOURCE.replace("kind = job['kind']","kind = job.get('kind')"),
            SOURCE.replace("source = decider(db, job)","source = None"),
            SOURCE.replace("def decide(db, job):","def decide_v2(db, job):"),
            SOURCE.replace("kind = job['kind']","kind = job['kind']\n        kind = job['kind']"),
        ):
            with self.subTest(code=code[:30]):
                with self.assertRaises(ValueError):
                    fix.corrected(code)

if __name__=='__main__':
    unittest.main()
