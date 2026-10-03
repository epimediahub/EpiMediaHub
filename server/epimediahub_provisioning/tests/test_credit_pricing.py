"""Exercise the real pricing/order routes against disposable SQLite databases."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import shutil
from concurrent.futures import ThreadPoolExecutor
from werkzeug.security import generate_password_hash
import unittest
from datetime import datetime, timedelta


class CreditPricingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bootstrap = tempfile.TemporaryDirectory(prefix="emh-credit-tests-")
        cls.previous_data_dir = os.environ.get("EPIMEDIAHUB_DATA_DIR")
        os.environ["EPIMEDIAHUB_DATA_DIR"] = cls.bootstrap.name
        sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
        cls.core = importlib.import_module("app")
        importlib.import_module("wsgi")
        cls.licensing = importlib.import_module("license_api")
        cls.core.app.config.update(TESTING=True)

    @classmethod
    def tearDownClass(cls):
        cls.bootstrap.cleanup()
        if cls.previous_data_dir is None:
            os.environ.pop("EPIMEDIAHUB_DATA_DIR", None)
        else:
            os.environ["EPIMEDIAHUB_DATA_DIR"] = cls.previous_data_dir

    def setUp(self):
        self.data = tempfile.TemporaryDirectory(prefix="emh-price-case-")
        self.addCleanup(self.data.cleanup)
        self.core.BASE_DIR = Path(self.data.name)
        self.core.DB_PATH = self.core.BASE_DIR / "provisioning.db"
        shutil.copy2(Path(self.bootstrap.name) / "provisioning.db", self.core.DB_PATH)
        self.admin = self.core.app.test_client()
        with self.admin.session_transaction() as session:
            session["admin"] = True
        self.reseller_id = self.make_reseller("First reseller")
        self.reseller = self.client_for(self.reseller_id)

    def make_reseller(self, name, price=None):
        with self.core.db() as con:
            return con.execute(
                "INSERT INTO resellers(name,username,password_hash,enabled,created_at,updated_at,credit_price_cents) "
                "VALUES(?,?,?,1,?,?,?)",
                (name, name.lower().replace(" ", "-"), generate_password_hash("ExistingPass-123"), self.core.iso(self.core.utcnow()), self.core.iso(self.core.utcnow()), price),
            ).lastrowid

    def client_for(self, reseller_id):
        client = self.core.app.test_client()
        with client.session_transaction() as session:
            session["reseller_id"] = reseller_id
        return client

    def row(self, sql, params=()):
        with self.core.db() as con:
            return con.execute(sql, params).fetchone()

    def set_price(self, value, reseller_id=None):
        return self.admin.post(
            f"/admin/resellers/{reseller_id or self.reseller_id}/price",
            data={"credit_price_eur": value},
        )

    def order(self, price, credits=10, client=None, **extra):
        return (client or self.reseller).post(
            "/reseller/credit-orders",
            data={"credits": credits, "unit_price_cents": price, **extra},
        )

    def test_new_reseller_has_no_default_price(self):
        response = self.admin.post("/admin/v080/resellers", data={
            "name": "New", "username": "new", "password": "test-password",
        })
        self.assertEqual(302, response.status_code)
        self.assertIsNone(self.row("SELECT credit_price_cents FROM resellers WHERE username='new'")[0])

    def test_admin_can_set_price_for_an_existing_account(self):
        self.admin.post("/admin/v080/resellers", data={
            "name": "New", "username": "new", "password": "test-password", "credit_price_eur": "3,47",
        })
        rid = self.row("SELECT id FROM resellers WHERE username='new'")[0]
        self.set_price("3,47", rid)
        self.assertEqual(347, self.row("SELECT credit_price_cents FROM resellers WHERE username='new'")[0])

    def test_unset_price_disables_orders_in_ui_and_server(self):
        page = self.reseller.get("/reseller/credits").get_data(as_text=True)
        self.assertIn("Preis noch offen", page)
        self.assertIn('disabled>Bestellen', page)
        self.assertNotIn("5,00 €", page)
        self.assertIn("credit_price_missing", self.order(500).location)
        self.assertEqual(0, self.row("SELECT COUNT(*) FROM credit_orders")[0])

    def test_each_reseller_gets_own_price_and_exact_package_total(self):
        second_id = self.make_reseller("Second reseller", 689)
        self.set_price("4,37")
        for credits in (10, 25, 50, 100):
            self.assertIn("credit_order_created", self.order(437, credits).location)
            self.assertEqual(credits * 437, self.row("SELECT amount_cents FROM credit_orders ORDER BY id DESC LIMIT 1")[0])
        self.order(689, client=self.client_for(second_id))
        self.assertEqual(6890, self.row("SELECT amount_cents FROM credit_orders WHERE reseller_id=?", (second_id,))[0])
        page = self.reseller.get("/reseller/credits").get_data(as_text=True)
        self.assertIn("4,37 € pro Credit", page)
        self.assertIn("109,25 €", page)
        self.assertNotIn("6,89 €", page)
        self.assertNotIn("Guthabenwert", page)

    def test_client_cannot_replace_the_calculated_amount_or_reseller(self):
        other_id = self.make_reseller("Other reseller", 1)
        self.set_price("4.37")
        self.order(437, amount_cents="1", reseller_id=str(other_id))
        row = self.row("SELECT amount_cents,reseller_id FROM credit_orders")
        self.assertEqual((4370, self.reseller_id), tuple(row))

    def test_stale_or_missing_quote_is_rejected(self):
        self.set_price("4.37")
        for price in (500, "", "invalid"):
            self.assertIn("credit_price_changed", self.order(price).location)
        self.assertEqual(0, self.row("SELECT COUNT(*) FROM credit_orders")[0])

    def test_price_change_preserves_orders_and_payment_credits_only_once(self):
        self.set_price("4.37")
        self.order(437, 25)
        order_id = self.row("SELECT id FROM credit_orders")[0]
        self.set_price("6.89")
        self.assertEqual(10925, self.row("SELECT amount_cents FROM credit_orders WHERE id=?", (order_id,))[0])
        self.admin.post(f"/admin/credit-orders/{order_id}/approve")
        self.admin.post(f"/admin/credit-orders/{order_id}/approve")
        self.assertEqual(25, self.row("SELECT SUM(amount) FROM credit_transactions WHERE reseller_id=?", (self.reseller_id,))[0])
        self.assertEqual(1, self.row("SELECT COUNT(*) FROM credit_transactions WHERE kind='purchase'")[0])
        self.assertEqual(10925, self.row("SELECT amount_cents FROM credit_orders WHERE id=?", (order_id,))[0])

    def test_clearing_price_stops_new_orders_but_preserves_existing_order(self):
        self.set_price("4.37")
        self.order(437)
        self.set_price("")
        self.assertIn("credit_price_missing", self.order(437).location)
        self.assertEqual(1, self.row("SELECT COUNT(*) FROM credit_orders")[0])
        self.assertEqual(4370, self.row("SELECT amount_cents FROM credit_orders")[0])

    def test_zero_price_is_an_explicit_admin_choice(self):
        self.set_price("0,00")
        self.assertIn("credit_order_created", self.order(0).location)
        self.assertEqual(0, self.row("SELECT amount_cents FROM credit_orders")[0])
        self.assertIn("0,00 € pro Credit", self.reseller.get("/reseller/credits").get_data(as_text=True))

    def test_invalid_prices_leave_saved_price_unchanged(self):
        self.set_price("4.37")
        for invalid in ("-1", "1.234", "nan", "inf", "1e3", "1,2,3", "1000000", "abc"):
            with self.subTest(price=invalid):
                self.assertIn("credit_price_invalid", self.set_price(invalid).location)
                self.assertEqual(437, self.row("SELECT credit_price_cents FROM resellers WHERE id=?", (self.reseller_id,))[0])

    def test_only_admin_can_change_prices(self):
        url = f"/admin/resellers/{self.reseller_id}/price"
        for client in (self.core.app.test_client(), self.reseller):
            response = client.post(url, data={"credit_price_eur": "0"})
            self.assertIn("/admin/login", response.location)
        self.assertIsNone(self.row("SELECT credit_price_cents FROM resellers WHERE id=?", (self.reseller_id,))[0])

    def test_retail_price_is_ten_euros_and_not_changed_by_reseller_prices(self):
        self.set_price("3.47")
        self.assertEqual(1000, self.licensing.RETAIL_LICENSE_PRICE_EUR_CENTS)
        self.assertEqual(347, self.row("SELECT credit_price_cents FROM resellers WHERE id=1")[0])
        for client, url in ((self.admin, "/admin/credits"), (self.reseller, "/reseller/credits")):
            response = client.get(url)
            self.assertEqual(200, response.status_code)
            self.assertIn("10,00 € einmalig pro Gerät", response.get_data(as_text=True))

    def test_migration_preserves_orders_and_credits_without_assuming_five_euros(self):
        now = self.core.iso(self.core.utcnow())
        with self.core.db() as con:
            con.execute("ALTER TABLE resellers DROP COLUMN credit_price_cents")
            con.execute("INSERT INTO credit_orders(reseller_id,credits,amount_cents,created_at) VALUES(?,10,5000,?)", (self.reseller_id, now))
            con.execute("INSERT INTO credit_transactions(reseller_id,amount,kind,created_at) VALUES(?,9,'admin_adjustment',?)", (self.reseller_id, now))
        self.licensing.ensure_license_schema()
        self.assertIsNone(self.row("SELECT credit_price_cents FROM resellers WHERE id=?", (self.reseller_id,))[0])
        self.assertEqual(5000, self.row("SELECT amount_cents FROM credit_orders")[0])
        self.assertEqual(9, self.row("SELECT SUM(amount) FROM credit_transactions")[0])
        self.set_price("4.37")
        self.licensing.ensure_license_schema()
        self.assertEqual(437, self.row("SELECT credit_price_cents FROM resellers WHERE id=?", (self.reseller_id,))[0])

    def test_trial_is_seven_days_and_lifetime_always_costs_one_credit(self):
        response = self.reseller.post("/v1/license/status", json={"device_id": "test-device", "trial_key": "a" * 64})
        payload = response.get_json()
        self.assertEqual("TRIAL_ACTIVE", payload["status"])
        self.assertEqual(timedelta(days=7), datetime.fromisoformat(payload["trial_expires_at"].replace("Z", "+00:00")) - datetime.fromisoformat(payload["trial_started_at"].replace("Z", "+00:00")))
        now = self.core.iso(self.core.utcnow())
        with self.core.db() as con:
            customer = con.execute("INSERT INTO customers(name,created_at,reseller_id) VALUES('Customer',?,?)", (now, self.reseller_id)).lastrowid
            device = con.execute("INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at) VALUES(?,'test-device','android','test-session',?)", (customer, now)).lastrowid
            con.execute("INSERT INTO credit_transactions(reseller_id,amount,kind,created_at) VALUES(?,2,'admin_adjustment',?)", (self.reseller_id, now))
        # No new purchase price is required to spend already owned credits.
        self.assertIn("activated", self.reseller.post(f"/reseller/devices/{device}/activate-lifetime").location)
        self.set_price("17.39")
        self.assertIn("already_active", self.reseller.post(f"/reseller/devices/{device}/activate-lifetime").location)
        self.assertEqual(1, self.row("SELECT SUM(amount) FROM credit_transactions WHERE reseller_id=?", (self.reseller_id,))[0])
        self.assertEqual(1, self.row("SELECT COUNT(*) FROM credit_transactions WHERE kind='activation'")[0])
        self.assertEqual("LIFETIME_ACTIVE", self.reseller.post("/v1/license/status", json={"device_id": "test-device", "trial_key": "a" * 64}).get_json()["status"])


    def make_device(self, device_id, reseller_id=None):
        now = self.core.iso(self.core.utcnow())
        with self.core.db() as con:
            cid = con.execute("INSERT INTO customers(name,created_at,reseller_id) VALUES(?,?,?)", (device_id, now, reseller_id)).lastrowid
            return con.execute("INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at) VALUES(?,?,'android',?,?)", (cid, device_id, device_id + "-session", now)).lastrowid

    def status(self, device_id):
        return self.core.app.test_client().post("/v1/license/status", json={"device_id": device_id, "trial_key": self.core.digest(device_id)})

    def test_legacy_account_ids_passwords_limits_and_customer_ownership_survive(self):
        device = self.make_device("legacy-tv", self.reseller_id)
        with self.core.db() as con:
            con.execute("UPDATE resellers SET customer_limit=1,device_limit=3,branding_name='Existing brand'")
            con.execute("ALTER TABLE resellers DROP COLUMN credit_price_cents")
            con.execute("DELETE FROM license_meta WHERE key='grandfathered_existing_devices_v1'")
            before = {t:[tuple(r) for r in con.execute("SELECT * FROM " + t)] for t in ("resellers","customers","devices","customer_playlists")}
        self.licensing.ensure_license_schema()
        self.licensing.ensure_license_schema()
        with self.core.db() as con:
            for table, rows in before.items():
                after = [tuple(r) for r in con.execute("SELECT * FROM " + table)]
                if table == "resellers": after = [r[:-1] for r in after]
                self.assertEqual(rows, after, table)
        login = self.core.app.test_client()
        response = login.post("/reseller/login", data={"username":"first-reseller", "password":"ExistingPass-123"})
        self.assertEqual("/reseller", response.location)
        self.assertEqual(200, login.get("/reseller").status_code)
        login.post("/reseller/customers", data={"name":"Over the existing limit"})
        self.assertEqual(0, self.row("SELECT COUNT(*) FROM customers WHERE name='Over the existing limit'")[0])
        self.assertEqual("LIFETIME_ACTIVE", self.status("legacy-tv").json["status"])
        self.assertEqual("grandfathered", self.row("SELECT source FROM lifetime_licenses")[0])
        self.assertEqual(0, self.row("SELECT COUNT(*) FROM credit_transactions")[0])
        self.make_device("new-after-migration", self.reseller_id)
        self.licensing.ensure_license_schema()
        self.assertEqual("TRIAL_ACTIVE", self.status("new-after-migration").json["status"])

    def test_direct_consumer_requires_ten_euro_payment_and_uses_no_reseller(self):
        device = self.make_device("direct-tv")
        self.status("direct-tv")
        response = self.admin.post(f"/admin/devices/{device}/activate-lifetime")
        self.assertIn("retail_payment_required", response.location)
        self.assertEqual(0, self.row("SELECT COUNT(*) FROM lifetime_licenses")[0])
        for _ in range(2):
            response = self.admin.post(f"/admin/devices/{device}/activate-lifetime",data={"retail_payment_confirmed":"yes"})
            self.assertEqual(302,response.status_code)
        self.assertEqual("LIFETIME_ACTIVE", self.status("direct-tv").json["status"])
        self.assertIsNone(self.row("SELECT reseller_id FROM lifetime_licenses")[0])
        self.assertEqual(0, self.row("SELECT COUNT(*) FROM credit_transactions")[0])
        audit = self.row("SELECT detail_json FROM audit_log WHERE action='retail_payment_confirmed'")
        self.assertIn('"amount_eur_cents":1000',audit[0])
        self.assertEqual(1,self.row("SELECT COUNT(*) FROM audit_log WHERE action='retail_payment_confirmed'")[0])
        self.assertEqual(1,self.row("SELECT COUNT(*) FROM resellers")[0])

    def test_one_credit_cannot_be_spent_twice_concurrently(self):
        ids = [self.make_device(f"concurrent-{n}",self.reseller_id) for n in range(2)]
        for n in range(2):self.status(f"concurrent-{n}")
        self.admin.post(f"/admin/resellers/{self.reseller_id}/credits",data={"amount":"1"})
        def activate(device):
            return self.client_for(self.reseller_id).post(f"/reseller/devices/{device}/activate-lifetime").location
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(activate,ids))
        self.assertEqual(1,sum("notice=activated" in r for r in results))
        self.assertEqual(1,sum("notice=no_credits" in r for r in results))
        self.assertEqual(0,self.row("SELECT SUM(amount) FROM credit_transactions")[0])
        self.assertEqual(1,self.row("SELECT COUNT(*) FROM lifetime_licenses")[0])

    def test_existing_dashboard_and_new_credit_routes_are_unique(self):
        routes={}
        for rule in self.core.app.url_map.iter_rules():
            for method in rule.methods-{"HEAD","OPTIONS"}:
                key=(str(rule),method)
                self.assertNotIn(key,routes, key)
                routes[key]=rule.endpoint
        self.assertEqual("v080_reseller_dashboard",routes[("/reseller","GET")])
        self.assertEqual("v080_reseller_create_customer",routes[("/reseller/customers","POST")])
        for client,path in ((self.admin,"/admin"),(self.reseller,"/reseller")):
            response=client.get(path)
            self.assertEqual(200,response.status_code)
            self.assertIn("Credits &amp; Lizenzen".replace("&amp;","&"),response.get_data(as_text=True))
        self.assertEqual(1000,self.reseller.get("/v1/license/capabilities").json["retail_price_eur_cents"])
        self.assertEqual(400,self.reseller.post("/v1/license/status",json={}).status_code)

    def test_reseller_cannot_activate_another_resellers_device(self):
        other=self.make_reseller("Other reseller")
        device=self.make_device("other-tv",other)
        self.status("other-tv")
        self.assertEqual(404,self.reseller.post(f"/reseller/devices/{device}/activate-lifetime").status_code)
        self.assertEqual(0,self.row("SELECT COUNT(*) FROM lifetime_licenses")[0])

    def test_reseller_deletion_preserves_credit_history(self):
        self.admin.post(f"/admin/resellers/{self.reseller_id}/credits",data={"amount":"1"})
        self.admin.post(f"/admin/v080/resellers/{self.reseller_id}/delete")
        self.assertIsNotNone(self.row("SELECT id FROM resellers WHERE id=?",(self.reseller_id,)))
        self.assertEqual(1,self.row("SELECT SUM(amount) FROM credit_transactions")[0])


if __name__ == "__main__":
    unittest.main()
