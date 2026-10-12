"""Security regression: admin/reseller CSRF, isolation, and private cache headers."""
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BOOT = tempfile.TemporaryDirectory()
os.environ["EPIMEDIAHUB_DATA_DIR"] = BOOT.name
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "fixed-test-secret-for-browser-sessions"
os.environ["EPIMEDIAHUB_SECURE_COOKIES"] = "0"
import app as core
from dashboard_v080 import install as install_dashboard
import license_api
import annual_license
from dashboard_security import install as install_security

install_dashboard(core.app, core.db)
core.app.add_url_rule("/skip-test", endpoint="v082_skip_dashboard", view_func=lambda: "skip")
install_security(core.app)
core.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)


class BrowserSecurity(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        core.BASE_DIR = Path(self.temp.name)
        core.DB_PATH = core.BASE_DIR / "provisioning.db"
        core.init_db()
        license_api.ensure_license_schema()
        annual_license._migrate()
        self.client = core.app.test_client()
        with self.client.session_transaction() as s:
            s["admin"] = True

    def token(self, client):
        response = client.get("/admin")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'_dashboard_csrf', response.data)
        self.assertIn("no-store", response.headers["Cache-Control"])
        self.assertEqual("DENY", response.headers["X-Frame-Options"])
        with client.session_transaction() as s:
            return s["_dashboard_csrf"]

    def test_rejects_missing_cross_session_and_accepts_valid_token(self):
        token = self.token(self.client)
        data = {"name": "Security reseller", "username": "secure_test",
                "password": "Valid-test-password-321"}
        route = "/admin/v080/resellers"
        self.assertEqual(self.client.post(route, data=data).status_code, 403)
        other = core.app.test_client()
        with other.session_transaction() as s:
            s["admin"] = True
        self.assertEqual(other.post(route, data=data, headers={"X-Dashboard-CSRF": token}).status_code, 403)
        valid = self.client.post(route, data=data, headers={"X-Dashboard-CSRF": token})
        self.assertIn(valid.status_code, (302, 303))
        with core.db() as con:
            self.assertIsNotNone(con.execute("SELECT id FROM resellers WHERE username='secure_test'").fetchone())

    def test_login_forms_include_csrf_token(self):
        guest = core.app.test_client()
        page = guest.get("/admin/login")
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="_dashboard_csrf"', page.data)
        self.assertEqual(guest.post("/admin/login", data={"password": "anything"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
