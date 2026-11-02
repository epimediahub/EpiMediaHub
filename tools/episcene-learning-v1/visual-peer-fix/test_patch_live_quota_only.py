"""Regression tests: surgically adjust quota values, preserving custom live code."""
import ast
import unittest
from pathlib import Path
import patch_live_quota_only as patcher

BASE = """MAX_NEW_PER_RUN = 4
MAX_DAILY=8
MAX_PER_PLAYLIST=2 # project-specific comment
def collect(con):
    # PRIVATE LIVE CHANGE: DO NOT OVERWRITE
    return [1,2,3]
def plan(con,rows):
    # PRIVATE LIVE CHANGE: DO NOT OVERWRITE
    return sorted(rows)
"""

class QuotaOnlyTests(unittest.TestCase):
    def test_preserves_two_custom_live_functions(self):
        changed=patcher.patch(BASE)
        self.assertIn("MAX_NEW_PER_RUN = 6",changed)
        self.assertIn("MAX_DAILY=16",changed)
        self.assertIn("MAX_PER_PLAYLIST=3 # project-specific comment",changed)
        before=ast.parse(BASE);after=ast.parse(changed)
        self.assertEqual(patcher.components(before),patcher.components(after))
        self.assertIn("PRIVATE LIVE CHANGE: DO NOT OVERWRITE",changed)

    def test_idempotent(self):
        once=patcher.patch(BASE)
        self.assertEqual(patcher.patch(once),once)

    def test_unexpected_quota_aborts(self):
        for other in ("MAX_DAILY=99","MAX_DAILY=None","MAX_DAILY=True",
                      "MAX_DAILY=14 # unexpected"):
            with self.subTest(other=other):
                self.assertRaises(ValueError,patcher.patch,
                                  BASE.replace("MAX_DAILY=8",other))

    def test_duplicate_quota_aborts(self):
        with self.assertRaises(ValueError):
            patcher.patch(BASE+"MAX_DAILY=8\n")

    def test_missing_quota_aborts(self):
        with self.assertRaises(ValueError):
            patcher.patch(BASE.replace("MAX_NEW_PER_RUN = 4",""))

    def test_rejects_conditional_assignment_to_quota(self):
        with self.assertRaises(ValueError):
            patcher.patch(BASE.replace("MAX_DAILY=8","MAX_DAILY=4 if True else 8"))

if __name__=="__main__":
    unittest.main(verbosity=2)
