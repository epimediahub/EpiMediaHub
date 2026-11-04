"""Offline regression tests for V5 protected feedback DB snapshot."""
from pathlib import Path
import os
import sqlite3
import tempfile
import unittest

from fingerprint_manual_reference_shadow_v5 import (
    snapshot_readonly_sqlite, shadow_feedback_snapshot_path
)


class ProtectedFeedbackSnapshotTests(unittest.TestCase):
    def test_private_snapshot_copies_live_wal_and_preserves_source(self):
        with tempfile.TemporaryDirectory(prefix="episcene_test_",dir="/tmp") as d:
            root=Path(d)
            source=root/"source.db"
            target=root/"feedback.db"
            with sqlite3.connect(source) as db:
                db.execute("PRAGMA journal_mode=WAL")
                db.execute("CREATE TABLE feedback_versions(marker_id INTEGER,decision TEXT)")
                db.execute("INSERT INTO feedback_versions VALUES(?,?)",(31,"positive"))
                db.commit()
            os.chmod(source,0o600)
            before_mode=source.stat().st_mode & 0o777
            snapshot_readonly_sqlite(source,target)
            self.assertEqual(source.stat().st_mode & 0o777,before_mode)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            with sqlite3.connect(f"file:{target}?mode=ro",uri=True) as db:
                self.assertEqual(db.execute(
                    "SELECT marker_id,decision FROM feedback_versions").fetchall(),
                    [(31,"positive")])
            self.assertIs(target, target)

    def test_snapshot_must_be_next_to_provisioning_snapshot(self):
        with tempfile.TemporaryDirectory(prefix="episcene_test_",dir="/tmp") as d:
            root=Path(d)
            primary=root/"snapshot.db"
            feedback=root/"feedback.db"
            primary.touch()
            feedback.touch()
            self.assertEqual(shadow_feedback_snapshot_path(str(feedback),primary), feedback)
            with self.assertRaises(RuntimeError):
                shadow_feedback_snapshot_path(str(root/"wrong.db"), primary)
            with self.assertRaises(RuntimeError):
                shadow_feedback_snapshot_path(str(Path(d).parent/"feedback.db"),primary)
            with self.assertRaises(RuntimeError):
                shadow_feedback_snapshot_path("/var/lib/episcene-learning/feedback.sqlite3",primary)

    def test_symlinked_backup_or_source_rejected(self):
        with tempfile.TemporaryDirectory(prefix="episcene_test_",dir="/tmp") as d:
            root=Path(d)
            source=root/"original.db"
            with sqlite3.connect(source) as c:
                c.execute("CREATE TABLE feedback_versions(marker_id INTEGER)")
            link=root/"source-link.db"
            link.symlink_to(source)
            with self.assertRaises(RuntimeError):
                snapshot_readonly_sqlite(link,root/"feedback.db")
            primary=root/"snapshot.db"
            primary.touch()
            backup_symlink=root/"feedback.db"
            backup_symlink.symlink_to(source)
            with self.assertRaises(RuntimeError):
                shadow_feedback_snapshot_path(str(backup_symlink),primary)

    def test_missing_protected_feedback_is_explicit_error(self):
        with tempfile.TemporaryDirectory(prefix="episcene_test_",dir="/tmp") as d:
            with self.assertRaises(RuntimeError):
                snapshot_readonly_sqlite(Path(d)/"missing.sqlite",Path(d)/"feedback.db")


if __name__=="__main__":
    unittest.main()
