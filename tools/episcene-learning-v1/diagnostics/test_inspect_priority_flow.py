#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path

import inspect_priority_flow as audit


class FlowTests(unittest.TestCase):
    def test_identifies_priority_query_functions_not_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'skip_automation.py'
            path.write_text(
                'def discover_one():\n'
                '    secret="should-never-be-printed"\n'
                '    sql="SELECT a FROM skip_language_priority JOIN x ORDER BY priority"\n'
                '    return select(sql)\n',encoding='utf-8')
            info=audit.inspect_path(path)
            self.assertEqual(info['status'],'ok')
            entry=info['functions'][0]
            self.assertEqual(entry['fn'],'discover_one')
            self.assertIn('skip_language_priority',entry['priority_refs'])
            self.assertIn('sql_order_by',entry['sql_shapes'])
            self.assertIn('select',entry['calls'])
            self.assertNotIn('should-never-be-printed',str(info))

    def test_ignore_commented_out_terms_and_symlinks(self):
        with tempfile.TemporaryDirectory() as td:
            f=Path(td)/'skip_catalogue.py'
            f.write_text('# skip_language_priority is deleted\n'
                         'def ordinary(): return True\n',encoding='utf-8')
            info=audit.inspect_path(f)
            self.assertEqual(info['functions'],[])
            link=Path(td)/'skip_schedule.py'
            link.symlink_to(f)
            self.assertEqual(audit.inspect_path(link)['status'],'unavailable')

    def test_unsurprising_function_without_priority_is_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/'skip_schedule.py'
            path.write_text('def submit(): return request_series("asset")\n',encoding='utf-8')
            self.assertEqual(audit.inspect_path(path)['functions'],[])


if __name__=='__main__':
    unittest.main()
