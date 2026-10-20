"""Isolated contract tests; never call real provisioning, license or VPN data."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest import mock
import uuid

from flask import Flask, request
import mobile_flask


def rid():
    return str(uuid.uuid4())


class NativeLegacyBridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "provisioning.db"
        with sqlite3.connect(self.db) as con:
            con.executescript("""
                CREATE TABLE customers (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    enabled INTEGER NOT NULL DEFAULT 1, reseller_id INTEGER
                );
                CREATE TABLE resellers (
                    id INTEGER PRIMARY KEY, name TEXT, username TEXT UNIQUE,
                    enabled INTEGER, customer_limit INTEGER, device_limit INTEGER,
                    branding_name TEXT
                );
                CREATE TABLE devices (
                    id INTEGER PRIMARY KEY, customer_id INTEGER,
                    display_name TEXT, config_version INTEGER
                );
                INSERT INTO customers VALUES(1,'Alpha',1,NULL);
                INSERT INTO customers VALUES(2,'Beta',1,NULL);
                INSERT INTO resellers VALUES(3,'Partner','partner',1,20,40,'Brand');
                INSERT INTO devices VALUES(7,1,'Living Room',5);
            """)
        self.app = Flask("native-legacy-isolated")
        self.app.secret_key = "isolated-secret-not-live"
        mobile_flask.install(self.app)
        self.client = self.app.test_client()
        self.env = mock.patch.object(mobile_flask, "_base", return_value=self.root)
        self.env.start()
        self.calls = {}

        def register(name, action):
            def original(**kwargs):
                self.calls[name] = self.calls.get(name, 0) + 1
                with sqlite3.connect(self.db) as con:
                    action(con, **kwargs)
                return "303 redirect from original"
            self.app.view_functions[name] = original

        register("v070_create_customer",
                 lambda con: con.execute("INSERT INTO customers(name) VALUES(?)",
                     (request.form["name"],)))
        register("v080_create_reseller",
                 lambda con: con.execute(
                     """INSERT INTO resellers
                        (name,username,enabled,customer_limit,device_limit,branding_name)
                        VALUES(?,?,1,?,?,?)""",
                     (request.form["name"], request.form["username"],
                      int(request.form["customer_limit"]),
                      int(request.form["device_limit"]), request.form["branding_name"])))
        register("v074_rename_device",
                 lambda con, device_id: con.execute(
                     "UPDATE devices SET display_name=? WHERE id=?",
                     (request.form["name"], device_id)))
        register("v070_sync_device",
                 lambda con, device_id: con.execute(
                     "UPDATE devices SET config_version=config_version+1 WHERE id=?",
                     (device_id,)))
        register("v070_move_device",
                 lambda con, device_id: con.execute(
                     "UPDATE devices SET customer_id=? WHERE id=?",
                     (int(request.form["customer_id"]), device_id)))
        register("v080_assign_customer_reseller",
                 lambda con, customer_id: con.execute(
                     "UPDATE customers SET reseller_id=? WHERE id=?",
                     (int(request.form["reseller_id"]) if request.form["reseller_id"]
                      else None, customer_id)))

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def signin(self):
        with self.client.session_transaction() as session:
            session["admin"] = True
            session["_dashboard_csrf"] = "test-only-csrf-" + "X"*40
        return self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]

    def post(self, action, ident, csrf=None, fields=None):
        data = {"confirm": "true", "request_id": rid()}
        if fields:
            data.update(fields)
        headers = {"X-Dashboard-CSRF": csrf} if csrf else {}
        return self.client.post(
            f"/admin/mobile/management/actions/{action}/{ident}",
            data=data, headers=headers)

    def scalar(self, sql, vals=()):
        with sqlite3.connect(self.db) as con:
            return con.execute(sql, vals).fetchone()[0]

    def test_session_csrf_confirmation_and_field_whitelist(self):
        self.assertEqual(self.post("create-customer", 0, fields={"name":"Gamma"}).status_code,401)
        csrf=self.signin()
        self.assertEqual(self.post("create-customer",0,fields={"name":"Gamma"}).status_code,403)
        bad={"name":"Gamma","confirm":"false"}
        self.assertEqual(self.post("create-customer",0,csrf,bad).status_code,400)
        self.assertEqual(self.post("create-customer",0,csrf,{
            "name":"Gamma", "hijack":"true"}).status_code,400)
        self.assertEqual(self.post("create-customer",0,csrf,{"name":"<script>"}).status_code,400)
        self.assertEqual(self.post("delete-customer",1,csrf).status_code,404)
        self.assertEqual(sum(self.calls.values()),0)

    def test_customer_creation_replay_prevents_duplicates(self):
        csrf=self.signin()
        request_id=rid()
        fields={"name":"Gamma","request_id":request_id}
        first=self.post("create-customer",0,csrf,fields)
        self.assertEqual(first.status_code,200)
        self.assertTrue(first.get_json()["applied"])
        second=self.post("create-customer",0,csrf,fields)
        self.assertEqual(second.status_code,200)
        self.assertTrue(second.get_json()["replayed"])
        self.assertEqual(first.get_json()["id"],second.get_json()["id"])
        self.assertEqual(self.scalar(
            "SELECT COUNT(*) FROM customers WHERE name='Gamma'"),1)
        self.assertEqual(self.calls["v070_create_customer"],1)
        mismatch=self.post("sync-device",7,csrf,{"request_id":request_id})
        self.assertEqual(mismatch.status_code,409)

    def test_reseller_creation_never_reflects_password(self):
        csrf=self.signin()
        payload={"name":"Reseller Neu","username":"händler_1",
            "password":"SECRET_PASSWORD_SENTINEL", "branding_name":"Marke",
            "customer_limit":"12","device_limit":"22"}
        # We deliberately accept ASCII-only account identifiers.
        payload["username"]="partnerneu"
        reply=self.post("create-reseller",0,csrf,payload)
        self.assertEqual(reply.status_code,200)
        self.assertEqual(reply.get_json()["applied"],True)
        self.assertNotIn("SECRET_PASSWORD_SENTINEL",reply.get_data(as_text=True))
        self.assertEqual(self.scalar(
            "SELECT COUNT(*) FROM resellers WHERE username='partnerneu'"),1)

    def test_device_rename_sync_move_and_reseller_assignment(self):
        csrf=self.signin()
        operations=[
            ("rename-device",7,{"name":"TV Lounge"},"v074_rename_device"),
            ("sync-device",7,{},"v070_sync_device"),
            ("move-device",7,{"customer_id":"2"},"v070_move_device"),
            ("assign-reseller",2,{"reseller_id":"3"},"v080_assign_customer_reseller")
        ]
        for action,ident,values,legacy in operations:
            with self.subTest(action=action):
                resp=self.post(action,ident,csrf,values)
                self.assertEqual(resp.status_code,200,resp.get_data(as_text=True))
                self.assertEqual(self.calls[legacy],1)
        self.assertEqual(self.scalar("SELECT display_name FROM devices WHERE id=7"),"TV Lounge")
        self.assertEqual(self.scalar("SELECT config_version FROM devices WHERE id=7"),6)
        self.assertEqual(self.scalar("SELECT customer_id FROM devices WHERE id=7"),2)
        self.assertEqual(self.scalar("SELECT reseller_id FROM customers WHERE id=2"),3)
        self.assertEqual(self.post("move-device",7,csrf,{"customer_id":"777"}).status_code,400)

    def test_crash_after_write_fails_closed_on_retry(self):
        csrf=self.signin()
        def write_then_crash():
            with sqlite3.connect(self.db) as con:
                con.execute("INSERT INTO customers(name) VALUES('Crash Yet Written')")
            raise RuntimeError("failure AFTER commit")
        self.app.view_functions["v070_create_customer"]=write_then_crash
        payload={"name":"Crash Yet Written","request_id":rid()}
        self.app.config["TESTING"]=False
        first=self.post("create-customer",0,csrf,payload)
        self.assertEqual(first.status_code,500)
        second=self.post("create-customer",0,csrf,payload)
        self.assertEqual(second.status_code,409)
        self.assertEqual(self.scalar(
            "SELECT COUNT(*) FROM customers WHERE name='Crash Yet Written'"),1)

    def test_original_redirect_is_not_success(self):
        csrf=self.signin()
        self.app.view_functions["v070_sync_device"]=lambda device_id: "redirect"
        reply=self.post("sync-device",7,csrf)
        self.assertEqual(reply.status_code,409)
        self.assertFalse(reply.get_json()["applied"])


if __name__ == "__main__":
    unittest.main()
