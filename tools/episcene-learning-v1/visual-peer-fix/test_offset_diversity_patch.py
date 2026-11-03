#!/usr/bin/env python3
"""Offline synthetic regression tests; no production modules, network or DB."""
import ast
import types
import unittest

from offset_diversity_patch import patch

BASE = '''def _pair_candidates(target, votes, np):
    offsets = sorted(np.flatnonzero(votes >= max(15, 15000 // target.step_ms)),
                     key=lambda i: int(votes[i]), reverse=True)[:12]
    return offsets

def release_ready(score):
    return score >= 0.90
'''

class Votes:
    def __init__(self, values):
        self.values = values
    def __getitem__(self, index):
        return self.values[index]
    def __ge__(self, threshold):
        return [v >= threshold for v in self.values]

class NpStub:
    @staticmethod
    def flatnonzero(flags):
        return [i for i, flag in enumerate(flags) if flag]

class PatchTests(unittest.TestCase):
    def run_offsets(self, src, votes):
        namespace = {}
        exec(compile(src, "<test>", "exec"), namespace)
        return list(namespace["_pair_candidates"](
            types.SimpleNamespace(step_ms=500), Votes(votes), NpStub))

    def test_diverse_shifts_not_crowded_out(self):
        scores = [0] * 40
        for i in range(12):
            scores[i] = 100 - i
        scores[20], scores[24] = 88, 87
        old = self.run_offsets(BASE, scores)
        new_src, changed = patch(BASE)
        new = self.run_offsets(new_src, scores)
        self.assertTrue(changed)
        self.assertEqual(len(old), 12)
        self.assertNotIn(20, old)
        self.assertNotIn(24, old)
        self.assertIn(20, new)
        self.assertIn(24, new)
        self.assertEqual(new[0], old[0])
        self.assertEqual(len(new), 12)

    def test_threshold_and_other_functions_unchanged(self):
        src, _ = patch(BASE)
        old_ast, new_ast = ast.parse(BASE), ast.parse(src)
        self.assertEqual(ast.dump(old_ast.body[1], include_attributes=False),
                         ast.dump(new_ast.body[1], include_attributes=False))
        self.assertIn("max(15, 15000 // target.step_ms)", src)
        self.assertIn("len(offsets) >= 12", src)

    def test_weak_shift_still_not_candidate(self):
        votes = [0] * 40
        votes[1] = 29
        votes[3] = 28
        src, _ = patch(BASE)
        self.assertEqual(self.run_offsets(src, votes), [])

    def test_reject_unknown_threshold(self):
        with self.assertRaises(ValueError):
            patch(BASE.replace("max(15, 15000 // target.step_ms)",
                               "max(5, 15000 // target.step_ms)"))

    def test_reject_already_patched(self):
        src, _ = patch(BASE)
        with self.assertRaises(ValueError):
            patch(src)

    def test_reject_duplicate_function(self):
        with self.assertRaises(ValueError):
            patch(BASE + "\n" + BASE)

if __name__ == "__main__":
    unittest.main()
