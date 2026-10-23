"""Pinned verified-marker bridge installer tests. Never writes a live host."""
from pathlib import Path
import hashlib
import importlib.util
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "enable_authenticated_all_playlist_bridge",
    Path(__file__).with_name("enable_authenticated_all_playlist_bridge.py"))
unit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(unit)


def sample_source():
    return b'''def demo():
    ANALYSIS_PLAYLISTS = (8, 10)
    KINDS = ("intro", "recap", "outro")
    rows = []
    chosen = []
    for r in rows:
        if r["playlist_id"] not in ANALYSIS_PLAYLISTS or r["kind"] not in KINDS:
            continue
    return {"from_playlists": list(ANALYSIS_PLAYLISTS)}
'''


class BridgeInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.script = self.root / "bridge.py"
        self.script.write_bytes(sample_source())
        self.store = self.root / "verified.sqlite3"
        with sqlite3.connect(self.store) as db:
            db.execute("CREATE TABLE verified_markers(playlist_id INT)")
            db.executemany("INSERT INTO verified_markers VALUES (?)",
                           [(8,), (10,), (8,)])
        self.patches = [
            patch.object(unit, "SOURCE", self.script),
            patch.object(unit, "PIN", hashlib.sha256(sample_source()).hexdigest()),
            patch.object(unit, "STORE", self.store),
            patch.object(unit, "BACKUP_PARENT", self.root),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def test_exact_version_and_restricted_patch(self):
        raw = unit.patch_source(sample_source())
        self.assertIn(b'type(r["playlist_id"]) is not int', raw)
        self.assertIn(b'sorted({x[2] for x in chosen})', raw)
        self.assertNotIn(b'if r["playlist_id"] not in ANALYSIS_PLAYLISTS', raw)

    def test_unexpected_live_version_fails_closed(self):
        self.script.write_bytes(sample_source() + b"# new revision\n")
        with self.assertRaisesRegex(unit.Stop, "UNEXPECTED_BRIDGE_VERSION"):
            unit.patch_source(self.script.read_bytes())

    def test_staging_does_not_write_to_production_source(self):
        self.assertEqual(unit.database_counts(self.store),
                         {"analysis": 3, "other": 0})
        original = self.script.read_bytes()

        def fake_preflight():
            return original, unit.patch_source(original), self.script.stat(), (
                {"analysis": 3, "other": 0})

        def fake_sync(source, destination):
            # Synthetic equivalent of a newly imported verified customer marker.
            self.assertTrue(Path(source).is_file())
            with sqlite3.connect(destination) as db:
                db.execute("CREATE TABLE verified_markers(playlist_id INT)")
                db.executemany("INSERT INTO verified_markers VALUES (?)",
                               [(8,), (10,), (8,), (55,)])

        with patch.object(unit, "preflight", side_effect=fake_preflight), \
                patch.object(unit, "sync_to", side_effect=fake_sync):
            report = unit.run(apply=False)
        self.assertEqual(report["preflight"], "PASS")
        self.assertEqual(report["candidate"]["other"], 1)
        self.assertEqual(self.script.read_bytes(), original)
        self.assertFalse(report["production_source_modified"])
        self.assertFalse(report["analysis_worker_restarted"])

    def test_staging_refuses_missing_customer_marker_without_touching_source(self):
        original = self.script.read_bytes()

        def fake_sync(_source, destination):
            with sqlite3.connect(destination) as db:
                db.execute("CREATE TABLE verified_markers(playlist_id INT)")
                db.executemany("INSERT INTO verified_markers VALUES (?)",
                               [(8,), (10,), (8,)])
        with patch.object(unit, "preflight", return_value=(
                original, unit.patch_source(original), self.script.stat(),
                {"analysis": 3, "other": 0})), \
                patch.object(unit, "sync_to", side_effect=fake_sync):
            with self.assertRaisesRegex(
                    unit.Stop, "NO_AUTHENTICATED_OTHER_PLAYLIST_SOURCE_IMPORTED"):
                unit.run(apply=True)
        self.assertEqual(self.script.read_bytes(), original)

    def test_missing_store_fails_without_creating_database(self):
        absent = self.root / "missing.sqlite3"
        with self.assertRaises(unit.Stop):
            unit.database_counts(absent)
        self.assertFalse(absent.exists())


if __name__ == "__main__":
    unittest.main()
