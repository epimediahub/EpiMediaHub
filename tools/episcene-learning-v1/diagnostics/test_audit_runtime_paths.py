#!/usr/bin/env python3
"""Validate read-only, credential-free AST scope survey."""
import json
import tempfile
import unittest
from pathlib import Path

import audit_runtime_paths as auditor


class SourceAuditTests(unittest.TestCase):
    def test_reports_actual_priority_code_without_leaking_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'production'
            learn=Path(tmp)/'learning'
            root.mkdir();learn.mkdir()
            (root/'skip_schedule.py').write_text(
                '# skip_language_priority is deprecated (comment only)\n'
                'MAX_JOB_TIMEOUT=300\n'
                'def choose():\n'
                '    sql="SELECT priority FROM skip_language_priority WHERE asset_key=?"\n'
                '    token="super-secret-not-in-report"\n'
                '    return sql,token\n',encoding='utf-8')
            (learn/'safe_release_rollout_v2.py').write_text(
                'MAX_DAILY=8\n'
                'def collect():\n'
                '    return "plain playlist selection"\n',encoding='utf-8')
            data=auditor.report(root,learn)
            text=json.dumps(data)
            self.assertNotIn('super-secret',text)
            self.assertNotIn('SELECT priority',text)
            self.assertEqual(data['summary']['internal_language_priority_locations'],1)
            record=data['language_priority_references'][0]
            self.assertEqual(record['file'],'skip_schedule.py')
            self.assertEqual(record['scope'],'choose')
            self.assertEqual(data['numeric_limits']['production/skip_schedule.py']['MAX_JOB_TIMEOUT'],300)
            self.assertEqual(data['numeric_limits']['learning/safe_release_rollout_v2.py']['MAX_DAILY'],8)

    def test_absent_priority_table_is_not_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'production'
            learn=Path(tmp)/'learning'
            root.mkdir();learn.mkdir()
            (root/'skip_schedule.py').write_text(
                'def dispatch(playlist_id):\n'
                '    return playlist_id\n',encoding='utf-8')
            data=auditor.report(root,learn)
            self.assertEqual(data['summary']['internal_language_priority_locations'],0)

    def test_refuses_symlinks_and_does_not_execute_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'production'
            learn=Path(tmp)/'learning'
            root.mkdir();learn.mkdir()
            target=Path(tmp)/'outside.py'
            target.write_text('raise RuntimeError("SHOULD NOT RUN")\n',encoding='utf-8')
            (root/'skip_worker.py').symlink_to(target)
            data=auditor.report(root,learn)
            self.assertEqual(data['unavailable']['production/skip_worker.py'],'UNAVAILABLE_OR_SYMLINK')


if __name__=='__main__':
    unittest.main()
