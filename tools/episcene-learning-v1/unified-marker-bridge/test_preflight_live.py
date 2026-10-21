"""Read-only production preflight regression tests without host access."""
from __future__ import annotations
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from preflight_live import diagnostic, inspect_db, regular_file, REQUIRED_PRODUCTION

def schema(folder):
    production = folder / "production.sqlite3"
    feedback = folder / "feedback.sqlite3"
    backend = folder / "backend"
    backend.mkdir()
    with sqlite3.connect(production) as db:
        db.execute("""CREATE TABLE skip_assets(
            asset_key TEXT, playlist_id INT, title TEXT, season INT,
            episode INT, duration_ms INT)""")
        db.execute("""CREATE TABLE skip_records(
            id INT, asset_key TEXT, start_ms INT,end_ms INT,
            segment_type TEXT,status TEXT)""")
        db.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?)",
                   ("customer-SECRET-DO-NOT-PRINT", 8, "SECRET_TV_TITLE_DO_NOT_PRINT", 1, 1, 40000))
    with sqlite3.connect(feedback) as db:
        db.execute("""CREATE TABLE feedback_versions(
            marker_id INT,asset_key TEXT,playlist_id INT,season INT,episode INT,
            kind TEXT,decision TEXT,active INT,start_ms INT,end_ms INT,
            provenance TEXT,reviewed_at TEXT)""")
    for name in ("skip_markers.py", "skip_release.py", "skip_analysis.py"):
        (backend / name).write_text("# dummy backend stub\n")
    return {
        "production_db": str(production),
        "feedback_db": str(feedback),
        "backend_root": str(backend),
        "unified_db": str(folder / "unified.sqlite3"),
        "bridge_root": str(folder / "missing-bridge"),
        "service_unit": str(folder / "nonexistent.service"),
        "timer_unit": str(folder / "nonexistent.timer"),
    }

class ReadOnlyPreflightTests(unittest.TestCase):
    def test_no_customer_secrets_or_identifiers_in_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = schema(folder)
            before = Path(paths["production_db"]).read_bytes()
            report = diagnostic(paths, active=True)
            printed = json.dumps(report)
            self.assertEqual(report["preflight_for_private_snapshot"], "PASS")
            for secret in ("customer-SECRET", "SECRET_TV_TITLE_DO_NOT_PRINT", "source_url",
                           "playlist_password", "token=", "customer_id"):
                self.assertNotIn(secret, printed)
            self.assertTrue(report["no_database_or_service_modified"])
            self.assertEqual(Path(paths["production_db"]).read_bytes(), before)
            self.assertEqual(report["public_marker_api_connected"], "NOT_VERIFIED")

    def test_missing_feedback_blocks_safely(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = schema(Path(tmp))
            Path(paths["feedback_db"]).unlink()
            report = diagnostic(paths, active=True)
            self.assertEqual(report["preflight_for_private_snapshot"], "BLOCKED")
            self.assertFalse(report["authenticated_feedback_db"]["exists"])

    def test_symlink_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            paths = schema(folder)
            link = folder / "link.sqlite3"
            link.symlink_to(paths["production_db"])
            self.assertFalse(regular_file(link))
            self.assertFalse(inspect_db(link, REQUIRED_PRODUCTION)["exists"])

    def test_backend_files_and_running_service_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            paths = schema(Path(tmp))
            report = diagnostic(paths, active=False)
            self.assertEqual(report["preflight_for_private_snapshot"], "BLOCKED")
            Path(paths["backend_root"], "skip_analysis.py").unlink()
            report = diagnostic(paths, active=True)
            self.assertFalse(report["existing_backend_file_checks"]["skip_analysis.py"])
            self.assertEqual(report["preflight_for_private_snapshot"], "BLOCKED")

if __name__ == "__main__":
    unittest.main()
