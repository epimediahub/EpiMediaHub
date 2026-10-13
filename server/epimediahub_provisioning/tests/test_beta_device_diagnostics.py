"""Opt-in, authenticated, whitelisted device error counters."""
import os
import sys
from pathlib import Path
import tempfile
import unittest
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BOOT = tempfile.TemporaryDirectory()
os.environ["EPIMEDIAHUB_DATA_DIR"] = BOOT.name
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "diagnostics-test-secret"
import app as core
from dashboard_v080 import migrate_resellers
import device_diagnostics as reports


class DeviceReports(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        core.BASE_DIR = Path(self.temp.name)
        core.DB_PATH = core.BASE_DIR / "provisioning.db"
        core.init_db()
        reports.migrate()
        with core.db() as con:
            con.execute("INSERT INTO customers(name,created_at) VALUES(?,?)",("Consent test",core.iso(core.utcnow())))
            self.customer=con.execute("SELECT id FROM customers WHERE name='Consent test'").fetchone()[0]
            con.execute("""INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at)
                           VALUES(?,?,'android',?,?)""",
                        (self.customer, "safe-device-id", core.digest("valid-device-token-"+"x"*35), core.iso(core.utcnow())))
            self.device=con.execute("SELECT id FROM devices WHERE device_id='safe-device-id'").fetchone()[0]
        self.client=core.app.test_client()
        self.headers={"Authorization":"Bearer "+"valid-device-token-"+"x"*35}
        self.sample={"consent": True, "component": "PLAYER", "code": "NO_AUDIO", "app_version":"1.0.64"}

    def test_consent_auth_and_only_enumerated_fields(self):
        route="/v1/device/error-report"
        self.assertEqual(self.client.post(route,json=self.sample).status_code,401)
        self.assertEqual(self.client.post(route,json={**self.sample,"consent":False},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post(route,json={**self.sample,"url":"https://secret.invalid/playlist?password=x"},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post(route,json={**self.sample,"code":"user-text"},headers=self.headers).status_code,400)
        accepted=self.client.post(route,json=self.sample,headers=self.headers)
        self.assertEqual(accepted.status_code,201)
        self.assertIn("no-store",accepted.headers["Cache-Control"])
        with core.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM device_error_events").fetchone()[0],1)
            self.assertEqual(reports.aggregate(con)[0]["code"],"NO_AUDIO")

    def test_rate_limit_expiry_and_disabled_device(self):
        route="/v1/device/error-report"
        for _ in range(reports.MAX_REPORTS_PER_DAY):
            self.assertEqual(self.client.post(route,json=self.sample,headers=self.headers).status_code,201)
        self.assertEqual(self.client.post(route,json=self.sample,headers=self.headers).status_code,429)
        with core.db() as con:
            con.execute("UPDATE device_error_events SET reported_at=? WHERE id=(SELECT MIN(id) FROM device_error_events)",
                        (core.iso(core.utcnow()-timedelta(days=31)),))
            con.execute("UPDATE devices SET enabled=0 WHERE id=?",(self.device,))
        self.assertEqual(self.client.post(route,json=self.sample,headers=self.headers).status_code,401)


if __name__=="__main__":
    unittest.main()
