#!/usr/bin/env python3
import json
import sqlite3
import unittest
import audit_metadata_coverage as audit

class CoverageTests(unittest.TestCase):
    def test_reports_only_aggregates_not_names(self):
        db=sqlite3.connect(':memory:')
        db.executescript("""
          CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER);
          CREATE TABLE skip_asset_languages(asset_key TEXT,codes TEXT);
          CREATE TABLE skip_series_languages(playlist_id INTEGER,series_id TEXT,codes TEXT);
          CREATE TABLE skip_catalogue_series(playlist_id INTEGER,series_id TEXT,payload_json TEXT);
          CREATE TABLE skip_catalogue_episodes(playlist_id INTEGER,series_id TEXT,asset_key TEXT);
          CREATE TABLE skip_language_priority(asset_key TEXT,priority INTEGER);
          INSERT INTO skip_assets VALUES ('private-asset-id',8),('some-key',10);
          INSERT INTO skip_asset_languages VALUES ('private-asset-id','[]');
          INSERT INTO skip_series_languages VALUES (8,'secret-series','["de"]');
          INSERT INTO skip_catalogue_series VALUES
            (8,'secret-series','{"name":"Secret TV Name","category_id":"17","stream_url":"https://private.test","language_priority":0}');
          INSERT INTO skip_catalogue_episodes VALUES (8,'secret-series','private-asset-id');
          INSERT INTO skip_language_priority VALUES ('private-asset-id',0);
        """)
        result=audit.report(db)
        self.assertEqual(result['by_playlist']['8']['series_language_codes']['populated'],1)
        self.assertEqual(result['by_playlist']['8']['asset_language_codes']['populated'],0)
        self.assertEqual(result['by_playlist']['8']['catalogue_priority_distribution']['0'],1)
        self.assertIn('category_id',result['catalogue_payload_keys']['8']['matching_keys'])
        view=json.dumps(result)
        for secret in ('secret-series','Secret TV Name','private-asset-id','private.test'):
            self.assertNotIn(secret,view)

    def test_missing_tables_are_not_assumed(self):
        db=sqlite3.connect(':memory:')
        data=audit.report(db)
        self.assertEqual(data['table_inventory']['skip_catalogue_series'],False)
        self.assertIsNone(data['by_playlist']['8']['series_language_codes'])

if __name__=='__main__':
    unittest.main()
