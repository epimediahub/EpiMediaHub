#!/usr/bin/env python3
import ast
import tempfile
import unittest
import zipfile
from pathlib import Path
import export_priority_source as export


class ExportTests(unittest.TestCase):
    def test_source_export_redacts_literals_but_keeps_safe_sql(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            f=root/'skip_schedule.py'
            f.write_text(
                '# private comment username somebody@example.org\n'
                'def select_job(db, password="TOP_SECRET_PW"):\n'
                '  token="RANDOM_SECRET_STRING_ABCDEF"\n'
                '  url="https://stream.example.net/private"\n'
                '  sql="""SELECT j.id FROM skip_jobs j LEFT JOIN skip_language_priority p\n'
                '            ON p.asset_key=j.asset_key WHERE j.status=\'queued\'\n'
                '            AND j.owner=\'CUSTOMER_EMAIL_PERSONAL\' ORDER BY p.priority"""\n'
                '  if 44444444444: return db.execute(sql)\n'
                '  return None\n',encoding='utf-8')
            manifest,sources=export.collect(root)
            generated=sources['skip_schedule.py']
            self.assertIn('skip_language_priority',generated)
            self.assertIn('ORDER BY',generated)
            self.assertIn('queued',generated)
            self.assertNotIn('TOP_SECRET_PW',generated)
            self.assertNotIn('RANDOM_SECRET_STRING_ABCDEF',generated)
            self.assertNotIn('stream.example.net',generated)
            self.assertNotIn('CUSTOMER_EMAIL_PERSONAL',generated)
            self.assertNotIn('somebody@example.org',generated)
            self.assertNotIn('44444444444',generated)
            ast.parse(generated)
            archive=root/'safe.zip'
            export.write_package(dest=archive,root=root)
            with zipfile.ZipFile(archive) as z:
                self.assertIn('sanitized/skip_schedule.py',z.namelist())
                content=b''.join(z.read(x) for x in z.namelist())
                self.assertNotIn(b'TOP_SECRET_PW',content)
                self.assertNotIn(b'stream.example.net',content)

    def test_only_allowlisted_top_level_functions(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            (root/'skip_schedule.py').write_text(
                'PROVIDER_PASSWORD="ABCNOTFORSHARING"\n'
                'def select_job(): return "queued"\n'
                'def unrelated(): return "SHOULD_NOT_EXPORT"\n',
                encoding='utf-8')
            _,src=export.collect(root)
            self.assertNotIn('PROVIDER_PASSWORD',src['skip_schedule.py'])
            self.assertNotIn('SHOULD_NOT_EXPORT',src['skip_schedule.py'])
            self.assertIn('def select_job',src['skip_schedule.py'])

    def test_symlink_source_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td)
            original=root/'real.py'
            original.write_text('def select_job(): return 1')
            (root/'skip_schedule.py').symlink_to(original)
            manifest,src=export.collect(root)
            self.assertEqual(manifest['modules']['skip_schedule.py']['status'],'UNAVAILABLE')
            self.assertNotIn('skip_schedule.py',src)


if __name__=='__main__':
    unittest.main()
