"""Read-only progress adapter regressions for EpiScene analysis playlists."""
import json
import sqlite3
import tempfile
from datetime import datetime,timezone
from pathlib import Path
import unittest

import live_analysis_snapshot as adapter
from monitor_rules import evaluate
from monitor_cycle import read_snapshot

NOW=int(datetime(2026,10,16,12,25,tzinfo=timezone.utc).timestamp())


def fixture():
    db=sqlite3.connect(':memory:')
    db.executescript("""
      CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,
        source_key TEXT,stream_id TEXT,extension TEXT);
      CREATE TABLE skip_jobs(id INTEGER,asset_key TEXT,status TEXT,updated_at TEXT);
      CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
      CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
      INSERT INTO skip_analysis_playlists VALUES(8,0),(10,0);
      INSERT INTO skip_analysis_sources VALUES(8,1),(10,0);
      INSERT INTO skip_assets VALUES
       ('HIDDEN_ASSET_8',8,'SECRET_SOURCE_8','1','mp4'),
       ('HIDDEN_ASSET_9',8,'SECRET_SOURCE_8','2','mkv'),
       ('HIDDEN_ASSET_10',10,'SECRET_SOURCE_10','1','mp4');
      INSERT INTO skip_jobs VALUES
       (1,'HIDDEN_ASSET_8','review','2026-10-16T12:00:00Z'),
       (2,'HIDDEN_ASSET_9','queued','2026-10-16T12:00:00Z'),
       (3,'HIDDEN_ASSET_10','no_match','2026-10-16T12:00:00Z');
    """)
    return db


class TestProgressAdapter(unittest.TestCase):
    def test_aggregated_lanes_no_private_data_and_original_db_unchanged(self):
        db=fixture()
        changes=db.total_changes
        payload=adapter.gather(db,NOW)
        self.assertEqual(len(payload["analysis_lanes"]),2)
        self.assertEqual(payload["analysis_lanes"][0]["queued_jobs"],1)
        self.assertTrue(payload["analysis_lanes"][1]["paused"])
        self.assertNotIn('SECRET_SOURCE',json.dumps(payload))
        self.assertNotIn('HIDDEN_ASSET',json.dumps(payload))
        self.assertEqual(db.total_changes,changes)
        alerts=evaluate(payload,NOW)
        self.assertEqual(len(alerts),1)
        self.assertEqual(alerts[0].kind,'analysis_stalled')

    def test_snapshot_is_consumable_by_private_monitor(self):
        payload=adapter.gather(fixture(),NOW)
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/"snapshot.json"
            adapter.safe_write(dest,payload)
            self.assertEqual(dest.stat().st_mode & 0o077,0)
            loaded=read_snapshot(dest,NOW)
            self.assertEqual(loaded,payload)
            dest.chmod(0o644)
            with self.assertRaises(PermissionError):
                adapter.safe_write(dest,payload)

    def test_untrusted_schema_fail_closed_without_unverified_stall_alarm(self):
        db=sqlite3.connect(':memory:')
        db.execute("CREATE TABLE skip_assets(asset_key TEXT)")
        self.assertEqual(adapter.gather(db,NOW)["analysis_lanes"],[])


if __name__=="__main__":
    unittest.main()
