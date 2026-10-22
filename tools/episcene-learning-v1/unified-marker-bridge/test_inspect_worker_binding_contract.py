import ast
import json
import tempfile
import unittest
from pathlib import Path

from inspect_worker_binding_contract import describe, functions, scan


class WorkerBindingInspectionTests(unittest.TestCase):
    def test_redacted_no_secret_or_sql_values(self):
        code = """
def select_job(password, conn):
    host = 'https://private.example/x?token=TOP_SECRET_SENTINEL'
    secret = 'TOP_SECRET_SENTINEL'
    sql = "SELECT asset_key FROM skip_jobs WHERE password='TOP_SECRET_SENTINEL'"
    row = conn.execute(sql).fetchone()
    if row['status'] == 'queued':
        return row['asset_key']
    return None
"""
        report=describe(*functions(ast.parse(code))[0])
        text=json.dumps(report)
        for bad in ('TOP_SECRET_SENTINEL', 'https://', 'private.example', 'password','token='):
            self.assertNotIn(bad,text)
        self.assertIn('skip_jobs',text)
        self.assertIn('queued',text)

    def test_same_named_functions_preserve_owner(self):
        tree=ast.parse("def analyze(): pass\nclass W:\n def analyze(self): pass\n")
        rows=[describe(node,parents) for node,parents in functions(tree)]
        self.assertEqual([r['owner'] for r in rows],['module','W'])

    def test_unknown_changed_function_refuses_ready(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            (root/'skip_schedule.py').write_text('def select_job(): return None')
            result=scan(root, {'skip_schedule.py':{'select_job':{'0000000000000000'}}})
            self.assertFalse(result['ready_for_exact_patch_review'])
            self.assertEqual(result['files'][0]['status'],'changed_or_missing_shape')


if __name__=='__main__':
    unittest.main()
