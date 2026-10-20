"""Prevent the native-backend inventory from exporting customer data or secrets."""
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest

from audit_native_management_contract import collect, inspect_source


class InventoryTests(unittest.TestCase):
    def test_extracts_route_contract_not_handler_body(self):
        snippet = '''
from flask import Flask
app = Flask(__name__)
@app.route("/admin/customers/<int:customer_id>", methods=["GET"])
def show_customer(customer_id):
    PASSWORD="NEVER_EXPORT_THIS_VALUE"
    return PASSWORD
@app.post("/admin/resellers/<id>/license")
def license_reseller(id):
    return "STILL_NEVER_EXPORT"
'''
        routes = inspect_source(snippet, "web.py")
        self.assertEqual(len(routes), 2)
        raw = str(routes)
        self.assertIn("/admin/customers/<int:customer_id>", raw)
        self.assertNotIn("NEVER_EXPORT", raw)
        self.assertNotIn("PASSWORD", raw)

    def test_reads_only_column_names_not_sensitive_row_values(self):
        with tempfile.TemporaryDirectory() as dirname:
            root = Path(dirname)
            source = root / "backend"
            source.mkdir()
            (source/"admin_routes.py").write_text("""
@app.get("/admin/resellers")
def resellers():
    return "TEST_SECRET_SHOULD_NOT_APPEAR"
""")
            db = root/"db.sqlite"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE customer_accounts (id INTEGER, display_name TEXT, secret_token TEXT)")
                conn.execute(
                    "INSERT INTO customer_accounts VALUES (1, 'PERSONAL_CUSTOMER_VALUE', 'SECRET_VALUE')"
                )
                conn.execute("CREATE TABLE unrelated_internal (raw_credentials TEXT)")
            exported = collect(source, db)
            blob = str(exported)
            self.assertIn("customer_accounts", blob)
            self.assertIn("display_name", blob)
            self.assertNotIn("secret_token", blob)
            self.assertNotIn("PERSONAL_CUSTOMER_VALUE", blob)
            self.assertNotIn("SECRET_VALUE", blob)
            self.assertNotIn("TEST_SECRET_SHOULD_NOT_APPEAR", blob)
            self.assertNotIn("unrelated_internal", blob)


if __name__=="__main__":
    unittest.main()
