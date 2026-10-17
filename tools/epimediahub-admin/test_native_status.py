import sqlite3
import tempfile
import unittest
from pathlib import Path
from native_status import read_status, summarize

SCHEMA="""
CREATE TABLE skip_analysis_playlists(id INTEGER PRIMARY KEY, archived INTEGER, config_json TEXT);
CREATE TABLE skip_analysis_sources(playlist_id INTEGER PRIMARY KEY, enabled INTEGER);
CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,stream_id TEXT);
CREATE TABLE skip_jobs(asset_key TEXT,status TEXT,updated_at TEXT);
INSERT INTO skip_analysis_playlists VALUES
 (8,0,'{"provider_url":"DO_NOT_OUTPUT"}'),
 (10,0,'{"provider_url":"DO_NOT_OUTPUT"}');
INSERT INTO skip_analysis_sources VALUES(8,1),(10,1);
INSERT INTO skip_assets VALUES('asset8',8,'SECRET_CUSTOMER'),('asset10',10,'SECRET_CUSTOMER');
INSERT INTO skip_jobs VALUES
 ('asset8','done','2026-10-17T14:00:00Z'),
 ('asset10','queued','2026-10-17T14:01:00Z');
"""
class NativeStatusTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path=Path(self.folder.name)/"episcene.sqlite3"
        with sqlite3.connect(self.path) as c:c.executescript(SCHEMA)

    def test_dedicated_sources_only(self):
        result=read_status(self.path)
        self.assertEqual([lane["id"] for lane in result["lanes"]],[8,10])
        self.assertEqual(result["lanes"][0]["completed"],1)
        self.assertEqual(result["lanes"][1]["queued"],1)
        self.assertNotIn("DO_NOT_OUTPUT",str(result))
        self.assertNotIn("SECRET_CUSTOMER",str(result))
        self.assertEqual(result["scope"],"independent_analysis_sources_only")

    def test_disabled_source_visible_not_false_healthy(self):
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE skip_analysis_sources SET enabled=0 WHERE playlist_id=10")
        self.assertFalse(read_status(self.path)["lanes"][1]["enabled"])

    def test_missing_source_fails_closed(self):
        with sqlite3.connect(self.path) as c:
            c.execute("DELETE FROM skip_analysis_sources WHERE playlist_id=10")
        self.assertFalse(read_status(self.path)["lanes"][1]["enabled"])

    def test_missing_schema_fails_closed(self):
        with sqlite3.connect(self.path) as c:c.execute("DROP TABLE skip_jobs")
        with self.assertRaisesRegex(RuntimeError,"SCHEMA"):
            read_status(self.path)

    def test_requires_file_and_disallows_symlink(self):
        with self.assertRaisesRegex(RuntimeError,"MISSING"):
            read_status(self.path.parent/"missing.db")
        alias=self.path.parent/"shortcut"
        alias.symlink_to(self.path)
        with self.assertRaisesRegex(RuntimeError,"MISSING"):
            read_status(alias)

    def test_queued_is_not_counted_as_completed(self):
        with sqlite3.connect(self.path) as c:
            c.execute("UPDATE skip_jobs SET status='queued' WHERE asset_key='asset8'")
        status=read_status(self.path)
        self.assertEqual(status["lanes"][0]["completed"],0)
        self.assertIsNone(status["lanes"][0]["last_completion_epoch"])

if __name__=="__main__":unittest.main()
