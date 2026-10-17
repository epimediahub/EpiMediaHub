"""Test full bounded incident -> persistent FCM outbox flow, without network."""
from pathlib import Path
import json
import os
import tempfile
import time
import unittest
import uuid

from mobile_registry import AdminMobileRegistry
from monitor_cycle import read_snapshot, run_once


class TestMonitorCycle(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.data=self.root/"admin-mobile"
        self.data.mkdir(mode=0o700)
        self.metrics=self.root/"metric.json"
        self.now=1781654400

    def tearDown(self):
        self.tmp.cleanup()

    def snapshot(self, extra=None):
        payload={"sampled_at_epoch":self.now,
                 "analysis_lanes":[{"id":"8","queued_jobs":7,
                    "last_progress_epoch":self.now-1200,"paused":False}]}
        if extra:payload.update(extra)
        self.metrics.write_text(json.dumps(payload))
        self.metrics.chmod(0o600)

    def test_retries_after_transient_transport_failure(self):
        self.snapshot()
        registry=AdminMobileRegistry(self.data/"registrations.sqlite3")
        install=str(uuid.uuid4());registry.register(install,"X"*180,self.now)
        sent=[]
        first=run_once(self.metrics,self.data,self.now,deliver=lambda tok,k:False)
        self.assertEqual(first["new_incident_generations"],1)
        self.assertEqual(first["push_failed_pending_retry"],1)
        self.assertEqual(len(registry.pending()),1)
        second=run_once(self.metrics,self.data,self.now+10,
            deliver=lambda tok,k: sent.append(k) or True)
        self.assertEqual(second["new_incident_generations"],0)
        self.assertEqual(second["push_sent"],1)
        self.assertEqual(sent,["analysis_stalled"])
        self.assertEqual(registry.pending(),[])
        self.assertEqual(run_once(self.metrics,self.data,self.now+20,
            deliver=lambda tok,k: True)["push_sent"],0)

    def test_denies_private_source_fields_and_stale_samples(self):
        self.snapshot(extra={"access_token":"secret"})
        with self.assertRaises(ValueError):
            read_snapshot(self.metrics,self.now)
        self.snapshot()
        with self.assertRaises(ValueError):
            read_snapshot(self.metrics,self.now+130)
        self.snapshot({"analysis_lanes":[{"id":"https://provider/url","queued_jobs":1,
          "last_progress_epoch":self.now-1000}]})
        with self.assertRaises(ValueError):
            read_snapshot(self.metrics,self.now)

    def test_no_push_when_no_admin_installations(self):
        self.snapshot()
        result=run_once(self.metrics,self.data,self.now,deliver=lambda t,k: True)
        self.assertEqual(result["alerts_observed"],1)
        self.assertEqual(result["registered_admin_installations"],0)
        self.assertEqual(result["push_sent"],0)
        self.assertFalse(result["credentials_printed"])


if __name__=="__main__":
    unittest.main()
