"""Regression tests for admin-only, privacy-first dashboard diagnostics."""
import importlib
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BOOT = tempfile.TemporaryDirectory()
os.environ["EPIMEDIAHUB_DATA_DIR"] = BOOT.name
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "test-strong-secret"
import app as core
from dashboard_v080 import install as install_dashboard, migrate_resellers

install_dashboard(core.app, core.db)
core.app.add_url_rule("/test-skip-dashboard", endpoint="v082_skip_dashboard", view_func=lambda: "ok")
import license_api
import annual_license
import dashboard_diagnostics
core.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)


class DiagnosticsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        core.BASE_DIR = Path(self.temp.name)
        core.DB_PATH = core.BASE_DIR / "provisioning.db"
        core.init_db()
        with core.db() as con:
            migrate_resellers(con)
            con.execute("INSERT INTO customers(name,created_at) VALUES('Testkunde','2026-10-12T18:00:00Z')")
            customer_id = con.execute("SELECT id FROM customers WHERE name='Testkunde'").fetchone()[0]
            con.execute("""INSERT INTO devices(customer_id,device_id,platform,session_token_hash,created_at,last_sync_status)
                           VALUES(?,?,'android',?,'2026-10-12T18:00:00Z','error')""",
                        (customer_id, "sensitive-device-id-abc", "secret-token-hash-xyz"))
        self.admin = core.app.test_client()
        with self.admin.session_transaction() as sess:
            sess["admin"] = True

    def test_admin_only_and_private_response(self):
        anonymous = core.app.test_client()
        response = anonymous.get("/admin/diagnostics")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login", response.location)
        response = self.admin.get("/admin/diagnostics")
        self.assertEqual(response.status_code, 200)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual("DENY", response.headers["X-Frame-Options"])
        self.assertIn(b"Synchronisierung", response.data)
        self.assertNotIn(b"sensitive-device-id-abc", response.data)
        self.assertNotIn(b"secret-token-hash-xyz", response.data)

    def test_admin_dashboard_navigation(self):
        # Every manager can find the diagnostics without exposing its contents.
        response = self.admin.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"/admin/diagnostics", response.data)


if __name__ == "__main__":
    unittest.main()
