"""No-production-data tests for native Android Admin management contract."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
from flask import Flask
import native_management_data as api
import mobile_flask


SCHEMA="""
CREATE TABLE customers (id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,reseller_id INTEGER);
CREATE TABLE devices (id INTEGER PRIMARY KEY,customer_id INTEGER,enabled INTEGER,
    display_name TEXT,platform TEXT,device_id TEXT);
CREATE TABLE customer_playlists (id INTEGER PRIMARY KEY,customer_id INTEGER,name TEXT,
    enabled INTEGER,config_json TEXT);
CREATE TABLE resellers (id INTEGER PRIMARY KEY,name TEXT,enabled INTEGER,
    customer_limit INTEGER,device_limit INTEGER,branding_name TEXT);
"""
PRIVATE="https://example.invalid/provider?username=PRIVATE_USER&password=PRIVATE_PASSWORD"


class NativeManagementTests(unittest.TestCase):
    def setUp(self):
        self.root=tempfile.TemporaryDirectory()
        self.db=Path(self.root.name)/"provisioning.db"
        with sqlite3.connect(self.db) as con:
            con.executescript(SCHEMA)
            con.execute("INSERT INTO customers VALUES (1,'Kunde 1',1,3)")
            con.execute("INSERT INTO customers VALUES (2,'Kunde 2',0,NULL)")
            con.execute("INSERT INTO devices VALUES (7,1,1,'Living Room','firetv','PRIVATE_MAC')")
            con.execute("INSERT INTO customer_playlists VALUES (10,1,'4K Test',1,?)",(PRIVATE,))
            con.execute("INSERT INTO resellers VALUES (3,'Partner 3',1,20,40,'Private Label')")
        self.app=Flask("test-native-management")
        self.app.secret_key="test-only-development-secret"
        self.app.config.update(TESTING=True)
        mobile_flask.install(self.app)
        self.client=self.app.test_client()

    def tearDown(self):
        self.root.cleanup()

    def signin(self):
        with self.client.session_transaction() as s:
            s["admin"]=True

    def test_anonymous_forbidden_all_endpoints(self):
        urls=(
            "/admin/mobile/management/overview",
            "/admin/mobile/management/customers",
            "/admin/mobile/management/resellers",
            "/admin/mobile/management/customers/1",
            "/admin/mobile/management/resellers/3",
        )
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code,401)

    def test_read_api_respects_verified_schema_and_no_config_leak(self):
        self.signin()
        from unittest import mock
        with mock.patch.object(mobile_flask, "_base", return_value=Path(self.root.name)):
            overview=self.client.get("/admin/mobile/management/overview")
            self.assertEqual(overview.status_code,200)
            self.assertEqual(overview.get_json()["customers"],2)
            self.assertEqual(overview.get_json()["resellers"],1)
            self.assertIsNone(overview.get_json()["active_vpns"])
            self.assertIsNone(overview.get_json()["active_licenses"])
            customers=self.client.get("/admin/mobile/management/customers")
            self.assertEqual(customers.get_json()["customers"][0]["id"],"2")
            self.assertEqual(customers.get_json()["customers"][1]["playlist_count"],1)
            resellers=self.client.get("/admin/mobile/management/resellers")
            self.assertEqual(len(resellers.get_json()["resellers"]),1)
            detail=self.client.get("/admin/mobile/management/customers/1")
            self.assertEqual(detail.get_json()["devices"][0]["name"],"Living Room")
            self.assertEqual(detail.get_json()["playlists"][0]["name"],"4K Test")
            reseller_detail=self.client.get("/admin/mobile/management/resellers/3")
            self.assertEqual(len(reseller_detail.get_json()["customers"]),1)
            self.assertEqual(self.client.get("/admin/mobile/management/customers/999").status_code,404)
            for r in (overview,customers,resellers,detail,reseller_detail):
                self.assertEqual(r.headers["Cache-Control"],"private, no-store")
                self.assertNotIn("PRIVATE_USER",r.get_data(as_text=True))
                self.assertNotIn("PRIVATE_PASSWORD",r.get_data(as_text=True))
                self.assertNotIn("PRIVATE_MAC",r.get_data(as_text=True))

    def test_search_all_entries_and_escape_sql_wildcards(self):
        self.signin()
        with sqlite3.connect(self.db) as con:
            con.execute("INSERT INTO customers VALUES (9,'A%_ Zeichen',1,null)")
            con.execute("INSERT INTO customers VALUES (10,'Anderer Kunde',1,null)")
        from unittest import mock
        with mock.patch.object(mobile_flask, "_base", return_value=Path(self.root.name)):
            route="/admin/mobile/management/customers"
            found=self.client.get(route,query_string={"q":"A%_"})
            self.assertEqual(found.status_code,200)
            self.assertEqual([x["id"] for x in found.get_json()["customers"]],["9"])
            another=self.client.get(route,query_string={"q":"Anderer"})
            self.assertEqual(another.get_json()["customers"][0]["name"],"Anderer Kunde")
            too_long=self.client.get(route,query_string={"q":"x"*81})
            self.assertEqual(too_long.status_code,400)
            reseller=self.client.get("/admin/mobile/management/resellers",
                query_string={"q":"Partner"})
            self.assertEqual(len(reseller.get_json()["resellers"]),1)

    def test_device_diagnostics_hide_private_identifiers(self):
        with sqlite3.connect(self.db) as con:
            for name,kind in (
                ("last_seen_at","TEXT"),("last_sync_at","TEXT"),
                ("last_sync_status","TEXT"),("config_version","INTEGER"),
                ("applied_config_version","INTEGER")):
                con.execute(f"ALTER TABLE devices ADD COLUMN {name} {kind}")
            con.execute("""
                UPDATE devices SET last_seen_at='2026-10-20T10:00:00Z',
                    last_sync_status='success',config_version=7,
                    applied_config_version=6 WHERE id=7
            """)
            con.execute("""CREATE TABLE device_error_events
                (id INTEGER, device_row_id INTEGER, component TEXT,code TEXT,
                 app_version TEXT,reported_at TEXT)""")
            con.execute("""INSERT INTO device_error_events VALUES
                (1,7,'player','E500','1.0.3','2026-10-20T10:00:00Z')""")
        endpoint="/admin/mobile/management/devices/7/diagnostics"
        self.assertEqual(self.client.get(endpoint).status_code,401)
        self.signin()
        from unittest import mock
        with mock.patch.object(mobile_flask,"_base",return_value=Path(self.root.name)):
            r=self.client.get(endpoint)
            self.assertEqual(r.status_code,200)
            body=r.get_json()
            self.assertEqual(body["config_version"],7)
            self.assertEqual(body["applied_config_version"],6)
            self.assertEqual(body["last_sync_status"],"success")
            self.assertEqual(body["recent_errors"][0]["code"],"E500")
            self.assertNotIn("PRIVATE_MAC",r.get_data(as_text=True))
            self.assertEqual(self.client.get(
                "/admin/mobile/management/devices/777/diagnostics").status_code,404)

    def test_schema_mismatch_fails_closed(self):
        self.signin()
        with tempfile.TemporaryDirectory() as other:
            with sqlite3.connect(Path(other)/"provisioning.db") as con:
                con.execute("CREATE TABLE customers (id INTEGER)")
            from unittest import mock
            with mock.patch.object(mobile_flask,"_base",return_value=Path(other)):
                r=self.client.get("/admin/mobile/management/customers")
            self.assertEqual(r.status_code,503)
            self.assertNotIn("sqlite",r.get_data(as_text=True).lower())

    def test_lists_bounded_and_report_more(self):
        with sqlite3.connect(self.db) as con:
            con.executemany("INSERT INTO customers VALUES (?, ?, 1, null)",
                [(i,"Kunde "+str(i)) for i in range(1000,1120)])
        value=api.customers(self.db)
        self.assertEqual(len(value["customers"]),100)
        self.assertTrue(value["has_more"])
        self.assertEqual(value["next_before_id"],"1020")
        second=api.customers(self.db,before_id=int(value["next_before_id"]))
        self.assertEqual(len(second["customers"]),22)
        self.assertFalse(second["has_more"])
        self.assertIsNone(second["next_before_id"])
        self.assertEqual(len({x["id"] for x in value["customers"]+second["customers"]}),122)
        self.assertEqual(api.overview(self.db)["customers"],122)

    def test_cursor_validation_and_reseller_pages(self):
        with sqlite3.connect(self.db) as con:
            con.executemany(
                "INSERT INTO resellers VALUES (?,?,1,20,40,'Brand')",
                [(i,"Partner "+str(i)) for i in range(10,121)])
        first=api.resellers(self.db)
        self.assertEqual(len(first["resellers"]),100)
        second=api.resellers(self.db,before_id=int(first["next_before_id"]))
        self.assertEqual(len(second["resellers"]),12)
        self.assertEqual(len({x["id"] for x in first["resellers"]+second["resellers"]}),112)
        for invalid in (-1,0,2**63,True,"18"):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    api.customers(self.db,before_id=invalid)
        self.signin()
        from unittest import mock
        with mock.patch.object(mobile_flask,"_base",return_value=Path(self.root.name)):
            for raw in ("bad","-1","0","9"*30,""):
                self.assertEqual(self.client.get("/admin/mobile/management/resellers",
                    query_string={"before_id":raw}).status_code,400)
            paged=self.client.get("/admin/mobile/management/resellers",
                query_string={"before_id":first["next_before_id"]})
            self.assertEqual(paged.status_code,200)
            self.assertEqual(len(paged.get_json()["resellers"]),12)


if __name__=="__main__":
    unittest.main()
