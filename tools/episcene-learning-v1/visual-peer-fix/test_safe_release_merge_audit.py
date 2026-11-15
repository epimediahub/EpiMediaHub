"""Synthetic, private-source-safe compatibility audit regressions."""
import tempfile
from pathlib import Path
import unittest
import safe_release_merge_audit as a

BASE="""MAX_NEW_PER_RUN=4
MAX_DAILY=8
MAX_PER_PLAYLIST=2
def protected():
    return 1
def collect():
    return 2
def plan():
    return 3
def audit():
    return 4
"""
NEW="""MAX_NEW_PER_RUN=6
MAX_DAILY=16
MAX_PER_PLAYLIST=3
MAX_PER_FAMILY_PER_RUN=2
MAX_PER_FAMILY_PER_DAY=4
def protected():
    return 11
def collect():
    return 12
def plan():
    return 13
def audit():
    return 4
"""

class MergeAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.old=root/"baseline.py";self.new=root/"candidate.py";self.live=root/"private_live.py"
        self.old.write_text(BASE);self.new.write_text(NEW)
        self.live.write_text(BASE)
    def tearDown(self):
        self.temp.cleanup()

    def test_known_public_changes_can_merge_without_modifying_private(self):
        orig=self.live.read_bytes()
        result=a.audit(self.old,self.new,self.live)
        self.assertTrue(result["limited_function_level_merge_looks_possible"])
        self.assertFalse(result["deployment_authorized"])
        self.assertFalse(result["private_source_exported"])
        self.assertEqual(self.live.read_bytes(),orig)
        self.assertEqual(result["proposed_changed_entries"]["function:plan"],
                         "SAFE_TO_MERGE_IN_PRINCIPLE")

    def test_private_unrelated_modifications_remain_distinct(self):
        self.live.write_text(BASE.replace("def audit():\n    return 4",
                                          "def audit():\n    return 99"))
        result=a.audit(self.old,self.new,self.live)
        self.assertTrue(result["limited_function_level_merge_looks_possible"])
        self.assertEqual(result["other_live_custom_entries_to_preserve_count"],1)

    def test_private_overlap_blocks_unreviewed_merge(self):
        self.live.write_text(BASE.replace("def collect():\n    return 2",
                                          "def collect():\n    return 999"))
        result=a.audit(self.old,self.new,self.live)
        self.assertFalse(result["limited_function_level_merge_looks_possible"])
        self.assertIn("function:collect",result["overlapping_changes_requiring_review"])

    def test_live_candidate_is_not_claimed_deployed(self):
        self.live.write_text(NEW)
        result=a.audit(self.old,self.new,self.live)
        self.assertTrue(result["limited_function_level_merge_looks_possible"])
        self.assertFalse(result["deployment_authorized"])
        self.assertEqual(result["proposed_changed_entries"]["function:plan"],
                         "CANDIDATE_ALREADY_PRESENT")

    def test_missing_required_function_fails_closed(self):
        self.live.write_text(BASE.replace("def plan():\n    return 3",""))
        with self.assertRaises(ValueError):
            a.audit(self.old,self.new,self.live)

    def test_unexpected_patch_scope_blocked(self):
        self.new.write_text(NEW.replace("def audit():\n    return 4",
                                        "def audit():\n    return 45"))
        with self.assertRaisesRegex(ValueError,"UNRECOGNIZED_PUBLIC_PATCH_SCOPE"):
            a.audit(self.old,self.new,self.live)

    def test_private_symlink_is_not_read(self):
        self.live.unlink()
        self.live.symlink_to(self.old)
        with self.assertRaises(ValueError):
            a.audit(self.old,self.new,self.live)

if __name__=="__main__":
    unittest.main(verbosity=2)
