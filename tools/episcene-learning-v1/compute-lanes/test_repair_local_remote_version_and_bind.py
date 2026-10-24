"""Local EpiScene worker repair: synthetic rollback and safe file swap tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location(
    "repair_local_remote_version_and_bind",
    Path(__file__).with_name("repair_local_remote_version_and_bind.py"))
r=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(r)

class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        base=Path(self.tmp.name)
        self.a=base/"api.py";self.b=base/"worker.py"
        self.a.write_text("new");self.b.write_text("old")
        self.drop=base/"dropin"/"local.conf"
        self.drop.parent.mkdir()
        self.calls=[]
        def runner(*args,**kw):
            self.calls.append(args)
            return ""
        def backup(**kw):
            path=base/"backup"
            path.mkdir()
            return str(path)
        self.steps=[
            patch.object(r,"API_SRC",self.a),
            patch.object(r,"REMOTE_SRC",self.b),
            patch.object(r,"DROPIN",self.drop),
            patch.object(r,"guard",return_value={"preflight":"PASS"}),
            patch.object(r,"cmd",side_effect=runner),
            patch.object(r,"status",return_value="inactive"),
            patch.object(r,"local_health",return_value={"active":False,"active_count":0}),
            patch.object(r,"restart_worker_and_wait",return_value=True),
            patch.object(r,"active",return_value=True),
            patch.object(r.tempfile,"mkdtemp",side_effect=backup),
        ]
        for step in self.steps:step.start()

    def tearDown(self):
        for step in reversed(self.steps):step.stop()
        self.tmp.cleanup()

    def test_success_keeps_api_and_writes_isolated_dropin(self):
        with patch.object(r,"local_client_health",return_value=True):
            result=r.apply()
        self.assertTrue(result["applied"])
        self.assertEqual(self.a.read_text(),"new")
        self.assertEqual(self.b.read_text(),"new")
        self.assertEqual(self.drop.read_text(),r.ENV_CONTENT)

    def test_failure_restores_file_and_dropin(self):
        with patch.object(r,"local_client_health",return_value=False):
            result=r.apply()
        self.assertFalse(result["applied"])
        self.assertTrue(result["rollback_restored"])
        self.assertEqual(self.b.read_text(),"old")
        self.assertFalse(self.drop.exists())

    def test_symlink_refused(self):
        alias=self.a.with_name("alias.py")
        alias.symlink_to(self.a)
        with self.assertRaises(r.Stop):
            r.source_sha(alias)

if __name__=="__main__":
    unittest.main()
