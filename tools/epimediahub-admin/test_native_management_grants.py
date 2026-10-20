"""Isolated Flask/SQLite tests for native Admin grant adapters.

Tests never import or call real production business actions, live VPN or
customer databases. Fixture handlers simulate the original audited functions.
"""
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import uuid

from flask import Flask
import mobile_flask

def future():
    return (datetime.now(timezone.utc)+timedelta(days=7)).isoformat()

class NativeGrantTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"provisioning.db"
        with sqlite3.connect(self.db) as con:
            con.executescript("""
                CREATE TABLE devices (id INTEGER PRIMARY KEY,device_id TEXT,enabled INTEGER);
                INSERT INTO devices VALUES (15,'test-device-only',1);
                CREATE TABLE annual_device_licenses (
                    device_id TEXT,granted_at TEXT,expires_at TEXT,revoked_at TEXT
                );
                CREATE TABLE vpn_trial_authorizations (
                    device_row_id INTEGER,granted_at TEXT,expires_at TEXT
                );
            """)
        self.app=Flask("native-grant-qa")
        self.app.secret_key="isolated-test-only-not-production"
        mobile_flask.install(self.app)
        self.client=self.app.test_client()
        self.invoked={"grant-year":0,"vpn-trial7":0}

        def annual(row_id):
            self.invoked["grant-year"]+=1
            with sqlite3.connect(self.db) as con:
                con.execute(
                    "INSERT INTO annual_device_licenses VALUES (?,?,?,NULL)",
                    ("test-device-only",datetime.now(timezone.utc).isoformat(),future())
                )
        def vpn(row_id):
            self.invoked["vpn-trial7"]+=1
            with sqlite3.connect(self.db) as con:
                con.execute(
                    "INSERT INTO vpn_trial_authorizations VALUES (?,?,?)",
                    (row_id,datetime.now(timezone.utc).isoformat(),future())
                )
        self.app.view_functions["admin_grant_year"]=annual
        self.app.view_functions["grant_trial_auto"]=vpn
        self.env=mock.patch.object(mobile_flask,"_base",return_value=Path(self.tmp.name))
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def login(self):
        with self.client.session_transaction() as sess:
            sess["admin"]=True
            sess["_dashboard_csrf"]="isolated-csrf-token-"+"k"*32
        return self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]

    def post(self,action="grant-year",id=15,csrf=None,data=None):
        path=f"/admin/mobile/management/devices/{id}/{action}"
        headers={"X-Dashboard-CSRF":csrf} if csrf else {}
        return self.client.post(path,headers=headers,
            json=data or {"confirm":True,"request_id":str(uuid.uuid4())})

    def test_anonymous_and_csrf_blocked_before_business_action(self):
        self.assertEqual(self.post().status_code,401)
        csrf=self.login()
        self.assertEqual(self.post().status_code,403)
        self.assertEqual(self.post(csrf="bad-token").status_code,403)
        self.assertEqual(sum(self.invoked.values()),0)

    def test_explicit_confirmation_and_strict_payload(self):
        csrf=self.login()
        self.assertEqual(self.post(csrf=csrf,data={"confirm":False}).status_code,400)
        self.assertEqual(self.post(csrf=csrf,data={
            "confirm":True,"request_id":str(uuid.uuid4()),"unknown":"data"
        }).status_code,400)
        self.assertEqual(sum(self.invoked.values()),0)

    def test_app_year_success_replay_returns_already_active(self):
        csrf=self.login()
        first=self.post(csrf=csrf)
        self.assertEqual(first.status_code,200)
        self.assertTrue(first.get_json()["applied"])
        self.assertEqual(first.headers["Cache-Control"],"private, no-store")
        again=self.post(csrf=csrf)
        self.assertEqual(again.status_code,409)
        self.assertEqual(self.invoked["grant-year"],1)

    def test_vpn_trial_success_replay_returns_already_active(self):
        csrf=self.login()
        first=self.post("vpn-trial7",csrf=csrf)
        self.assertEqual(first.status_code,200)
        self.assertTrue(first.get_json()["applied"])
        again=self.post("vpn-trial7",csrf=csrf)
        self.assertEqual(again.status_code,409)
        self.assertEqual(self.invoked["vpn-trial7"],1)

    def test_unavailable_real_handler_never_guess_or_write(self):
        csrf=self.login()
        del self.app.view_functions["grant_trial_auto"]
        response=self.post("vpn-trial7",csrf=csrf)
        self.assertEqual(response.status_code,503)
        self.assertEqual(sum(self.invoked.values()),0)
        self.assertNotIn("test-device-only",response.get_data(as_text=True))

    def test_failed_legacy_handler_redirect_is_not_success(self):
        csrf=self.login()
        self.app.view_functions["admin_grant_year"]=lambda row_id: "redirect"
        self.assertEqual(self.post(csrf=csrf).status_code,409)

    def test_disabled_device_fails_closed(self):
        csrf=self.login()
        with sqlite3.connect(self.db) as con:
            con.execute("UPDATE devices SET enabled=0 WHERE id=15")
        self.assertEqual(self.post(csrf=csrf).status_code,503)
        self.assertEqual(sum(self.invoked.values()),0)

if __name__=="__main__":
    unittest.main()
