"""End-to-end VPN provisioning without manual keys, with tenant and billing boundaries."""
import base64
import os
from pathlib import Path
import re
import secrets
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
BOOT = tempfile.TemporaryDirectory()
os.environ["EPIMEDIAHUB_DATA_DIR"] = BOOT.name
os.environ["EPIMEDIAHUB_SECRET_KEY"] = "test-autoprovision-session"
os.environ["EPIMEDIAHUB_VPN_AGENT_TOKEN"] = "private-agent-test-token-with-enough-entropy"
import app as core
import vpn_dashboard as vpn
from dashboard_v080 import install as install_dashboard, migrate_resellers

install_dashboard(core.app,core.db)
vpn.install(core.app,core.db)
core.app.config.update(TESTING=True,SESSION_COOKIE_SECURE=False)
KEYS = [base64.b64encode(bytes(range(i,i+32))).decode() for i in (1,33,65)]
SERVER_KEY = base64.b64encode(bytes(range(110,142))).decode()

class AutomaticProvisioningTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        core.BASE_DIR = Path(self.temp.name)
        core.DB_PATH = core.BASE_DIR / "provisioning.db"
        core.init_db()
        with core.db() as con:
            migrate_resellers(con)
            vpn.migrate(con)
            for id in (1,2):
                con.execute("INSERT INTO resellers(id,name,username,password_hash,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                            (id,f"Reseller {id}",f"reseller{id}","unused",vpn.stamp(),vpn.stamp()))
                con.execute("INSERT INTO customers(id,name,reseller_id,created_at) VALUES(?,?,?,?)",
                            (id,f"Customer {id}",id,vpn.stamp()))
                con.execute("""INSERT INTO devices(id,customer_id,device_id,platform,session_token_hash,created_at)
                               VALUES(?,?,?,?,?,?)""",
                            (id,id,f"stable-device-{id}","android",core.digest("valid-device-session-"+str(id)+"-"*10),vpn.stamp()))
        self.admin=core.app.test_client()
        self.reseller=core.app.test_client()
        self.guest=core.app.test_client()
        with self.admin.session_transaction() as x:x["admin"]=True
        with self.reseller.session_transaction() as x:x["reseller_id"]=1
        self.agent={"Authorization":"Bearer "+os.environ["EPIMEDIAHUB_VPN_AGENT_TOKEN"]}

    def auth(self, id):
        return {"Authorization":"Bearer "+"valid-device-session-"+str(id)+"-"*10}

    def enroll(self, id, key=None, device=None):
        return self.guest.post("/v1/device/vpn/enroll",headers=self.auth(id),
                               json={"device_id":device or f"stable-device-{id}","public_key":key or KEYS[id-1]})

    def post(self, operation, *, client=None, **data):
        client=client or self.admin
        base="/admin/vpn" if client is self.admin else "/reseller/vpn"
        response=client.get(base)
        token=re.search(r'name="csrf" value="([^"]+)"',response.text)[1]
        return client.post(base+"/action",data={"operation":operation,"request_id":secrets.token_urlsafe(24),"csrf":token,**data})

    def snapshot(self):
        return self.guest.get("/v1/vpn-agent/desired",headers=self.agent).json

    def ack(self):
        states=self.snapshot()["peers"]
        body={"peers":[{"id":x["id"],"generation":x["generation"],
                        "enabled":x["enabled"],"last_handshake":0} for x in states],
              "server_public_key":SERVER_KEY}
        return self.guest.post("/v1/vpn-agent/applied",headers=self.agent,json=body)

    def test_no_registration_or_known_public_id_without_session(self):
        self.assertEqual(401,self.guest.get("/v1/device/vpn/status").status_code)
        self.assertEqual(401,self.guest.post("/v1/device/vpn/enroll",json={"device_id":"stable-device-1","public_key":KEYS[0]}).status_code)
        self.assertEqual(403,self.enroll(1,device="stable-device-2").status_code)
        self.assertEqual(200,self.guest.get("/v1/device/identity",headers=self.auth(1)).status_code)
        self.assertEqual("stable-device-1",self.guest.get("/v1/device/identity",headers=self.auth(1)).json["device_id"])

    def test_admin_free_grant_first_then_no_key_adb_enroll_and_ack(self):
        x=self.post("grant",device_row_id="1",days="7")
        self.assertEqual(303,x.status_code)
        with core.db() as con:
            queued=con.execute("SELECT * FROM vpn_pending_grants WHERE device_row_id=1").fetchone()
            self.assertEqual(7,queued["days"])
        enrolled=self.enroll(1)
        self.assertEqual(200,enrolled.status_code)
        self.assertEqual("WAITING_FOR_SERVER",enrolled.json["status"])
        self.assertTrue(self.ack().status_code==200)
        result=self.guest.get("/v1/device/vpn/status",headers=self.auth(1)).json
        self.assertEqual("READY",result["status"])
        self.assertTrue(result["enabled"])
        self.assertEqual("stable-device-1",result["device_id"])
        self.assertEqual(SERVER_KEY,result["server_public_key"])
        self.assertEqual("10.92.0.2/32",result["client_address"])
        self.assertEqual(["0.0.0.0/0","::/0"],result["allowed_ips"])
        with core.db() as con:
            self.assertIsNone(con.execute("SELECT * FROM vpn_pending_grants WHERE device_row_id=1").fetchone())
            self.assertEqual(0,con.execute("SELECT COUNT(*) FROM vpn_credits").fetchone()[0])

    def test_idempotency_and_no_duplicate_tunnel_or_account(self):
        self.post("grant",device_row_id="1",days="7")
        self.enroll(1)
        self.assertEqual(200,self.enroll(1).status_code)
        self.assertEqual(409,self.enroll(1,key=KEYS[1]).status_code)
        self.assertEqual(409,self.enroll(2,key=KEYS[0]).status_code)
        self.assertEqual(200,self.enroll(2,key=KEYS[1]).status_code)
        with core.db() as con:
            self.assertEqual(2,con.execute("SELECT COUNT(*) FROM vpn_devices").fetchone()[0])
            addrs=[x[0] for x in con.execute("SELECT client_address FROM vpn_devices ORDER BY id")]
            self.assertEqual(["10.92.0.2/32","10.92.0.3/32"],addrs)

    def test_reseller_paid_queued_grant_is_charged_once(self):
        self.post("price",reseller_id=1,price="5,00")
        self.post("credit",reseller_id=1,amount=4,note="Test")
        self.post("plan",name="30 days",days=30,credits=2)
        self.assertEqual(200,self.ack().status_code)
        page=self.reseller.get("/reseller/vpn").text
        self.assertIn("Tarif für Gerät buchen",page)
        res=self.post("activate",client=self.reseller,device_row_id="1",plan="1:30:2")
        self.assertEqual(303,res.status_code)
        with core.db() as con:
            spent=con.execute("SELECT COALESCE(SUM(amount),0) FROM vpn_credits WHERE reseller_id=1").fetchone()[0]
            self.assertEqual(2,spent)
        self.enroll(1)
        self.ack()
        self.assertEqual("READY",self.guest.get("/v1/device/vpn/status",headers=self.auth(1)).json["status"])

    def test_ip_pool_skips_existing_unmanaged_finland_peers(self):
        self.assertEqual(200,self.guest.post("/v1/vpn-agent/applied",headers=self.agent,
            json={"peers":[],"server_public_key":SERVER_KEY,
                  "unmanaged_networks":["10.92.0.2/32","10.92.0.90/32"]}).status_code)
        self.post("grant",device_row_id="1",days="7")
        res=self.enroll(1)
        self.assertEqual("WAITING_FOR_SERVER",res.json["status"])
        with core.db() as con:
            address=con.execute("SELECT client_address FROM vpn_devices WHERE device_row_id=1").fetchone()[0]
        self.assertEqual("10.92.0.3/32",address)

    def test_other_reseller_cannot_claim_another_device(self):
        self.assertEqual(303,self.post("grant",client=self.admin,device_row_id="1",days="7").status_code)
        self.assertEqual(404,self.post("activate",client=self.reseller,device_row_id="2",plan="1:30:1").status_code)
        self.assertEqual(403,self.enroll(1,device="stable-device-2").status_code)

    def test_revocation_is_not_turned_into_direct_fallback(self):
        self.post("grant",device_row_id="1",days="7")
        self.enroll(1)
        self.ack()
        self.assertEqual("READY",self.guest.get("/v1/device/vpn/status",headers=self.auth(1)).json["status"])
        self.post("suspend",device_row_id="1")
        self.assertNotEqual("READY",self.guest.get("/v1/device/vpn/status",headers=self.auth(1)).json["status"])
        self.assertFalse(self.guest.get("/v1/device/vpn/status",headers=self.auth(1)).json["enabled"])
        with core.db() as con:
            con.execute("UPDATE devices SET enabled=0 WHERE id=1")
        self.assertEqual(401,self.guest.get("/v1/device/vpn/status",headers=self.auth(1)).status_code)

if __name__=="__main__":unittest.main()
