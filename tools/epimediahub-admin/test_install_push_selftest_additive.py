"""Offline regression checks for additive Admin self-test production installer."""
from pathlib import Path
import ast
import unittest
import install_push_selftest_additive as deploy

ROOT=Path(__file__).resolve().parent

class TestPushInstall(unittest.TestCase):
    def source(self,name):
        return (ROOT/name).read_text(encoding="utf-8")

    def test_sender_legacy_and_idempotent(self):
        latest=self.source('fcm_sender.py')
        old=latest.replace('"expiry_monthly","expiry_weekly","push_test",',
                           '"expiry_monthly","expiry_weekly",')
        self.assertNotEqual(old,latest)
        result=deploy.patch_sender(old)
        self.assertIn('"push_test"',result)
        self.assertEqual(deploy.patch_sender(result),result)
        self.assertEqual(deploy.patch_sender(latest),latest)
        ast.parse(result)
        self.assertIn('def send(fcm_token: str, kind: str)',result)

    def test_sender_legacy_without_expiry_alerts(self):
        old=self.source('fcm_sender.py').replace(
            '    "expiry_monthly","expiry_weekly","push_test",\n','')
        self.assertIn('ALLOWED_KINDS=frozenset',old)
        result=deploy.patch_sender(old)
        self.assertIn('"push_test"',result)
        self.assertNotIn('"expiry_monthly"',result)
        self.assertIn('"analysis_stalled"',result)
        self.assertEqual(deploy.patch_sender(result),result)

    def test_sender_suspicious_allowlist_fails_closed(self):
        original=self.source('fcm_sender.py')
        with self.assertRaisesRegex(RuntimeError,'STOP_'):
            deploy.patch_sender(original.replace('"push_test",','"unreviewed_private_kind",'))
        with self.assertRaisesRegex(RuntimeError,'STOP_'):
            deploy.patch_sender(original.replace('frozenset((', 'eval(('))

    def test_registry_legacy_and_idempotent(self):
        latest=self.source('mobile_registry.py')
        first=latest.index("    def begin_push_test(")
        last=latest.index("    def _connect(self):",first)
        old=latest[:first]+latest[last:]
        unregister_clean='''            if db.execute("""SELECT 1 FROM sqlite_master WHERE
                  type='table' AND name='admin_mobile_push_tests'""").fetchone():
                db.execute("DELETE FROM admin_mobile_push_tests WHERE installation_id=?",
                           (normalized,))
'''
        self.assertIn(unregister_clean,old)
        old=old.replace(unregister_clean,'')
        result=deploy.patch_registry(old)
        self.assertEqual(result,latest)
        self.assertEqual(deploy.patch_registry(result),result)
        ast.parse(result)

    def test_flask_legacy_and_idempotent(self):
        latest=self.source('mobile_flask.py')
        self.assertIn(deploy.TEST_PREPARED,latest)
        self.assertIn(deploy.TEST_FLASK,latest)
        old=latest.replace(deploy.TEST_PREPARED,'').replace(deploy.TEST_FLASK,'')
        old=old.replace('from mobile_registry import AdminMobileRegistry\nimport fcm_sender',
                        'from mobile_registry import AdminMobileRegistry')
        old=old.replace(
            '       "push_sender_configured":_push_transport_prepared(),\n','')
        self.assertNotEqual(old,latest)
        restored=deploy.patch_flask(old)
        self.assertEqual(restored,latest)
        self.assertEqual(deploy.patch_flask(restored),restored)
        ast.parse(restored)

    def test_unexpected_sources_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError,'STOP_'):
            deploy.patch_flask('def unrelated(): pass')
        with self.assertRaisesRegex(RuntimeError,'STOP_'):
            deploy.patch_sender('ALLOWED_KINDS=()')
        with self.assertRaisesRegex(RuntimeError,'STOP_'):
            deploy.patch_registry('class AdminMobileRegistry: pass')

    def test_no_install_import_side_effects(self):
        self.assertTrue(callable(deploy.preflight))
        self.assertTrue(callable(deploy.save_and_install))
        self.assertIn('--check',deploy.main.__code__.co_consts.__str__())

if __name__=='__main__':
    unittest.main()
