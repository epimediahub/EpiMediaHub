import sqlite3
import unittest

import new_4k_catalogue_preflight as m


class New4kPreflightTests(unittest.TestCase):
    def make_db(self):
        db=sqlite3.connect(":memory:")
        db.row_factory=sqlite3.Row
        db.executescript("""
            CREATE TABLE skip_analysis_playlists(id INTEGER,archived INTEGER);
            CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
            CREATE TABLE skip_assets(asset_key TEXT, playlist_id INTEGER, updated_at TEXT);
            CREATE TABLE skip_jobs(asset_key TEXT,status TEXT, updated_at TEXT);
            CREATE TABLE skip_catalogue_episodes(
                playlist_id INTEGER,asset_key TEXT,seen_generation INTEGER);
            INSERT INTO skip_analysis_playlists VALUES(8,0),(10,0);
            INSERT INTO skip_analysis_sources VALUES(8,1),(10,1);
            INSERT INTO skip_assets VALUES
              ('8-old',8,'2026-10-20T08:00:00Z'),
              ('8-new',8,'2026-10-23T08:00:00Z'),
              ('8-unmapped',8,'2026-10-20T08:00:00Z'),
              ('10-keep',10,'2026-10-23T08:00:00Z');
            INSERT INTO skip_jobs VALUES
              ('8-old','failed','2026-10-23T09:00:00Z'),
              ('8-new','queued','2026-10-23T09:00:00Z'),
              ('8-unmapped','queued','2026-10-22T09:00:00Z'),
              ('10-keep','queued','2026-10-23T09:00:00Z');
            INSERT INTO skip_catalogue_episodes VALUES
              (8,'8-old',4),(8,'8-new',5),(10,'10-keep',7);
        """)
        return db

    def test_stale_and_unmapped_jobs_are_separated_without_writing(self):
        db=self.make_db()
        before=db.total_changes
        result=m.snapshot(db,1792749600.0)
        self.assertEqual(result['catalogue_generation_verification'],
                         'OBSERVED_NUMERIC_GENERATIONS_NOT_VERIFIED_COMPLETE')
        self.assertEqual(result['latest_generation_catalogue_episodes'],1)
        self.assertEqual(result['previous_generations_catalogue_episodes'],1)
        self.assertEqual(result['jobs_by_catalogue_generation']['failed']['OLDER_OR_ZERO'],1)
        self.assertEqual(result['jobs_by_catalogue_generation']['queued']['LATEST'],1)
        self.assertEqual(result['jobs_by_catalogue_generation']['queued']['UNMAPPED'],1)
        self.assertFalse(result['safe_to_disable_old_jobs'])
        self.assertNotIn('10-keep',str(result))
        self.assertNotIn('8-new',str(result))
        self.assertEqual(db.total_changes,before)
        db.close()

    def test_no_catalogue_is_not_claimed_as_stale(self):
        db=self.make_db()
        db.execute("DELETE FROM skip_catalogue_episodes WHERE playlist_id=8")
        result=m.snapshot(db,1792749600.0)
        self.assertEqual(result['catalogue_generation_verification'],
                         'NO_NONZERO_CATALOGUE_GENERATION')
        self.assertFalse(result['safe_to_disable_old_jobs'])
        db.close()

    def test_unexpected_schema_fails_closed(self):
        db=sqlite3.connect(':memory:')
        with self.assertRaisesRegex(RuntimeError,'STOP_UNKNOWN_PRODUCTION_SCHEMA'):
            m.snapshot(db,1792749600.0)
        db.close()

    def test_parse_utc_timestamps(self):
        self.assertAlmostEqual(m.parsed("2026-10-23T08:00:00Z"),
                               m.parsed("2026-10-23T08:00:00+00:00"))
        self.assertIsNone(m.parsed("not a real date"))


if __name__=="__main__":
    unittest.main()
