"""Synthetic ownership and cross-cut tests; no production DB or provider calls."""
from pathlib import Path
import importlib.util
import sqlite3
import sys
import unittest

spec=importlib.util.spec_from_file_location(
    "asset_registry_scope",Path(__file__).with_name("asset_registry_scope.py"))
scope=importlib.util.module_from_spec(spec)
sys.modules[spec.name]=scope
spec.loader.exec_module(scope)


class ScopedRegistryTests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:")
        self.db.executescript("""
        CREATE TABLE customers(id INTEGER,enabled INTEGER);
        CREATE TABLE devices(id INTEGER,customer_id INTEGER,enabled INTEGER);
        CREATE TABLE customer_playlists(id INTEGER,customer_id INTEGER);
        CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER,duration_ms INTEGER);
        INSERT INTO customers VALUES(10,1),(20,1);
        INSERT INTO devices VALUES(1,10,1),(2,20,1);
        INSERT INTO customer_playlists VALUES(55,10),(77,20);
        INSERT INTO skip_assets VALUES('shared-key',77,2000000);
        """)
        scope.schema(self.db)

    def tearDown(self):
        self.db.close()

    def asset(self,playlist=55,duration=3000000,episode=1):
        return scope.Asset(playlist,"shared-key","The Lincoln Lawyer",
                           "episode",4,episode,duration,"314159","mkv")

    def test_same_key_different_playlists_and_cuts_are_isolated(self):
        self.assertEqual(scope.register_authenticated(self.db,1,self.asset()),"registered")
        self.assertEqual(scope.register_authenticated(
            self.db,2,self.asset(playlist=77,duration=2000000)),"registered")
        self.assertEqual(scope.lookup_owned(self.db,1,55,"shared-key")["duration_ms"],3000000)
        self.assertEqual(scope.lookup_owned(self.db,2,77,"shared-key")["duration_ms"],2000000)
        self.assertIsNone(scope.lookup_owned(self.db,1,55,"does-not-exist"))
        # Never mutate global legacy asset row or a row owned by another user.
        self.assertEqual(self.db.execute("SELECT playlist_id,duration_ms FROM skip_assets").fetchone(),
                         (77,2000000))

    def test_other_device_cannot_claim_foreign_playlist(self):
        with self.assertRaisesRegex(scope.Conflict,"NOT_AUTHORIZED"):
            scope.register_authenticated(self.db,1,self.asset(playlist=77))
        self.assertIsNone(scope.lookup_owned(self.db,2,77,"shared-key"))

    def test_no_replace_when_episode_or_runtime_drift(self):
        scope.register_authenticated(self.db,1,self.asset())
        self.assertEqual(scope.register_authenticated(self.db,1,self.asset()),"already_registered")
        with self.assertRaisesRegex(scope.Conflict,"SCOPED_MEDIA_IDENTITY_CONFLICT"):
            scope.register_authenticated(self.db,1,self.asset(duration=2000000))
        with self.assertRaisesRegex(scope.Conflict,"SCOPED_MEDIA_IDENTITY_CONFLICT"):
            scope.register_authenticated(self.db,1,self.asset(episode=2))
        self.assertEqual(scope.lookup_owned(self.db,1,55,"shared-key")["episode"],1)

    def test_authentication_checks_are_live(self):
        scope.register_authenticated(self.db,1,self.asset())
        self.db.execute("UPDATE devices SET enabled=0 WHERE id=1")
        with self.assertRaisesRegex(scope.Conflict,"NOT_AUTHORIZED"):
            scope.lookup_owned(self.db,1,55,"shared-key")

    def test_invalid_asset_rejected(self):
        with self.assertRaisesRegex(scope.Conflict,"UNTRUSTED_MEDIA_METADATA"):
            scope.register_authenticated(self.db,1,self.asset(duration=-1))


if __name__=="__main__":
    unittest.main()
