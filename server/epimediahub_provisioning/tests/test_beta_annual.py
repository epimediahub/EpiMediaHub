"""365-day subscription, backwards compatibility and no-credit regressions."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BOOT = tempfile.TemporaryDirectory()
os.environ["EPIMEDIAHUB_DATA_DIR"] = BOOT.name
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "test-annual-app-entitlement-secret"
os.environ["EPIMEDIAHUB_SECURE_COOKIES"] = "0"
import app as core
from dashboard_v080 import install as install_dashboard, migrate_resellers
install_dashboard(core.app, core.db)
core.app.add_url_rule("/stub-skip", endpoint="v082_skip_dashboard", view_func=lambda: "ok")
import license_api
import annual_license
from dashboard_security import install as install_security
install_security(core.app)
core.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)


class AnnualLicenseTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        core.BASE_DIR = Path(self.temp.name)
        core.DB_PATH = core.BASE_DIR / "provisioning.db"
        core.init_db()
        license_api.ensure_license_schema()
        annual_license._migrate()
        with core.db() as con:
            con.execute("INSERT INTO customers(name,created_at) VALUES(?,?)",
                        ("Jahreslizenzkunde", core.iso(core.utcnow())))
            self.customer = con.execute("SELECT id FROM customers WHERE name='Jahreslizenzkunde'").fetchone()[0]
            con.execute("""INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at)
                  VALUES(?,?,'android',?,?)""",
                  (self.customer, "annual-device-1", "seshash-1", core.iso(core.utcnow())))
            self.device = con.execute("SELECT id FROM devices WHERE device_id='annual-device-1'").fetchone()[0]
        self.admin = core.app.test_client()
        with self.admin.session_transaction() as sess:
            sess["admin"] = True
        self.admin.get("/admin")
        with self.admin.session_transaction() as sess:
            self.token = sess["_dashboard_csrf"]
        self.path = f"/admin/devices/{self.device}/grant-year"
        self._status()  # Device registered its trial secret before an admin grant.

    def _grant(self):
        return self.admin.post(self.path, data={"_dashboard_csrf":self.token})

    def _status(self, **extra):
        return self.admin.post("/v1/license/status", json={
            "device_id":"annual-device-1", "trial_key":"f"*64, **extra})

    def test_annual_grant_365_days_idempotent_and_no_credit(self):
        self.assertEqual(self._grant().status_code, 302)
        with core.db() as con:
            granted = con.execute("SELECT * FROM annual_device_licenses WHERE device_id='annual-device-1'").fetchone()
            self.assertIsNotNone(granted)
            seconds = (annual_license._parse(granted["expires_at"]) - annual_license._parse(granted["granted_at"])).total_seconds()
            self.assertEqual(seconds, 365*86400)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM credit_transactions").fetchone()[0],0)
            prior = granted["expires_at"]
        self.assertEqual(self._grant().status_code, 302)
        with core.db() as con:
            self.assertEqual(con.execute("SELECT expires_at FROM annual_device_licenses WHERE device_id='annual-device-1'").fetchone()[0], prior)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM audit_log WHERE action='grant_annual_app_license'").fetchone()[0],1)
        old = self._status()
        self.assertEqual(old.status_code, 200)
        self.assertEqual(old.json["status"], "TRIAL_ACTIVE")
        self.assertEqual(old.json["entitlement_type"], "ANNUAL")
        self.assertGreater(old.json["remaining_seconds"],364*86400)
        new = self._status(supported_entitlements=["ANNUAL"])
        self.assertEqual(new.json["status"], "ANNUAL_ACTIVE")
        self.assertEqual(self.admin.get("/v1/license/capabilities").json["annual_days"],365)
        self.assertIn(b"App 1 Jahr", self.admin.get("/admin").data)

    def test_copied_device_id_cannot_steal_year(self):
        self._grant()
        stolen = self._status(trial_key="c"*64)
        self.assertNotEqual(stolen.json.get("entitlement_type"), "ANNUAL")

    def test_expiration_returns_authoritative_trial_state(self):
        self._grant()
        self._status()
        with core.db() as con:
            past = core.iso(core.utcnow() - timedelta(days=2))
            con.execute("UPDATE annual_device_licenses SET expires_at=?", (past,))
            con.execute("UPDATE license_subjects SET trial_expires_at=?",(past,))
        response = self._status(supported_entitlements=["ANNUAL"])
        self.assertEqual(response.json["status"], "TRIAL_EXPIRED")

    def test_admin_only_and_revocation(self):
        other = core.app.test_client()
        other.get("/reseller/login")
        with other.session_transaction() as sess:
            sess["reseller_id"] = 50
            other_token = sess["_dashboard_csrf"]
        response=other.post(self.path,data={"_dashboard_csrf":other_token})
        self.assertEqual(response.status_code, 302)
        with core.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM annual_device_licenses").fetchone()[0],0)
        self._grant()
        revoke = self.admin.post(f"/admin/devices/{self.device}/revoke-year",data={"_dashboard_csrf":self.token})
        self.assertEqual(revoke.status_code,302)
        with core.db() as con:
            self.assertIsNotNone(con.execute("SELECT revoked_at FROM annual_device_licenses WHERE device_id='annual-device-1'").fetchone()[0])
        self.assertNotEqual(self._status(supported_entitlements=["ANNUAL"]).json["status"],"ANNUAL_ACTIVE")

    def test_lifetime_not_downgraded(self):
        self._status()
        with core.db() as con:
            sid=con.execute("SELECT id FROM license_subjects LIMIT 1").fetchone()[0]
            con.execute("""INSERT INTO lifetime_licenses(subject_id,customer_id,activated_device_id,status,source,activated_at)
                       VALUES(?,?,?,'ACTIVE','admin_grant',?)""",
                       (sid,self.customer,"annual-device-1",core.iso(core.utcnow())))
        self._grant()
        with core.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM annual_device_licenses").fetchone()[0],0)
        self.assertEqual(self._status(supported_entitlements=["ANNUAL"]).json["status"],"LIFETIME_ACTIVE")


if __name__=="__main__":
    unittest.main()
