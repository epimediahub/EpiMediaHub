"""Regression tests for the exact-target manual-submit server installer."""
import ast
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import install_manual_release_fix as installer


def baseline():
    # Exact original release-gated submit block inside a non-imported function.
    return ('import re\n\n'
            + installer.ANCHOR + '\n    return None\n\n'
            + 'def fake_submit():\n'
            + '    def old():\n'
            + installer.ORIGINAL.replace('            ', '        ', 1)
              .replace('\n            ', '\n        ')
            + '\n')


class InstallerSafety(unittest.TestCase):
    def test_patch_replaces_machine_release_gate_once(self):
        old=baseline()
        # Test the exact insertion at its normal 12-space indentation.
        old=('import re\n\n' + installer.ANCHOR + '\n    return None\n\n'
             + 'def fake_submit():\n    if True:\n'
             + installer.ORIGINAL)
        ast.parse(old)
        patched,changed=installer.patch(old)
        self.assertTrue(changed)
        ast.parse(patched)
        self.assertEqual(patched.count(installer.HELPER),1)
        self.assertEqual(patched.count(installer.REPLACEMENT),1)
        self.assertNotIn(installer.ORIGINAL,patched)
        self.assertNotIn('release_enabled(con',patched)
        self.assertEqual(installer.patch(patched),(patched,False))

    def test_fails_closed_on_drift_or_duplicates(self):
        old=('import re\n\n'+installer.ANCHOR+'\n    pass\n\n'
             +'def fake_submit():\n    if True:\n'+installer.ORIGINAL)
        for value in ('',old.replace("enabled as release_enabled","enabled as custom_release"),
                      old+installer.ORIGINAL,old.replace(installer.ANCHOR,'def changed():')):
            with self.subTest(source=value):
                with self.assertRaises((RuntimeError,SyntaxError)):
                    installer.patch(value)

    def test_preflight_does_not_write_or_restart(self):
        old=('import re\n\n'+installer.ANCHOR+'\n    pass\n\n'
             +'def fake_submit():\n    if True:\n'+installer.ORIGINAL)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'skip_markers.py';path.write_text(old)
            before=path.read_bytes()
            with mock.patch.object(installer.os,'geteuid',return_value=0), \
                 mock.patch.object(installer,'live_service',return_value=True), \
                 mock.patch.object(installer,'restart_and_check',side_effect=AssertionError('no restart')):
                self.assertTrue(installer.install(path,Path(tmp)/'backups',check=True))
            self.assertEqual(path.read_bytes(),before)
            self.assertFalse((Path(tmp)/'backups').exists())

    def test_no_work_on_already_patched(self):
        old=('import re\n\n'+installer.ANCHOR+'\n    pass\n\n'
             +'def fake_submit():\n    if True:\n'+installer.ORIGINAL)
        newer,_=installer.patch(old)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'skip_markers.py';path.write_text(newer)
            with mock.patch.object(installer.os,'geteuid',return_value=0), \
                 mock.patch.object(installer,'live_service',return_value=True):
                self.assertFalse(installer.install(path,Path(tmp)/'backups',check=False))
            self.assertEqual(newer,path.read_text())

    def test_rollback_restores_bytes_when_service_fails(self):
        old=('import re\n\n'+installer.ANCHOR+'\n    pass\n\n'
             +'def fake_submit():\n    if True:\n'+installer.ORIGINAL)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'skip_markers.py';path.write_text(old)
            before=path.read_bytes()
            # CI runs unprivileged, so only mock filesystem chown/root owner.
            real_stat=Path.stat
            def safe_stat(obj,*args,**kwargs):
                st=real_stat(obj,*args,**kwargs)
                if obj.name=='backups':
                    from types import SimpleNamespace
                    return SimpleNamespace(st_uid=0,st_mode=st.st_mode)
                return st
            with mock.patch.object(installer.os,'geteuid',return_value=0), \
                 mock.patch.object(installer.os,'chown'), \
                 mock.patch.object(installer,'live_service',return_value=True), \
                 mock.patch.object(installer,'restart_and_check',side_effect=RuntimeError('fake_restart_failure')), \
                 mock.patch.object(Path,'stat',safe_stat), \
                 mock.patch.object(installer.subprocess,'run'):
                with self.assertRaisesRegex(RuntimeError,'fake_restart_failure'):
                    installer.install(path,Path(tmp)/'backups')
            self.assertEqual(path.read_bytes(),before)


if __name__=='__main__':
    unittest.main(verbosity=2)
