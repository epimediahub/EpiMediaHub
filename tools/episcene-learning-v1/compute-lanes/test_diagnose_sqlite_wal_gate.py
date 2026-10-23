"""Read-only systemd/SQLite diagnostic tests with synthetic database."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location(
    "diagnose_sqlite_wal_gate", Path(__file__).with_name("diagnose_sqlite_wal_gate.py"))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Fake:
    returncode = 0
    stdout = """ActiveState=failed
SubState=failed
Result=exit-code
ExecMainStatus=1
ProtectSystem=strict
ReadWritePaths=/var/lib/episcene-learning /secret/private
Environment=DO_NOT_EXPORT
"""


class DiagnoseSqliteWalGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.db = self.dir / "test.sqlite3"
        with sqlite3.connect(self.db) as connection:
            connection.execute("CREATE TABLE skip_assets (asset_key TEXT, playlist_id INT, title TEXT, duration_ms INT, season INT, episode INT)")

    def tearDown(self):
        self.tmp.cleanup()

    def test_readonly_pragma_does_not_mutate_database(self):
        original = self.db.read_bytes()
        result = module.sqlite_probe(self.db)
        self.assertEqual(result["state"], "readable")
        self.assertTrue(result["schema_present"])
        self.assertEqual(self.db.read_bytes(), original)

    def test_no_secrets_or_paths_from_systemd_output(self):
        values = module.service_properties(call=lambda *args, **kwargs: Fake())
        self.assertEqual(values["ReadWritePaths"], {"configured": True})
        self.assertEqual(values["ExecMainStatus"], 1)
        self.assertNotIn("DO_NOT_EXPORT", str(values))
        self.assertNotIn("/secret/", str(values))

    def test_missing_database_not_created(self):
        missing = self.dir / "missing.sqlite3"
        result = module.sqlite_probe(missing)
        self.assertEqual(result["state"], "path_unavailable")
        self.assertFalse(missing.exists())

    def test_file_metadata_contains_no_contents(self):
        self.assertEqual(module.details(self.db)["state"], "present")
        self.assertNotIn("CREATE TABLE", str(module.details(self.db)))


if __name__ == "__main__":
    unittest.main()
