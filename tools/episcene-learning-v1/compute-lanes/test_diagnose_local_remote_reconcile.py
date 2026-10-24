"""Synthetic, socket-free test for local EpiScene worker reconciliation."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location(
    "diagnose_local_remote_reconcile",
    Path(__file__).with_name("diagnose_local_remote_reconcile.py"))
diag=importlib.util.module_from_spec(spec)
spec.loader.exec_module(diag)


class WorkerReconcileTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        root=Path(self.tmp.name)
        self.prov=root/"provisioning"
        self.analysis=root/"analysis"
        self.prov.mkdir()
        self.analysis.mkdir()
        (self.prov/"skip_analysis.py").write_bytes(b"new scope code, no customer identifiers")
        (self.analysis/"skip_analysis.py").write_bytes(b"old worker code")
        self.local=hashlib.sha256((self.prov/"skip_analysis.py").read_bytes()).hexdigest()
        self.remote=hashlib.sha256((self.analysis/"skip_analysis.py").read_bytes()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_provenance_identifies_old_worker_version_without_raw_hash(self):
        start_prov=(self.prov/"skip_analysis.py").read_bytes()
        with patch.object(diag,"PROV",self.prov),patch.object(diag,"ANAL",self.analysis),\
             patch.object(diag.importlib,"import_module",return_value=types.SimpleNamespace(
                 SERVER_IP="10.87.26.1",PORT=8790,PROTOCOL="v1",
                 versions=lambda:{"skip_analysis.py":self.local,"another.py":"x"})),\
             patch.object(diag,"local_health",return_value={
                 "state":"OK","active_count":0,"tasks_active":False,
                 "protocol":"v1","reported_versions":{
                    "skip_analysis.py":self.remote,"another.py":"x"}}),\
             patch.object(diag,"listener",return_value={"listener_on_loopback":True}),\
             patch.object(diag,"configured_address_assigned",return_value=False):
            report=diag.diagnostic()
        self.assertEqual(report["different_component_names"],["skip_analysis.py"])
        self.assertTrue(report["file_provenance"]["api_file_compared_to_current"]["matches_reported_version"])
        self.assertTrue(report["file_provenance"]["worker_tree_file_compared_to_running_remote"]["matches_reported_version"])
        self.assertFalse(report["file_provenance"]["worker_tree_file_compared_to_current"]["matches_reported_version"])
        self.assertFalse(report["configured_remote_target_assigned_to_this_host"])
        self.assertFalse(report["safe_to_restart_worker_based_on_this_report_alone"])
        self.assertNotIn(self.local,str(report))
        self.assertNotIn(self.remote,str(report))
        self.assertEqual((self.prov/"skip_analysis.py").read_bytes(),start_prov)
        self.assertEqual(report["database_writes"],0)

    def test_digest_does_not_echo_contents(self):
        r=diag.digest_match(self.prov/"skip_analysis.py",self.local)
        self.assertEqual(r,{"exists":True,"matches_reported_version":True})
        self.assertNotIn("scope code",str(r))

    def test_never_follow_symlinks(self):
        alias=self.prov/"link.py"
        alias.symlink_to(self.prov/"skip_analysis.py")
        self.assertEqual(diag.digest_match(alias,self.local),{"exists":False})

    def test_service_discovery_never_probes_network(self):
        with patch.object(diag,"call",return_value=""):
            report=diag.listener()
        self.assertFalse(report["listener_present"])
        self.assertEqual(report["worker_process_count"],0)

    def test_private_config_ip_lookups_are_boolean_only(self):
        with patch.object(diag,"call",return_value="2: tun0 inet 10.87.26.1/24 scope global tun0"):
            self.assertTrue(diag.configured_address_assigned("10.87.26.1"))
            self.assertFalse(diag.configured_address_assigned("10.87.26.2"))


if __name__=="__main__":
    unittest.main()
