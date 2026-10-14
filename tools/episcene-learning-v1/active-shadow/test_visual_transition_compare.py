#!/usr/bin/env python3
"""EpiScene reference image comparison: descriptive only, zero production writes."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

import visual_shadow_capture as capture
import visual_progress_report as progress
import visual_transition_compare as compare
from test_visual_shadow_capture import fixture


def read(original,shadow,frames=None):
    with sqlite3.connect(original.resolve().as_uri()+"?mode=ro",uri=True) as db, \
         sqlite3.connect(shadow.resolve().as_uri()+"?mode=ro",uri=True) as sh:
        if frames is None:
            return compare.assess(progress.compare(db,sh))
        with sqlite3.connect(frames.resolve().as_uri()+"?mode=ro",uri=True) as cache:
            return compare.assess(progress.compare(db,sh,cache))


class Comparisons(unittest.TestCase):
    def test_zero_and_partial_captures_never_claim_verification(self):
        with tempfile.TemporaryDirectory() as td:
            src,shadow,out=fixture(Path(td))
            b=src.read_bytes()
            initial=read(src,shadow)
            self.assertEqual(initial['status'],"WAITING_FOR_AT_LEAST_3_REFERENCE_WINDOWS")
            self.assertEqual(initial['new_auto_approvals'],0)
            capture.run(src,shadow,out,
                fetcher=lambda t,f:[[1,1,40,150] for _ in range(80)])
            partial=read(src,shadow,out)
            self.assertEqual(partial['reference_ready'],1)
            self.assertEqual(partial['candidate_ready'],0)
            self.assertEqual(partial['new_verified_labels'],0)
            self.assertEqual(src.read_bytes(),b)

    def test_candidate_outlier_vs_reference_images_remains_unapproved(self):
        with tempfile.TemporaryDirectory() as td:
            src,shadow,out=fixture(Path(td))
            b=src.read_bytes()
            def fake(task,factory):
                if task["type"]=="reference":
                    return [[1,1,20,160] for _ in range(40)] + \
                           [[2,2,55,40] for _ in range(40)]
                return [[3,3,20,160] for _ in range(80)]
            for _ in range(6):
                capture.run(src,shadow,out,fetcher=fake)
            result=read(src,shadow,out)
            self.assertEqual(result['reference_ready'],5)
            self.assertEqual(result['candidate_ready'],1)
            self.assertTrue(result['source_capture_complete'])
            self.assertEqual(result['status'],"COMPARISON_AVAILABLE")
            self.assertGreater(result['candidates'][0]['distance_from_reference_profile'],0)
            self.assertFalse(result['candidates'][0]['credits_start_verified'])
            self.assertFalse(result['candidates'][0]['eligible_for_automatic_release'])
            self.assertEqual(result['new_auto_approvals'],0)
            self.assertEqual(src.read_bytes(),b)

    def test_without_any_reference_profile_only_wait(self):
        r={"completed":1,"expected_targets":5,"pending_ids":[11,12,13,14],
           "results":[dict(id=1,kind="candidate",status="VISUAL_HASHES_READY")]}
        result=compare.assess(r)
        self.assertEqual(result["status"],"WAITING_FOR_AT_LEAST_3_REFERENCE_WINDOWS")
        self.assertEqual(result["candidate_ready"],1)
        self.assertEqual(result["candidates"][0]["status"],"WAITING_FOR_REFERENCE_PROFILE")


if __name__=="__main__":
    unittest.main(verbosity=2)
