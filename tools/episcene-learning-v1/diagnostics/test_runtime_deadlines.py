#!/usr/bin/env python3
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import runtime_deadlines as m


class RuntimeTriageTest(unittest.TestCase):
    def make_db(self, folder):
        path = folder / "db.sqlite"
        with sqlite3.connect(path) as db:
            db.executescript("""
                CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER);
                CREATE TABLE skip_jobs(asset_key TEXT,status TEXT,updated_at TEXT);
                CREATE TABLE skip_records(
                    id INTEGER,asset_key TEXT,source TEXT,status TEXT,segment_type TEXT);
                CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT);
                INSERT INTO skip_assets VALUES ('secret_episode_1',8),
                                               ('secret_episode_2',10);
                INSERT INTO skip_jobs VALUES ('secret_episode_1','partial','2026-10-22T15:00:00Z'),
                                            ('secret_episode_2','review','2026-10-22T15:00:00Z');
                INSERT INTO skip_records VALUES
                      (1,'secret_episode_1','episcene','pending','intro'),
                      (2,'secret_episode_2','audio_repetition','pending','outro');
                INSERT INTO skip_auto_evidence VALUES
                      (1,'{"method":"episcene_consensus","decision":{"status":"REVIEW"}}');
            """)
        return path

    def test_counts_and_no_mutation_or_identifiers(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_db(Path(td))
            before = path.read_bytes()
            with mock.patch.object(m, "configured_budgets", return_value={}), \
                 mock.patch.object(m, "service_states", return_value={}), \
                 mock.patch.object(m, "journal_counts", return_value={}):
                data = m.report(path)
            self.assertEqual(data["jobs"]["8"]["status_counts"]["partial"], 1)
            self.assertEqual(data["jobs"]["10"]["status_counts"]["review"], 1)
            self.assertEqual(data["pending_release_blockers"]["VISUAL_NOT_AUTO_CONFIRMED"], 1)
            self.assertTrue(data["time_budget_suspected"])
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn("secret_episode", json.dumps(data))
            self.assertFalse(data["production_db_modified"])

    def test_budget_inventory_never_outputs_secrets_or_source(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "skip_analysis_worker.py"
            p.write_text("MAX_ANALYSIS_TIMEOUT=300\nTOKEN='private'\nPASSWORD=4444\n"
                         "def f():\n    deadline_seconds=600\n")
            with mock.patch.object(m, "PROVISIONING", Path(td)), \
                 mock.patch.object(m, "REMOTE", Path(td)):
                found = m.configured_budgets()["skip_analysis_worker.py"]
            self.assertEqual(found["named_numeric_budget_assignments"],
                             {"MAX_ANALYSIS_TIMEOUT": 300, "deadline_seconds": 600})
            self.assertNotIn("private", json.dumps(found))
            self.assertNotIn("PASSWORD", json.dumps(found))

    def test_dates_and_logs_are_bounded(self):
        self.assertIsNone(m.date_seconds("nonsense"))
        self.assertIsNotNone(m.date_seconds("2026-10-22T15:00:00Z"))
        with mock.patch.object(m, "run", return_value=(0, "timeout for user 123\npartial\n")),
             mock.patch.object(m, "SERVICE_NAMES", ("fake.service",)):
            data = m.journal_counts()
            self.assertEqual(data["fake.service"]["timeouts"], 1)
            self.assertEqual(data["fake.service"]["partial"], 1)


if __name__ == "__main__":
    unittest.main()
