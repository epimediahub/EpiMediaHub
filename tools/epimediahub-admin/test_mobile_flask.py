"""Real Flask test-client checks for private Admin mobile authorization."""
import os
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import uuid
from unittest import mock

from flask import Flask
import mobile_flask
from mobile_registry import AdminMobileRegistry


class TestPrivateAdminMobile(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=mock.patch.dict(os.environ,{
            "EPIMEDIAHUB_DATA_DIR":self.temp.name,
            "EPIMEDIAHUB_ADMIN_FCM_PROJECT_ID":"epi-admin-test"
        })
        self.env.start()
        self.app=Flask("test-private-admin")
        self.app.secret_key="a-long-isolated-test-only-secret"
        self.app.add_url_rule("/login","login",lambda:"login")
        mobile_flask.install(self.app)
        self.client=self.app.test_client()
        self.install=str(uuid.uuid4())
        self.token="TEST_FCM_"+"a"*160

    def tearDown(self):
        self.env.stop()
        self.temp.cleanup()

    def signin(self):
        with self.client.session_transaction() as session:
            session["admin"]=True
            session["_dashboard_csrf"]="my-test-csrf-"+"a"*32

    def test_anonymous_cannot_read_or_register(self):
        self.assertEqual(self.client.get("/admin/mobile/bootstrap").status_code,401)
        self.assertEqual(self.client.get("/admin/mobile/alerts.json").status_code,401)
        self.assertEqual(self.client.post("/admin/mobile/register",json={
            "installation_id":self.install,"fcm_token":self.token,
            "platform":"android-admin"}).status_code,401)

    def test_csrf_and_registration_idempotent_and_private(self):
        self.signin()
        data={"installation_id":self.install,"fcm_token":self.token,
              "platform":"android-admin"}
        boot=self.client.get("/admin/mobile/bootstrap")
        self.assertEqual(boot.status_code,200)
        csrf=boot.get_json()["csrf"]
        self.assertEqual(boot.headers["Cache-Control"],"private, no-store")
        self.assertEqual(self.client.post("/admin/mobile/register",json=data).status_code,403)
        result=self.client.post("/admin/mobile/register",json=data,
            headers={"X-Dashboard-CSRF":csrf})
        self.assertEqual(result.status_code,201)
        self.assertEqual(self.client.post("/admin/mobile/register",json=data,
            headers={"X-Dashboard-CSRF":csrf}).status_code,201)
        registry=AdminMobileRegistry(Path(self.temp.name)/"admin-mobile"/"registrations.sqlite3")
        self.assertEqual(registry.active_count(),1)
        self.assertNotIn(self.token,str(result.get_json()))
        self.assertEqual(self.client.post("/admin/mobile/unregister",
            json={"installation_id":self.install},
            headers={"X-Dashboard-CSRF":csrf}).status_code,200)
        self.assertEqual(registry.active_count(),0)

    def test_untrusted_fields_or_platform_blocked(self):
        self.signin()
        csrf=self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]
        data={"installation_id":self.install,"fcm_token":self.token,
            "platform":"android-admin","password":"DO-NOT-STORE"}
        self.assertEqual(self.client.post("/admin/mobile/register",json=data,
            headers={"X-Dashboard-CSRF":csrf}).status_code,400)
        data.pop("password")
        data["platform"]="iptv-player"
        self.assertEqual(self.client.post("/admin/mobile/register",json=data,
            headers={"X-Dashboard-CSRF":csrf}).status_code,400)

    def test_incident_page_html_autoescapes_alerts(self):
        self.signin()
        from monitor_rules import Alert
        mobile_flask._incidents().observe([Alert(
            "analysis_stalled:8","analysis_stalled","critical","8",
            "<script>alert(123)</script>")],1760000000)
        view=self.client.get("/admin/mobile/alerts")
        self.assertEqual(view.status_code,200)
        self.assertIn(b"&lt;script&gt;",view.data)
        self.assertNotIn(b"<script>alert(123)",view.data)
        self.assertEqual(view.headers["Cache-Control"],"no-store, private")

    def test_native_episcene_api_never_leaks_sources_without_session(self):
        self.assertEqual(self.client.get("/admin/mobile/episcene/status").status_code,401)
        self.signin()
        sanitized={"sampled_at_epoch":1234567890,"scope":"independent_analysis_sources_only",
                   "lanes":[{"id":8,"label":"4K ANALYSE","enabled":True,"queued":10,
                             "running":1,"completed":3,"failed":0,
                             "last_completion_epoch":1234567880},
                            {"id":10,"label":"THE BEST","enabled":True,"queued":20,
                             "running":0,"completed":5,"failed":0,
                             "last_completion_epoch":None}]}
        with mock.patch.object(mobile_flask,"read_status",return_value=sanitized):
            response=self.client.get("/admin/mobile/episcene/status")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.get_json(),sanitized)
        self.assertEqual(response.headers["Cache-Control"],"private, no-store")
        with mock.patch.object(mobile_flask,"read_status",
                               side_effect=RuntimeError("database locked")):
            unavailable=self.client.get("/admin/mobile/episcene/status")
        self.assertEqual(unavailable.status_code,503)
        self.assertNotIn("database locked",unavailable.get_data(as_text=True))

    def test_admin_updates_require_login_and_private_digest(self):
        self.assertEqual(self.client.get("/admin/mobile/update/status").status_code,401)
        self.assertEqual(self.client.get("/admin/mobile/update/apk").status_code,401)
        self.signin()
        self.assertEqual(self.client.get("/admin/mobile/update/status").get_json(),
                         {"available":False})
        self.assertEqual(self.client.get("/admin/mobile/update/apk").status_code,404)
        private=Path(self.temp.name)/"admin-mobile"
        private.mkdir(mode=0o700)
        private.chmod(0o700)
        folder=private/"releases"
        folder.mkdir(mode=0o700)
        content=b"TEST_NOT_A_REAL_APK"*1024
        (folder/"current.apk").write_bytes(content)
        (folder/"current.apk").chmod(0o600)
        payload={"package":"de.epimediahub.admin","version_code":25,
                 "version_name":"1.0.25",
                 "sha256":hashlib.sha256(content).hexdigest(),
                 "size_bytes":len(content)}
        (folder/"current.json").write_text(json.dumps(payload))
        (folder/"current.json").chmod(0o600)
        status=self.client.get("/admin/mobile/update/status")
        self.assertEqual(status.status_code,200)
        self.assertEqual(status.get_json()["version_code"],25)
        self.assertEqual(status.headers["Cache-Control"],"private, no-store")
        apk=self.client.get("/admin/mobile/update/apk")
        self.assertEqual(apk.status_code,200)
        self.assertEqual(apk.data,content)
        self.assertEqual(apk.headers["Cache-Control"],"private, no-store")
        self.assertEqual(apk.headers["X-Admin-APK-SHA256"],payload["sha256"])
        (folder/"current.apk").write_bytes(b"BAD"+content)
        invalid=self.client.get("/admin/mobile/update/status")
        self.assertEqual(invalid.status_code,503)
        self.assertNotIn("private_key",str(invalid.get_json()))

    def test_symlinked_private_update_file_never_served(self):
        self.signin()
        private=Path(self.temp.name)/"admin-mobile"
        private.mkdir(mode=0o700)
        folder=private/"releases"
        folder.mkdir(mode=0o700)
        (folder/"current.apk").symlink_to(Path(self.temp.name)/"outside.apk")
        (folder/"current.json").write_text("{}")
        (folder/"current.json").chmod(0o600)
        self.assertEqual(self.client.get("/admin/mobile/update/apk").status_code,503)

    def test_native_alert_ack_requires_admin_csrf_and_safe_json(self):
        route="/admin/mobile/alerts/ack"
        self.assertEqual(self.client.post(route,json={"alert_key":"analysis_stalled:8"}).status_code,401)
        self.signin()
        from monitor_rules import Alert
        mobile_flask._incidents().observe([Alert(
            "analysis_stalled:8","analysis_stalled","critical","8","Analyse ohne Fortschritt")],
            1760000000)
        data={"alert_key":"analysis_stalled:8"}
        self.assertEqual(self.client.post(route,json=data).status_code,403)
        csrf=self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]
        invalid=self.client.post(route,json=dict(data,secret="DO_NOT_STORE"),
                                 headers={"X-Dashboard-CSRF":csrf})
        self.assertEqual(invalid.status_code,400)
        response=self.client.post(route,json=data,headers={"X-Dashboard-CSRF":csrf})
        self.assertEqual(response.status_code,200)
        self.assertTrue(response.get_json()["acknowledged"])
        self.assertNotIn("DO_NOT_STORE",response.get_data(as_text=True))
        again=self.client.post(route,json=data,headers={"X-Dashboard-CSRF":csrf})
        self.assertFalse(again.get_json()["acknowledged"])

    def test_login_required_for_acknowledgements(self):
        self.signin()
        from monitor_rules import Alert
        mobile_flask._incidents().observe([Alert(
            "analysis_stalled:8","analysis_stalled","critical","8",
            "EpiScene-Lane ohne Fortschritt trotz wartender Jobs")],1760000000)
        self.assertEqual(self.client.post("/admin/mobile/ack/analysis_stalled:8").status_code,403)
        csrf=self.client.get("/admin/mobile/bootstrap").get_json()["csrf"]
        r=self.client.post("/admin/mobile/ack/analysis_stalled:8",
            data={"_dashboard_csrf":csrf})
        self.assertEqual(r.status_code,303)
        self.assertEqual(mobile_flask._incidents().get("analysis_stalled:8")["state"],"acknowledged")


if __name__=="__main__":
    unittest.main()
