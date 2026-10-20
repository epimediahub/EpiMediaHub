import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from audit_playlist_paths import report


class SourceAuditTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = self.root / 'provisioning.db'
        with sqlite3.connect(self.db) as con:
            con.executescript("""
                CREATE TABLE customer_playlists (
                    id INTEGER PRIMARY KEY, username TEXT, password TEXT, url TEXT
                );
                CREATE TABLE skip_assets (
                    id INTEGER PRIMARY KEY, playlist_id INTEGER, stream_url TEXT
                );
                CREATE TABLE skip_jobs (
                    id INTEGER PRIMARY KEY, playlist_id INTEGER, status TEXT
                );
                INSERT INTO customer_playlists VALUES (
                    8, 'SECRET_USER_X', 'SECRET_PASSWORD_X', 'https://secret.example/test'
                );
                INSERT INTO skip_assets VALUES (
                    1, 8, 'https://secret.example/SECRET_USER_X/SECRET_PASSWORD_X'
                );
                INSERT INTO skip_assets VALUES (2, 10, 'https://secret.example/old');
                INSERT INTO skip_jobs VALUES (1, 8, 'failed');
            """)
        (self.root / 'skip_catalogue.py').write_text(
            "PROVIDER_PASSWORD = 'SECRET_PASSWORD_X'\n"
            "stream_url = 'https://secret.example/SECRET_USER_X'\n"
        )

    def test_no_secrets_in_output(self):
        result = report(self.db, self.root)
        serialized = json.dumps(result)
        for leak in ('SECRET_USER_X', 'SECRET_PASSWORD_X', 'secret.example'):
            self.assertNotIn(leak, serialized)
        self.assertEqual('READ_ONLY', result['database']['status'])
        self.assertEqual(
            {'8': 1, '10': 1},
            result['database']['tables']['skip_assets']['records_per_analysis_playlist']
        )
        self.assertEqual(
            2, result['source_references']['skip_catalogue.py']['matching_lines']
        )

    def test_no_db_modification(self):
        report(self.db, self.root)
        with sqlite3.connect(self.db) as con:
            password = con.execute(
                'SELECT password FROM customer_playlists WHERE id=8'
            ).fetchone()[0]
            self.assertEqual('SECRET_PASSWORD_X', password)

    def test_missing_db_is_safe(self):
        self.assertEqual(
            'SOURCE_UNAVAILABLE',
            report(self.root / 'missing.db', self.root)['database']['status']
        )


if __name__ == '__main__':
    unittest.main()
