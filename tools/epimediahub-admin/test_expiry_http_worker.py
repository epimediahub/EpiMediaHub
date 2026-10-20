"""Synthetic daily HTTP observation tests; no network and no real IPTV secrets."""
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock

from expiry_http_worker import refresh,DailyRefreshUnavailable
from expiry_http_snapshot import read_snapshot,InsecureSnapshotUnavailable
from expiry_report_coverage import preview
from xtream_expiry_refresh import ProviderHttpError


class HttpObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"provisioning.db"
        self.cache=self.root/"admin-mobile"/"expiry-http.sqlite3"
        self.verified=self.root/"admin-mobile"/"expiry-cache.sqlite3"
        self.now=datetime(2026,10,20,17,0,tzinfo=timezone.utc)
        with sqlite3.connect(self.db) as con:
            con.executescript("""
                CREATE TABLE customers(
                    id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,reseller_id INTEGER);
                CREATE TABLE customer_playlists(
                    id INTEGER PRIMARY KEY,customer_id INTEGER,name TEXT,
                    enabled INTEGER,config_json TEXT);
                INSERT INTO customers VALUES(1,'Test Alice',1,NULL),(2,'Test Bob',1,1);
            """)
            for ident,cust,provider,username in [
                (11,1,"http://provider.example:8080","PRIVATE_ALICE"),
                (12,2,"http://provider.example:8080","PRIVATE_BOB"),
                (13,2,"http://provider2.example:8080","PRIVATE_CHARLIE")]:
                con.execute("INSERT INTO customer_playlists VALUES(?,?,?,?,?)",(
                    ident,cust,"THE BEST" if ident!=13 else "4K IPTV",1,
                    json.dumps({"playlist_type":"XTREAM",
                                "xtream_server":provider,
                                "xtream_username":username,
                                "xtream_password":"VERY_PRIVATE_PASSWORD_"+str(ident)})))

    def tearDown(self):self.tmp.cleanup()

    def _run(self,fetch,clock=None):
        with mock.patch.dict(os.environ,{"EPIMEDIAHUB_XTREAM_DAILY_HTTP_APPROVED":"YES"}):
            return refresh(database=self.db,cache=self.cache,
                           now=clock or self.now,http_fetch=fetch)

    def test_requires_fresh_explicit_approval_and_does_not_touch_db(self):
        with mock.patch.dict(os.environ,{"EPIMEDIAHUB_XTREAM_DAILY_HTTP_APPROVED":"NO"}):
            with self.assertRaises(DailyRefreshUnavailable):
                refresh(database=self.db,cache=self.cache)
        self.assertFalse(self.cache.exists())
        self.assertFalse(self.cache.with_name("expiry-http.key").exists())

    def test_success_undated_http_denied_and_private_partial_preview(self):
        def fake(origin,user,password):
            self.assertTrue(password.startswith("VERY_PRIVATE_PASSWORD_"))
            if user=="PRIVATE_ALICE":
                return {"user_info":{"username":user,"exp_date":1792531200}}
            if user=="PRIVATE_BOB":
                return {"user_info":{"username":user,"exp_date":"0"}}
            raise ProviderHttpError(403)
        result=self._run(fake)
        self.assertEqual(result["active_xtream_accounts"],3)
        self.assertEqual(result["dates_observed_over_unverified_transport"],1)
        self.assertEqual(result["unverified_or_unknown"],2)
        self.assertEqual(result["result_counts"]["provider_http_4xx"],1)
        self.assertNotIn("PRIVATE_",json.dumps(result))
        self.assertNotIn("provider.example",json.dumps(result))
        self.assertFalse(self.verified.exists())  # authoritative feed untouched
        view=preview(self.db,self.verified,self.now)
        self.assertEqual(view["confirmed_accounts"],0)
        self.assertEqual(view["http_observed_accounts"],1)
        self.assertEqual(view["unverified_accounts"],2)
        self.assertFalse(view["snapshot_complete"])
        entries=[row for group in view["playlists"] for row in group["entries"]]
        self.assertEqual(sorted(x["status"] for x in entries),
                         ["http_observed","unverified","unverified"])
        self.assertNotIn("VERY_PRIVATE_PASSWORD",json.dumps(view))
        self.assertNotIn("PRIVATE_ALICE",json.dumps(view))
        self.assertEqual(self.cache.stat().st_mode & 0o077,0)
        self.assertEqual(self.cache.with_name("expiry-http.key").stat().st_mode & 0o077,0)

    def test_second_run_replaces_every_row_failed_date_cannot_stay_current(self):
        self._run(lambda o,u,p:{"user_info":{"username":u,"exp_date":"1792531200"}})
        first=preview(self.db,self.verified,self.now)
        self.assertEqual(first["http_observed_accounts"],3)
        self._run(lambda o,u,p:{"user_info":{"username":u,"exp_date":"0"}},
                  clock=self.now+timedelta(days=1))
        second=preview(self.db,self.verified,self.now+timedelta(days=1))
        self.assertEqual(second["http_observed_accounts"],0)
        self.assertEqual(second["unverified_accounts"],3)
        self.assertFalse(second["snapshot_complete"])

    def test_rotated_credentials_break_stale_identity_mapping(self):
        self._run(lambda o,u,p:{"user_info":{"username":u,"exp_date":"1792531200"}})
        with sqlite3.connect(self.db) as con:
            raw=con.execute("SELECT config_json FROM customer_playlists WHERE id=11").fetchone()[0]
            changed=json.loads(raw)
            changed["xtream_password"]="ROTATED_PRIVATE_PASSWORD"
            con.execute("UPDATE customer_playlists SET config_json=? WHERE id=11",
                        (json.dumps(changed),))
        view=preview(self.db,self.verified,self.now)
        self.assertEqual(view["http_observed_accounts"],2)
        self.assertEqual(view["unverified_accounts"],1)
        self.assertNotIn("ROTATED_PRIVATE_PASSWORD",json.dumps(view))

    def test_old_snapshot_not_treated_as_current(self):
        self._run(lambda o,u,p:{"user_info":{"username":u,"exp_date":"1792531200"}})
        after=self.now+timedelta(days=3)
        view=preview(self.db,self.verified,after)
        self.assertEqual(view["http_observed_accounts"],0)
        self.assertEqual(view["unverified_accounts"],3)

    def test_symlink_cache_fails_closed(self):
        self.cache.parent.mkdir(mode=0o700,parents=True)
        self.cache.symlink_to(self.db)
        with self.assertRaises(InsecureSnapshotUnavailable):
            read_snapshot(self.cache,self.now)


if __name__=="__main__":
    unittest.main()
