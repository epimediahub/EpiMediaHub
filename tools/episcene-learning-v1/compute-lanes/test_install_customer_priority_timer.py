"""Synthetic-only installer tests; never executes systemctl or touches production."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location(
   "install_customer_priority_timer",
   Path(__file__).with_name("install_customer_priority_timer.py"))
m=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)


class PriorityTimerInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        parent=Path(self.tmp.name)
        self.root=parent/"installed"
        self.unit=parent/"smart.service"
        self.timer=parent/"smart.timer"
        self.source=parent/"priority-source.py"
        self.source.write_text("# safe synthetic priority\n")
        class FakePriority:
            @staticmethod
            def run(apply=False):
                return {"check":"PASS","priority_requests_proposed":0,
                        "analysis_jobs_modified":0,
                        "versions":{"scheduler":"match","analysis_worker":"match"}}
        self.calls=[]
        def fake_ctl(*args,**kwargs):
            self.calls.append(args)
            return 0
        patches=[
            patch.object(m,"ROOT",self.root),
            patch.object(m,"SCRIPT",self.root/"priority.py"),
            patch.object(m,"UNIT",self.unit),
            patch.object(m,"TIMER",self.timer),
            patch.object(m,"SOURCE",self.source),
            patch.object(m.os,"geteuid",return_value=0),
            patch.object(m,"active",return_value=True),
            patch.object(m,"load",return_value=FakePriority),
            patch.object(m,"ctl",side_effect=fake_ctl),
        ]
        self.patches=patches
        for p in patches:p.start()

    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()

    def test_preflight_leaves_existing_files_untouched(self):
        report=m.preflight()
        self.assertEqual(report["preflight"],"PASS")
        self.assertEqual(report["changes_made"],0)
        self.assertFalse(self.root.exists())
        self.assertFalse(self.unit.exists())
        self.assertEqual(self.calls,[])

    def test_success_installs_only_new_isolated_units(self):
        result=m.install()
        self.assertTrue(result["applied"])
        self.assertTrue(result["customer_priority_timer_active"])
        self.assertFalse(result["analysis_worker_restarted"])
        self.assertEqual(self.source.read_bytes(),m.SCRIPT.read_bytes())
        self.assertEqual(self.unit.read_text(),m.SERVICE_CONTENT)
        self.assertEqual(self.timer.read_text(),m.TIMER_CONTENT)
        self.assertEqual(self.calls[0],("daemon-reload",))
        self.assertEqual(self.calls[1],("start",m.PRIORITY_SERVICE))
        self.assertEqual(self.calls[2],("enable","--now",m.PRIORITY_TIMER))
        self.assertTrue(m.verify()["verified"])
        self.assertNotIn("epimediahub-analysis-worker.service",
                         " ".join(" ".join(x) for x in self.calls))

    def test_failed_first_sync_rolls_back_and_does_not_restart_worker(self):
        def fail(*args,**kwargs):
            self.calls.append(args)
            return 1 if args[0]=="start" else 0
        with patch.object(m,"ctl",side_effect=fail):
            result=m.install()
        self.assertFalse(result["applied"])
        self.assertEqual(result["reason"],"FIRST_PRIORITY_SYNC_FAILED")
        self.assertTrue(result["rollback_restored"])
        self.assertFalse(self.unit.exists())
        self.assertFalse(self.timer.exists())
        self.assertFalse(self.root.exists())
        self.assertNotIn("restart"," ".join(" ".join(x) for x in self.calls))

    def test_existing_unit_must_never_be_overwritten(self):
        self.unit.write_text("foreign manager")
        with self.assertRaisesRegex(m.Stop,"EXISTING_PRIORITY_UNIT"):
            m.preflight()
        self.assertEqual(self.unit.read_text(),"foreign manager")

    def test_drifted_installed_payload_not_verified(self):
        self.assertTrue(m.install()["applied"])
        m.SCRIPT.write_text("modified priority logic")
        with self.assertRaisesRegex(m.Stop,"VERSION_DRIFT"):
            m.verify()

    def test_timer_disables_network_and_bounds_resources(self):
        self.assertIn("PrivateNetwork=true",m.SERVICE_CONTENT)
        self.assertIn("ProtectSystem=strict",m.SERVICE_CONTENT)
        self.assertIn("CPUQuota=30%",m.SERVICE_CONTENT)
        self.assertIn("MemoryMax=512M",m.SERVICE_CONTENT)
        self.assertIn("OnUnitInactiveSec=15min",m.TIMER_CONTENT)


if __name__=="__main__":
    unittest.main()
