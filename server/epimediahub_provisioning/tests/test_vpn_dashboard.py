"""VPN routes exercised through Flask and SQLite, with the existing dashboard schema."""
import base64
import importlib
import json
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import unittest
from datetime import timedelta

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BOOT = tempfile.TemporaryDirectory()
os.environ["EPIMEDIAHUB_DATA_DIR"] = BOOT.name
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "local-test-session-secret"
os.environ["EPIMEDIAHUB_ADMIN_PASSWORD"] = "local-test-admin-password"
os.environ["EPIMEDIAHUB_VPN_AGENT_TOKEN"] = "local-agent-test-token-with-enough-length"
import app as core
from dashboard_v080 import install as dashboard_install, migrate_resellers
import vpn_dashboard as vpn

dashboard_install(core.app, core.db)
vpn.install(core.app, core.db)
core.app.config.update(TESTING=True, SESSION_COOKIE_SECURE=False)
KEY1 = base64.b64encode(bytes(range(32))).decode()
KEY2 = base64.b64encode(bytes(range(1,33))).decode()


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        core.BASE_DIR = Path(self.temp.name)
        core.DB_PATH = core.BASE_DIR / "provisioning.db"
        core.init_db()
        with core.db() as con:
            migrate_resellers(con)
            vpn.migrate(con)
            for rid in (1,2):
                con.execute("INSERT INTO resellers(id,name,username,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?)", (rid, f"Reseller {rid}", f"r{rid}", "unused", vpn.stamp(), vpn.stamp()))
                con.execute("INSERT INTO customers(id,name,created_at,reseller_id) VALUES(?,?,?,?)", (rid, f"Kunde {rid}", vpn.stamp(), rid))
            for did,cid in ((1,1),(2,2),(3,1)):
                con.execute("INSERT INTO devices(id,customer_id,device_id,display_name,platform,session_token_hash,created_at) VALUES(?,?,?,?,?,?,?)", (did,cid,f"android-{did}",f"Fire TV {did}","android",f"token-{did}",vpn.stamp()))
        self.admin = core.app.test_client()
        self.reseller = core.app.test_client()
        self.other = core.app.test_client()
        self.anonymous = core.app.test_client()
        with self.admin.session_transaction() as session: session["admin"] = True
        with self.reseller.session_transaction() as session: session["reseller_id"] = 1
        with self.other.session_transaction() as session: session["reseller_id"] = 2
        self.auth = {"Authorization": "Bearer " + os.environ["EPIMEDIAHUB_VPN_AGENT_TOKEN"]}

    def post(self, operation, *, client=None, request_id=None, **values):
        client = client or self.admin
        base = "/admin/vpn" if client is self.admin else "/reseller/vpn"
        page = client.get(base)
        self.assertEqual(page.status_code,200)
        csrf = re.search(r'name="csrf" value="([^"]+)"', page.text)[1]
        return client.post(base + "/action", data={"operation":operation,"csrf":csrf,"request_id":request_id or secrets.token_urlsafe(24),**values})

    def bind(self, did=1, key=KEY1, address="10.92.0.2"):
        self.assertEqual(self.post("bind",device_row_id=did,public_key=key,client_address=address).status_code,303)

    def snapshot(self):
        response = self.anonymous.get("/v1/vpn-agent/desired", headers=self.auth)
        self.assertEqual(response.status_code,200)
        return response.json

    def ack(self, snapshot=None):
        snapshot = snapshot or self.snapshot()
        return self.anonymous.post("/v1/vpn-agent/applied",headers=self.auth,json={"peers":[{k:p[k] for k in ("id","generation","enabled")} for p in snapshot["peers"]]})

    def fund(self):
        self.post("price", reseller_id=1, price="3,25")
        self.post("credit", reseller_id=1, amount=10, note="Testguthaben")
        self.post("plan", name="Finnland Monat", days=30, credits=2)

    def test_login_and_tenant_boundaries(self):
        self.assertEqual(self.anonymous.get("/admin/vpn").status_code,302)
        page = self.reseller.get("/reseller/vpn")
        self.assertIn("Kunde 1",page.text)
        self.assertNotIn("Kunde 2",page.text)
        self.assertEqual(self.post("suspend",client=self.reseller,device_row_id=2).status_code,404)
        self.assertEqual(self.post("credit",client=self.reseller,reseller_id=1,amount=9,note="bad").status_code,403)

    def test_csrf_without_prior_page_is_rejected(self):
        result=self.admin.post("/admin/vpn/action",data={"csrf":"missing","operation":"plan","request_id":secrets.token_urlsafe(24),"name":"bad","days":30,"credits":1})
        self.assertEqual(result.status_code,403)
        with core.db() as con:self.assertEqual(con.execute("SELECT COUNT(*) FROM vpn_plans").fetchone()[0],0)

    def test_duplicate_keys_addresses_and_bad_addresses_do_not_bind(self):
        self.bind()
        self.bind(3,KEY2,"10.92.0.2")
        self.bind(3,KEY1,"10.92.0.3")
        self.bind(3,KEY2,"0.0.0.0/0")
        with core.db() as con:self.assertEqual(con.execute("SELECT COUNT(*) FROM vpn_devices").fetchone()[0],1)

    def test_grant_ack_suspend_and_stale_ack(self):
        self.bind()
        self.post("grant",device_row_id=1,days=7)
        snapshot=self.snapshot()
        self.assertTrue(snapshot["peers"][0]["enabled"])
        self.assertIn("Bestätigung offen",self.admin.get("/admin/vpn").text)
        self.assertEqual(self.ack(snapshot).status_code,200)
        self.assertIn('badge green',self.admin.get("/admin/vpn").text)
        self.post("suspend",device_row_id=1)
        self.assertEqual(self.ack(snapshot).status_code,409)
        self.assertFalse(self.snapshot()["peers"][0]["enabled"])
        self.assertEqual(self.ack().status_code,200)

    def test_expiry_device_revocation_customer_change_and_reseller_block_fail_closed(self):
        self.bind()
        self.post("grant",device_row_id=1,days=7)
        for sql,restore in (("UPDATE devices SET enabled=0 WHERE id=1","UPDATE devices SET enabled=1 WHERE id=1"),("UPDATE resellers SET enabled=0 WHERE id=1","UPDATE resellers SET enabled=1 WHERE id=1"),("UPDATE devices SET customer_id=2 WHERE id=1","UPDATE devices SET customer_id=1 WHERE id=1")):
            with core.db() as con:con.execute(sql)
            self.assertFalse(self.snapshot()["peers"][0]["enabled"])
            with core.db() as con:con.execute(restore)
        with core.db() as con:con.execute("UPDATE vpn_devices SET expires_at=?",(vpn.stamp(vpn.now()-timedelta(seconds=1)),))
        self.assertFalse(self.snapshot()["peers"][0]["enabled"])

    def test_deleted_device_remains_revocation_tombstone(self):
        self.bind();self.post("grant",device_row_id=1,days=7)
        with core.db() as con:con.execute("DELETE FROM devices WHERE id=1")
        peers=self.snapshot()["peers"]
        self.assertEqual(len(peers),1);self.assertFalse(peers[0]["enabled"])

    def test_price_required_price_snapshot_and_approval_exactly_once(self):
        self.post("order",client=self.reseller,quantity=2,unit_price_cents=100)
        with core.db() as con:self.assertEqual(con.execute("SELECT COUNT(*) FROM vpn_orders").fetchone()[0],0)
        self.post("price",reseller_id=1,price="3,25")
        self.post("order",client=self.reseller,quantity=2,unit_price_cents=325)
        self.post("price",reseller_id=1,price="4,00")
        self.post("order",client=self.reseller,quantity=2,unit_price_cents=325)
        self.post("approve",order_id=1);self.post("approve",order_id=1)
        with core.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM vpn_orders").fetchone()[0],1)
            self.assertEqual(con.execute("SELECT unit_price_cents FROM vpn_orders").fetchone()[0],325)
            self.assertEqual(vpn.balance(con,1),2)

    def test_no_server_means_no_credit_charge_and_retry_is_idempotent(self):
        self.bind();self.fund()
        self.post("activate",client=self.reseller,device_row_id=1,plan="1:30:2")
        with core.db() as con:self.assertEqual(vpn.balance(con,1),10)
        self.assertEqual(self.ack().status_code,200)
        nonce=secrets.token_urlsafe(24)
        self.post("activate",client=self.reseller,request_id=nonce,device_row_id=1,plan="1:30:2")
        with core.db() as con:first=con.execute("SELECT expires_at FROM vpn_devices").fetchone()[0]
        self.post("activate",client=self.reseller,request_id=nonce,device_row_id=1,plan="1:30:2")
        with core.db() as con:
            self.assertEqual(vpn.balance(con,1),8)
            self.assertEqual(con.execute("SELECT expires_at FROM vpn_devices").fetchone()[0],first)

    def test_reseller_cannot_transfer_and_admin_transfer_retires_old_key(self):
        self.bind();self.post("grant",device_row_id=1,days=7)
        values=dict(device_row_id=1,target_device_row_id=3,public_key=KEY2,client_address="10.92.0.2")
        self.assertEqual(self.post("transfer",client=self.reseller,**values).status_code,403)
        self.post("transfer",**values)
        peers=self.snapshot()["peers"]
        self.assertEqual([p["enabled"] for p in peers],[False,True])
        self.assertEqual(peers[0]["expires_at"],peers[1]["expires_at"])

    def test_agent_auth_partial_ack_and_private_data(self):
        self.bind()
        self.assertEqual(self.anonymous.get("/v1/vpn-agent/desired").status_code,401)
        self.assertEqual(self.anonymous.post("/v1/vpn-agent/applied",headers=self.auth,json={"peers":[]}).status_code,409)
        payload=json.dumps(self.snapshot())
        self.assertNotIn("Kunde",payload);self.assertNotIn("token-1",payload);self.assertNotIn("PrivateKey",payload)
        self.assertEqual(self.admin.get("/admin/vpn").headers["Cache-Control"],"no-store")

    def test_dashboard_to_agent_and_back_uses_the_actual_protocol(self):
        from test_vpn_agent import FakeWireGuard
        from vpn_finland_agent import Agent
        self.bind();self.post("grant",device_row_id=1,days=7)
        config_file=Path(self.temp.name)/"wg0.conf"
        config_file.write_text(f"[Interface]\nAddress = 10.92.0.1/24\n\n[Peer]\nPublicKey = {KEY1}\nAllowedIPs = 10.92.0.2/32\n")
        runner=FakeWireGuard()
        agent=Agent({"dashboard_url":"https://api.epimediahub.com","token":"test-"*10,"state_file":str(Path(self.temp.name)/"agent-state.json"),"wireguard_config":str(config_file)},runner)
        report=agent.apply(self.snapshot())
        self.assertEqual(self.anonymous.post("/v1/vpn-agent/applied",headers=self.auth,json=report).status_code,200)
        self.post("suspend",device_row_id=1)
        report=agent.apply(self.snapshot())
        self.assertEqual(runner.peers[KEY1],set())
        self.assertEqual(self.anonymous.post("/v1/vpn-agent/applied",headers=self.auth,json=report).status_code,200)

    def test_escaping_and_repeated_migration_preserve_existing_data(self):
        with core.db() as con:
            con.execute("UPDATE customers SET name='<script>alert(1)</script>' WHERE id=1")
            con.execute("CREATE TABLE legacy_credits(amount INTEGER)");con.execute("INSERT INTO legacy_credits VALUES(42)")
            vpn.migrate(con);vpn.migrate(con)
            self.assertEqual(con.execute("SELECT amount FROM legacy_credits").fetchone()[0],42)
        page=self.admin.get("/admin/vpn")
        self.assertIn("&lt;script&gt;",page.text);self.assertNotIn("<script>alert(1)",page.text)


if __name__ == "__main__":
    unittest.main()
