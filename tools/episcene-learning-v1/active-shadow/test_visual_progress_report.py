#!/usr/bin/env python3
"""Verify the visual progress report never writes to production datasets."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from test_visual_shadow_capture import fixture
import visual_shadow_capture
import visual_progress_report


def report(original,shadow,capture=None):
    with sqlite3.connect(original.resolve().as_uri()+'?mode=ro',uri=True) as db,\
         sqlite3.connect(shadow.resolve().as_uri()+'?mode=ro',uri=True) as sh:
        if capture is None:
            return visual_progress_report.compare(db,sh,None)
        with sqlite3.connect(capture.resolve().as_uri()+'?mode=ro',uri=True) as frames:
            return visual_progress_report.compare(db,sh,frames)


class VisualProgressTests(unittest.TestCase):
    def test_before_and_after_single_window_with_original_db_immutable(self):
        with tempfile.TemporaryDirectory() as td:
            original,shadow,capture=fixture(Path(td))
            before=original.read_bytes()
            first=report(original,shadow)
            self.assertEqual(first['expected_targets'],6)
            self.assertEqual(first['completed'],0)
            self.assertEqual(first['new_auto_approvals'],0)
            fake=lambda task,dbfactory: [[1,2,3,4] for _ in range(80)]
            visual_shadow_capture.run(original,shadow,capture,fetcher=fake)
            second=report(original,shadow,capture)
            self.assertEqual(second['completed'],1)
            self.assertEqual(second['reference_completed'],1)
            self.assertEqual(second['candidate_completed'],0)
            self.assertEqual(second['new_verified_labels'],0)
            self.assertEqual(original.read_bytes(),before)
            ready=[item for item in second['results'] if item['status']=='VISUAL_HASHES_READY']
            self.assertEqual(len(ready),1)
            self.assertEqual(ready[0]['brightness_shift'],0)
            self.assertEqual(ready[0]['immediate_frame_change'],0)

    def test_metadata_revision_invalidates_old_visual_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            original,shadow,capture=fixture(Path(td))
            visual_shadow_capture.run(original,shadow,capture,
                fetcher=lambda task,dbfactory:[[1,2,3,4] for _ in range(80)])
            with sqlite3.connect(original) as db:
                db.execute("UPDATE skip_assets SET updated_at='2026-10-15' WHERE asset_key='mob-2'")
            updated=report(original,shadow,capture)
            self.assertEqual(updated['completed'],0)
            self.assertIn('STALE_ASSET_VERSION',updated['statuses'])

    def test_motion_and_brightness_shift_are_descriptive_not_approval(self):
        pre=[[1,1,40,155] for _ in range(40)]
        post=[[2,2,15,30] for _ in range(40)]
        m=visual_progress_report.stats(pre+post)
        self.assertGreater(m['brightness_shift'],100)
        self.assertGreater(m['contrast_shift'],20)
        self.assertGreater(m['immediate_frame_change'],0)
        self.assertNotIn('approved',m)


if __name__=='__main__':
    unittest.main(verbosity=2)
