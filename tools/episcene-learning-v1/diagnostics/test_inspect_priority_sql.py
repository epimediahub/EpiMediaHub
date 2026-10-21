#!/usr/bin/env python3
import tempfile
import unittest
from pathlib import Path
import inspect_priority_sql as a


class SafeSqlTests(unittest.TestCase):
    def test_reports_shapes_not_urls_or_secrets(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            src=root/'skip_schedule.py'
            src.write_text(
              'def select_job(db):\n'
              '  sql="""SELECT id FROM skip_jobs j LEFT JOIN skip_language_priority lp\n'
              '  ON lp.asset_key=j.asset_key WHERE lp.priority=0\n'
              '  ORDER BY lp.priority, j.id"""\n'
              '  password="BAD_SHOULD_NEVER_PRINT"\n'
              '  endpoint="https://never-reveal.test/path"\n'
              '  return db.execute(sql)\n',encoding='utf-8')
            info=a.inspect_file(src,('select_job',))
            self.assertEqual(info['status'],'OK')
            row=info['functions']['select_job']
            self.assertEqual(row['priority_sql_with_order_by'],1)
            self.assertEqual(row['priority_sql_with_where'],1)
            self.assertIn('lp.priority=0',row['priority_comparisons'])
            output=a.brief({'skip_schedule.py':info})
            self.assertNotIn('BAD_SHOULD_NEVER_PRINT',output)
            self.assertNotIn('never-reveal.test',output)

    def test_detects_gating_priority_python_condition(self):
        with tempfile.TemporaryDirectory() as td:
            src=Path(td)/'skip_schedule.py'
            src.write_text(
                'def should_pause(language_priority):\n'
                '  if language_priority > 1: return True\n'
                '  return False\n',encoding='utf-8')
            row=a.inspect_file(src,('should_pause',))['functions']['should_pause']
            self.assertIn('language_priority',row['python_priority_conditions'])

    def test_missing_file_returns_failure_not_data(self):
        with tempfile.TemporaryDirectory() as td:
            r=a.inspect_file(Path(td)/'absent.py',('whatever',))
            self.assertEqual(r['status'],'UNAVAILABLE')


if __name__=='__main__':
    unittest.main()
