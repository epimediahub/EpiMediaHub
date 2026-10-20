"""Synthetic original Flask delete handlers: no production customer data."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
import uuid
from unittest import mock

from flask import Flask, request, abort
import mobile_flask
from native_delete_confirmation import expected_confirmation,ConfirmationUnavailable


class NativeDeletionContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.db=self.root/"provisioning.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript("""
                CREATE TABLE customers(id INTEGER PRIMARY KEY,name TEXT,reseller_id INTEGER);
                CREATE TABLE resellers(id INTEGER PRIMARY KEY,name TEXT);
                CREATE TABLE devices(id INTEGER PRIMARY KEY,customer_id INTEGER);
                INSERT INTO resellers VALUES(9,'Synthetic Partner');
                INSERT INTO customers VALUES(7,'Synthetic Client',9);
                INSERT INTO devices VALUES(3,7);
            """)
        self.app=Flask("native-delete-synthetic")
        self.app.secret_key="test-only"
        mobile_flask.install(self.app)
        self.client=self.app.test_client()
        self.patch_base=mock.patch.object(mobile_flask,"_base",return_value=self.root)
        self.patch_base.start()
        self.env=mock.patch.dict(os.environ,{
            "EPIMEDIAHUB_NATIVE_ADMIN_ENABLE_DELETES":"YES"})
        self.env.start()
        db_path=self.db

        def v074_delete_device(device_id):
            if request.form.get("confirm","") != f"Gerät {device_id} löschen":
                abort(400)
            with sqlite3.connect(db_path) as conn:
                conn.execute("DELETE FROM devices WHERE id=?",(device_id,))
            return "redirect"

        def v073_delete_customer(customer_id):
            if request.form.get("confirm","") != f"KUNDE {customer_id} LÖSCHEN":
                abort(400)
            with sqlite3.connect(db_path) as conn:
                conn.execute("DELETE FROM devices WHERE customer_id=?",(customer_id,))
                conn.execute("DELETE FROM customers WHERE id=?",(customer_id,))
            return "redirect"

        def v080_delete_reseller(reseller_id):
            if request.form.get("confirm","") != f"RESELLER {reseller_id} LÖSCHEN":
                abort(400)
            with sqlite3.connect(db_path) as conn:
                conn.execute("UPDATE customers SET reseller_id=NULL WHERE reseller_id=?",
                             (reseller_id,))
                conn.execute("DELETE FROM resellers WHERE id=?",(reseller_id,))
            return "redirect"

        for h in (v074_delete_device,v073_delete_customer,v080_delete_reseller):
            self.app.view_functions[h.__name__]=h

    def tearDown(self):
        self.env.stop()
        self.patch_base.stop()
        self.tmp.cleanup()

    def signin(self):
        with self.client.session_transaction() as sess:
            sess["admin"]=True
            sess["_dashboard_csrf"]="test-only-"+("X"*40)
        return self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]

    def post(self,kind,ident,phrase,csrf):
        return self.client.post(
            f"/admin/mobile/management/actions/{kind}/{ident}",
            data={"request_id":str(uuid.uuid4()),"confirm":phrase},
            headers={"X-Dashboard-CSRF":csrf}
        )

    def test_original_required_phrase_not_guessed_or_bypassed(self):
        self.assertEqual(self.client.get(
            "/admin/mobile/management/delete-confirm/delete-customer/7"
        ).status_code,401)
        csrf=self.signin()
        expected={
            "delete-device":(3,"Gerät 3 löschen"),
            "delete-customer":(7,"KUNDE 7 LÖSCHEN"),
            "delete-reseller":(9,"RESELLER 9 LÖSCHEN")
        }
        with self.app.app_context():
            for kind,(ident,phrase) in expected.items():
                self.assertEqual(expected_confirmation(kind,ident),phrase)
        for kind,(ident,phrase) in expected.items():
            self.assertEqual(self.client.get(
                f"/admin/mobile/management/delete-confirm/{kind}/{ident}"
            ).get_json()["required_confirmation"],phrase)
            self.assertEqual(self.post(kind,ident,"true",csrf).status_code,400)
            self.assertEqual(self.post(kind,ident,phrase+"!",csrf).status_code,400)
        self.assertEqual(self.post("delete-device",3,"Gerät 3 löschen",csrf).status_code,200)
        self.assertEqual(self.post("delete-customer",7,"KUNDE 7 LÖSCHEN",csrf).status_code,200)
        self.assertEqual(self.post("delete-reseller",9,"RESELLER 9 LÖSCHEN",csrf).status_code,200)
        with sqlite3.connect(self.db) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM devices").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM customers").fetchone()[0],0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM resellers").fetchone()[0],0)

    def test_feature_gate_must_be_explicit_even_for_authenticated_admin(self):
        csrf=self.signin()
        with mock.patch.dict(os.environ,{"EPIMEDIAHUB_NATIVE_ADMIN_ENABLE_DELETES":"NO"}):
            self.assertEqual(self.client.get(
                "/admin/mobile/management/delete-confirm/delete-device/3"
            ).status_code,503)
            self.assertEqual(self.post(
                "delete-device",3,"Gerät 3 löschen",csrf).status_code,503)

    def test_unverified_confirmation_expressions_are_rejected(self):
        def v074_delete_device(device_id):
            expected=f"REMOVE {device_id}" + os.environ.get("BAD_DYNAMIC","")
            if request.form.get("confirm")!=expected:
                abort(400)
            return "redirect"
        self.app.view_functions["v074_delete_device"]=v074_delete_device
        self.signin()
        with self.app.app_context():
            with self.assertRaises(ConfirmationUnavailable):
                expected_confirmation("delete-device",3)


if __name__=="__main__":
    unittest.main()
