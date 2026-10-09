import base64
import copy
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from datetime import datetime,timedelta,timezone

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from vpn_finland_agent import Agent, MARKER, seal_config, validate

KEY1=base64.b64encode(bytes(range(32))).decode()
KEY2=base64.b64encode(bytes(range(1,33))).decode()
OTHER=base64.b64encode(bytes(range(2,34))).decode()


class FakeWireGuard:
    def __init__(self):self.peers={KEY1:{"10.92.0.2/32"},OTHER:{"10.92.0.90/32"}};self.calls=[]
    def __call__(self,args,**kwargs):
        self.calls.append(args)
        if args[1:]==["show","wg0","allowed-ips"]:return SimpleNamespace(stdout="\n".join(k+"\t"+(" ".join(v) or "(none)") for k,v in self.peers.items()))
        if args[1:]==["show","wg0","public-key"]:return SimpleNamespace(stdout=KEY2+"\n")
        if args[1:]==["show","wg0","latest-handshakes"]:return SimpleNamespace(stdout="\n".join(k+"\t0" for k in self.peers))
        if args[1:4]==["set","wg0","peer"]:
            self.peers[args[4]]=set(args[6].split(",")) if args[6] else set()
            return SimpleNamespace(stdout="")
        raise AssertionError(args)


class AgentTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.wg=self.root/"wg0.conf"
        self.original=f"[Interface]\nPrivateKey = fixture-private-key\nAddress = 10.92.0.1/24\nSaveConfig = true # existing server setting\n\n[Peer]\nPublicKey = {KEY1}\nPresharedKey = fixture-psk\nAllowedIPs = 10.92.0.2/32\n\n[Peer]\nPublicKey = {OTHER}\nAllowedIPs = 10.92.0.90/32\n"
        self.wg.write_text(self.original)
        self.runner=FakeWireGuard()
        self.config={"dashboard_url":"https://api.epimediahub.com","token":"test-"*10,"state_file":str(self.root/"state.json"),"wireguard_config":str(self.wg)}
        self.agent=Agent(self.config,self.runner)

    def snapshot(self):
        return {"version":1,"node":"finland","server_time":datetime.now(timezone.utc).isoformat(),"lease_seconds":60,"peers":[{"id":1,"public_key":KEY1,"client_address":"10.92.0.2/32","enabled":True,"expires_at":(datetime.now(timezone.utc)+timedelta(days=1)).isoformat(),"generation":"a"*64,"revision":1}]}

    def test_agent_curl_transport_uses_stdin_for_secret_and_json_post(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        response = SimpleNamespace(stdout='{"peers":[]}\n200', returncode=0, stderr="")
        with patch("vpn_finland_agent.subprocess.run", return_value=response) as run:
            body=self.agent.request("/v1/vpn-agent/desired")
        self.assertEqual(body, {"peers":[]})
        args,kwargs=run.call_args
        command=args[0]
        self.assertNotIn(self.config["token"], " ".join(command))
        self.assertIn("--proto", command)
        self.assertIn("=https", command)
        self.assertEqual(command[command.index("--header")+1], "@-")
        self.assertIn("Authorization: Bearer "+self.config["token"]+"\n",kwargs["input"])
        self.assertFalse(kwargs["shell"] if "shell" in kwargs else False)

        with patch("vpn_finland_agent.subprocess.run", return_value=response) as post:
            self.agent.request("/v1/vpn-agent/applied", {"peers":[]})
        args,kwargs=post.call_args
        self.assertIn("--data-binary",args[0])
        self.assertIn("Content-Type: application/json\n",kwargs["input"])
        self.assertNotIn(self.config["token"]," ".join(args[0]))

    def test_agent_curl_transport_rejects_denied_or_redirected_requests(self):
        from unittest.mock import patch
        from urllib.error import HTTPError
        for code in (301,401,403,404):
            with self.subTest(status=code):
                response=SimpleNamespace(stdout='{}\n'+str(code),returncode=0,stderr="")
                with patch("vpn_finland_agent.subprocess.run",return_value=response):
                    with self.assertRaises(HTTPError) as caught:
                        self.agent.request("/v1/vpn-agent/desired")
                self.assertEqual(caught.exception.code, code)
                self.assertNotIn(self.config["token"],str(caught.exception))
        with self.assertRaises(ValueError):
            self.agent.request("/v1/vpn-agent/desired", {"peers":[]})
        with self.assertRaises(ValueError):
            self.agent.request("https://evil.example/", None)

    def test_actual_rules_ack_and_sealed_reboot_config(self):
        report=self.agent.apply(self.snapshot())
        self.assertTrue(report["peers"][0]["enabled"])
        content=self.wg.read_text()
        self.assertNotIn("AllowedIPs = 10.92.0.2/32",content)
        self.assertIn("AllowedIPs = 10.92.0.90/32",content)
        self.assertIn("PresharedKey = fixture-psk",content)
        self.assertIn("PrivateKey = fixture-private-key",content)
        self.assertIn("SaveConfig = false",content)
        self.assertEqual(self.wg.with_name("wg0.conf.before-epimediahub-vpn").read_text(),self.original)
        self.assertEqual(self.wg.stat().st_mode & 0o777,0o600)
        self.agent.close_all()
        self.assertEqual(self.runner.peers[KEY1],set());self.assertEqual(self.runner.peers[OTHER],{"10.92.0.90/32"})

    def test_transfer_disables_old_before_new(self):
        snapshot=self.snapshot();snapshot["peers"][0]["enabled"]=False
        snapshot["peers"].append({**snapshot["peers"][0],"id":2,"public_key":KEY2,"enabled":True,"generation":"b"*64})
        self.agent.apply(snapshot)
        changes=[c for c in self.runner.calls if c[1]=="set"]
        self.assertEqual([(c[4],c[6]) for c in changes],[(KEY1,""),(KEY2,"10.92.0.2/32")])

    def test_expiration_watchdog_and_restart_revoke_owned_peers(self):
        self.agent.apply(self.snapshot())
        self.agent.deadlines[KEY1]=time.monotonic()-1;self.agent.expire()
        self.assertEqual(self.runner.peers[KEY1],set())
        self.agent.apply(self.snapshot())
        replacement=Agent(self.config,self.runner);replacement.close_all()
        self.assertEqual(self.runner.peers[KEY1],set())

    def test_recover_ownership_from_sealed_config(self):
        self.agent.apply(self.snapshot());Path(self.config["state_file"]).unlink()
        replacement=Agent(self.config,self.runner);replacement.close_all()
        self.assertEqual(self.runner.peers[KEY1],set())

    def test_unmanaged_ip_collision_rejected_without_changing_peer(self):
        snapshot=self.snapshot();snapshot["peers"][0]["client_address"]="10.92.0.90/32"
        with self.assertRaises(ValueError):self.agent.apply(snapshot)
        self.assertEqual(self.runner.peers[OTHER],{"10.92.0.90/32"})

    def test_invalid_grants_and_insecure_origin_rejected(self):
        for patch in ({"public_key":";bad"},{"client_address":"0.0.0.0/0"},{"enabled":"true"},{"expires_at":"2000-01-01T00:00:00Z"}):
            snapshot=self.snapshot();snapshot["peers"][0].update(patch)
            with self.assertRaises(ValueError):validate(snapshot,"10.92.0.0/24")
        with self.assertRaises(ValueError):Agent({**self.config,"dashboard_url":"http://api.epimediahub.com"},self.runner)


if __name__=="__main__":unittest.main()
