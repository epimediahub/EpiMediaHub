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
      CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER,expires_at INTEGER);
      CREATE TABLE episcene_daily_reports(day TEXT,generated_at REAL);
      CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
      INSERT INTO skip_analysis_playlists VALUES(8,0,0),(10,0,0);
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

    def test_pinned_analysis_source_expiry_without_customer_metadata(self):
        db=fixture()
        db.execute("UPDATE skip_analysis_playlists SET expires_at=? WHERE id=8",
                   (NOW+48*3600,))
        db.commit()
        result=adapter.gather(db,NOW)
        self.assertEqual(result["playlists"],[
            {"id":"8","expires_at_epoch":NOW+48*3600}])
        self.assertNotIn("SECRET_SOURCE",json.dumps(result))
        kinds={a.kind for a in evaluate(result,NOW)}
        self.assertIn("playlist_access",kinds)

    def test_dedicated_report_generated_today_creates_info_alert(self):
        from zoneinfo import ZoneInfo
        berlin_day=datetime.fromtimestamp(NOW,ZoneInfo("Europe/Berlin")).date().isoformat()
        db=fixture()
        db.execute("INSERT INTO episcene_daily_reports VALUES(?,?)",
                   (berlin_day,float(NOW-20)))
        db.commit()
        payload=adapter.gather(db,NOW)
        self.assertTrue(payload["daily_report"]["ready"])
        kinds={alert.kind for alert in evaluate(payload,NOW)}
        self.assertIn("daily_report",kinds)
        earlier=adapter.gather(db,NOW+2*24*3600)
        self.assertNotIn("daily_report",earlier)

    def test_untrusted_schema_fail_closed_without_unverified_stall_alarm(self):
        db=sqlite3.connect(':memory:')
        db.execute("CREATE TABLE skip_assets(asset_key TEXT)")
        self.assertEqual(adapter.gather(db,NOW)["analysis_lanes"],[])


if __name__=="__main__":
    unittest.main()
