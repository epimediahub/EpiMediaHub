"""Strict tests of native Admin rename behavior with only artificial data."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest import mock
from flask import Flask

import mobile_flask


class NativeRenameTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)
        self.db=self.path/"provisioning.db"
        with sqlite3.connect(self.db) as con:
            con.executescript("""
                CREATE TABLE customers (
                  id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,reseller_id INTEGER
                );
                CREATE TABLE resellers (
                  id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,
                  branding_name TEXT,customer_limit INTEGER,device_limit INTEGER
                );
                CREATE TABLE customer_playlists (
                  id INTEGER PRIMARY KEY,customer_id INTEGER,name TEXT,
                  config_json TEXT, enabled INTEGER
                );
                CREATE TABLE devices (
                  id INTEGER PRIMARY KEY,customer_id INTEGER,display_name TEXT,
                  device_id TEXT,platform TEXT,enabled INTEGER
                );
                INSERT INTO customers VALUES(1,'Kunde Alt',1,3);
                INSERT INTO resellers VALUES(3,'Partner Alt',1,'Brand',10,20);
                INSERT INTO customer_playlists
                  VALUES(10,1,'Stream','SECRET_STREAM_PASSWORD',1);
                INSERT INTO devices
                  VALUES(20,1,'Device','PRIVATE_DEVICE_TOKEN','android',1);
            """)
        self.app=Flask("native-rename-unit")
        self.app.secret_key="not-production-isolated-qa"
        mobile_flask.install(self.app)
        self.client=self.app.test_client()
        self.guard=mock.patch.object(mobile_flask,"_base",return_value=self.path)
        self.guard.start()

    def tearDown(self):
        self.guard.stop()
        self.tmp.cleanup()

    def login(self):
        with self.client.session_transaction() as sess:
            sess["admin"]=True
            sess["_dashboard_csrf"]="test-csrf-"+"q"*36
        return self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]

    def request(self,kind="customers",entity=1,csrf=None,data=None):
        headers={"X-Dashboard-CSRF":csrf} if csrf else {}
        if data is None:
            data={"expected_name":"Kunde Alt","name":"Kunde Neu",
                  "request_id":str(uuid.uuid4())}
        return self.client.post(
            f"/admin/mobile/management/{kind}/{entity}/rename",
            json=data,headers=headers)

    def test_authenticated_csrf_guard(self):
        payload=self.request()
        self.assertEqual(payload.status_code,401)
        self.login()
        self.assertEqual(self.request().status_code,403)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT name FROM customers").fetchone()[0],"Kunde Alt")

    def test_safe_single_rename_and_replay(self):
        csrf=self.login()
        cmd={"expected_name":"Kunde Alt","name":"Kunde Neu",
             "request_id":str(uuid.uuid4())}
        first=self.request(csrf=csrf,data=cmd)
        self.assertEqual(first.status_code,200)
        self.assertTrue(first.get_json()["applied"])
        duplicate=self.request(csrf=csrf,data=cmd)
        self.assertEqual(duplicate.status_code,200)
        self.assertTrue(duplicate.get_json()["replayed"])
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT name FROM customers").fetchone()[0],"Kunde Neu")
            self.assertEqual(con.execute(
                "SELECT COUNT(*) FROM native_admin_edit_events").fetchone()[0],1)
            self.assertEqual(con.execute(
                "SELECT config_json FROM customer_playlists").fetchone()[0],
                "SECRET_STREAM_PASSWORD")
        self.assertNotIn("SECRET_STREAM_PASSWORD",first.get_data(as_text=True))

    def test_conflict_and_id_cannot_override(self):
        csrf=self.login()
        stale=self.request(csrf=csrf,data={"expected_name":"Falsch","name":"Kunde Neu",
                                          "request_id":str(uuid.uuid4())})
        self.assertEqual(stale.status_code,409)
        invalid=self.request(csrf=csrf,data={"expected_name":"Kunde Alt",
                 "name":"Kunde Neu","request_id":"not-a-uuid"})
        self.assertEqual(invalid.status_code,400)
        code=self.request(csrf=csrf,data={"expected_name":"Kunde Alt",
                                          "name":"<script>alert(1)</script>",
                                          "request_id":str(uuid.uuid4())})
        self.assertEqual(code.status_code,400)

    def test_reseller_rename_does_not_touch_credits(self):
        csrf=self.login()
        response=self.request("resellers",3,csrf,
            {"expected_name":"Partner Alt","name":"Partner Neu",
             "request_id":str(uuid.uuid4())})
        self.assertEqual(response.status_code,200)
        with sqlite3.connect(self.db) as con:
            row=con.execute("SELECT name,branding_name,customer_limit FROM resellers").fetchone()
            self.assertEqual(row,("Partner Neu","Brand",10))
            self.assertEqual(con.execute("SELECT reseller_id FROM customers").fetchone()[0],3)


if __name__=="__main__":
    unittest.main()
