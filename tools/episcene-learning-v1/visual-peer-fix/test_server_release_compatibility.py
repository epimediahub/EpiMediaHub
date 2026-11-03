"""Synthetic old/live/new SHA and systemd evidence without shell/network writes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import server_release_compatibility as c

class ReleaseCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.old=self.root/"old.py"
        self.new=self.root/"new.py"
        self.live=self.root/"live.py"
        self.old.write_text("def run():\n    return 1\n")
        self.new.write_text("def run():\n    return 2\n")
        self.live.write_bytes(self.old.read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def test_known_live_provenance_with_no_writes(self):
        with patch.object(c,"LIVE",self.live), \
             patch.object(c,"MODULES",{}), \
             patch.object(c,"systemd",return_value="active"):
            result=c.run(self.old,self.new)
        self.assertTrue(result["live_equals_reviewed_main"])
        self.assertFalse(result["live_equals_candidate"])
        self.assertFalse(result["deployment_allowed"])
        self.assertEqual(result["writes"],0)
        self.assertEqual(result["marker_approvals"],0)
        self.assertEqual(self.live.read_bytes(),self.old.read_bytes())

    def test_drift_is_not_claimed_compatible(self):
        self.live.write_text("def unexpected():\n    return 100\n")
        with patch.object(c,"LIVE",self.live), \
             patch.object(c,"MODULES",{}), \
             patch.object(c,"systemd",return_value="inactive"):
            result=c.run(self.old,self.new)
        self.assertTrue(result["live_diverges_from_both"])
        self.assertTrue(result["live_function_names_differ_from_main"])
        self.assertFalse(result["service_checks"]["timer_active"])
        self.assertFalse(result["deployment_allowed"])

    def test_missing_or_symlinked_code_fails_safe(self):
        self.live.unlink()
        self.live.symlink_to(self.old)
        with patch.object(c,"LIVE",self.live):
            result=c.run(self.old,self.new)
        self.assertEqual(result["live_controller"],"UNAVAILABLE")
        self.assertFalse(result["deployment_allowed"])

    def test_invalid_reference_source_is_rejected(self):
        self.old.write_text("bad syntax !!!")
        with self.assertRaises(ValueError):
            c.run(self.old,self.new)

if __name__=="__main__":
    unittest.main(verbosity=2)
