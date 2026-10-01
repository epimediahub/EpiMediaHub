"""One-job retry preserves approvals and keeps the normal worker safeguards."""
from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import random
import sys
import unittest
from unittest import mock

from test_skip_analysis_references import ReferenceFixture
from skip_analysis import register_asset
from skip_analysis_worker import process_one

SERVER = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("retry_fixture", SERVER / "deploy/retry_skip_analysis.py")
retry_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retry_tool)


class RetryTests(ReferenceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.record_id = self.marker()
        with self.db() as con:
            register_asset(con, self.seed, self.seed, self.device)
            con.execute("UPDATE skip_jobs SET status='done'")
            con.execute("INSERT INTO skip_fingerprints VALUES(?,'[1,2,3]',125,2000,26530,'previous')",
                        (self.record_id,))
        self.waiting(status="no_match")

    def test_only_selected_job_and_reference_cache_change_then_worker_creates_pending_proposal(self):
        other_seed = self.descriptor("83", 12, season=3)
        other_id = self.marker(other_seed)
        with self.db() as con:
            register_asset(con, other_seed, other_seed, self.device)
            con.execute("UPDATE skip_jobs SET status='done' WHERE asset_key=?", (other_seed["asset_key"],))
            con.execute("INSERT INTO skip_fingerprints VALUES(?,'[4,5,6]',125,2000,26530,'previous')",
                        (other_id,))
            before = [tuple(row) for row in con.execute("SELECT * FROM skip_records ORDER BY id")]
        result = retry_tool.retry(self.db_path, self.job()["id"], fresh_reference=True)
        self.assertTrue(result["queued"])
        self.assertEqual(result["cleared"], 1)
        with self.db() as con:
            self.assertEqual([tuple(row) for row in con.execute("SELECT * FROM skip_records ORDER BY id")], before)
            self.assertEqual(con.execute("SELECT record_id FROM skip_fingerprints").fetchall()[0][0], other_id)
        rng = random.Random(331)
        reference = [rng.getrandbits(32) for _ in range(80)]
        target = [rng.getrandbits(32) for _ in range(240)] + reference + [rng.getrandbits(32) for _ in range(80)]
        def fingerprint(_source, start, _length, _busy):
            return (target if start == 0 else reference), 125.0
        with mock.patch("skip_analysis_worker.provider_proxy", side_effect=lambda *_: contextlib.nullcontext("fixture")), \
             mock.patch("skip_analysis_worker.probe", return_value=(self.target["duration_ms"], [])), \
             mock.patch("skip_analysis_worker.fingerprint", side_effect=fingerprint):
            self.assertEqual(process_one(self.db), "review")
        with self.db() as con:
            proposal = con.execute("SELECT * FROM skip_records WHERE asset_key=? AND source='audio'",
                                   (self.target["asset_key"],)).fetchone()
            approved = con.execute("SELECT * FROM skip_records WHERE id=?", (self.record_id,)).fetchone()
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(approved["status"], "approved")

    def test_disabled_source_blocks_retry_without_changing_cache_or_markers(self):
        with self.db() as con:
            con.execute("UPDATE skip_analysis_sources SET enabled=0 WHERE playlist_id=1")
        before = hashlib.sha256(self.db_path.read_bytes()).digest()
        with self.assertRaisesRegex(retry_tool.RetryFailure, "^source_disabled$"):
            retry_tool.retry(self.db_path, self.job()["id"], fresh_reference=True)
        self.assertEqual(before, hashlib.sha256(self.db_path.read_bytes()).digest())

    def test_active_worker_lock_blocks_retry(self):
        before = hashlib.sha256(self.db_path.read_bytes()).digest()
        with (self.db_path.parent / "skip-analysis.lock").open("a") as lock:
            retry_tool.fcntl.flock(lock, retry_tool.fcntl.LOCK_EX)
            argv = ["retry", "--job-id", str(self.job()["id"]), "--fresh-reference",
                    "--app-dir", str(SERVER), "--data-dir", str(self.db_path.parent)]
            with mock.patch.object(sys, "argv", argv):
                with contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(retry_tool.main(), 2)
        self.assertEqual(before, hashlib.sha256(self.db_path.read_bytes()).digest())


if __name__ == "__main__":
    unittest.main()
