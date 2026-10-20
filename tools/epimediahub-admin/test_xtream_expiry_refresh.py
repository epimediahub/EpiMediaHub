"""Offline fixtures only; no production contacts or credentials."""
from datetime import date,datetime,timezone
import json
from pathlib import Path
import socket
import sqlite3
import tempfile
import unittest
from unittest import mock

from xtream_expiry_refresh import (
    ProbeError,read_accounts,parse_endpoint,resolve_public,
    probe,secure_fetch
)


class XtreamLiveProbeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/"accounts.sqlite"
        with sqlite3.connect(self.path) as db:
            db.executescript("""
                CREATE TABLE customers(id INTEGER PRIMARY KEY,enabled INTEGER);
                CREATE TABLE customer_playlists(
                    id INTEGER PRIMARY KEY,customer_id INTEGER,enabled INTEGER,
                    config_json TEXT);
                INSERT INTO customers VALUES(1,1),(2,0);
            """)
            for ident,kind,owner in [
                (1,"XTREAM",1),(2,"XTREAM",1),(3,"M3U",1),
                (4,"XTREAM",2)]:
                config={
                    "playlist_type":kind,
                    "xtream_server":"https://provider.example",
                    "xtream_username":"PRIVATE_USER_"+str(ident),
                    "xtream_password":"PRIVATE_PASSWORD_"+str(ident),
                    "playlist_name":"SECRET_NAME",
                }
                db.execute("INSERT INTO customer_playlists VALUES(?,?,1,?)",
                           (ident,owner,json.dumps(config)))
        self.now=datetime(2026,10,20,16,0,tzinfo=timezone.utc)

    def tearDown(self):
        self.temp.cleanup()

    def test_only_enabled_xtream_accounts_and_no_customer_names(self):
        accounts=read_accounts(self.path)
        self.assertEqual([x[0] for x in accounts],[1,2])
        self.assertNotIn("SECRET_NAME",repr(accounts))
        self.assertEqual(accounts[0][1][0],"https://provider.example")

    def test_confirmed_expiry_is_tied_to_exact_account_id(self):
        calls=[]
        def fake(server,username,password):
            self.assertEqual(server,"https://provider.example")
            self.assertTrue(password.startswith("PRIVATE_PASSWORD_"))
            calls.append(username)
            return {"user_info":{
                "username":username,"exp_date":"1792531200"}}
        summary,rows=probe(self.path,fetch=fake,now=self.now)
        self.assertEqual(summary["active_xtream_accounts"],2)
        self.assertTrue(summary["all_confirmed"])
        self.assertEqual([p for p,_,_ in rows],[1,2])
        self.assertEqual(len(calls),2)
        self.assertNotIn("PRIVATE_PASSWORD",json.dumps(summary))
        self.assertNotIn("PRIVATE_USER",json.dumps(summary))

    def test_missing_or_unlimited_account_blocks_complete_refresh(self):
        def fake(server,username,password):
            return {"user_info":{
                "username":username,
                "exp_date": "0" if username.endswith("2") else "1792531200"}}
        summary,rows=probe(self.path,fetch=fake,now=self.now)
        self.assertFalse(summary["all_confirmed"])
        self.assertEqual(summary["confirmed"],1)
        self.assertEqual(summary["result_counts"]["provider_date_unknown"],1)
        self.assertEqual(len(rows),1)

    def test_https_only_and_no_hidden_urls_credentials_or_ports(self):
        for endpoint in (
            "http://provider.example",
            "https://provider.example:8080",
            "https://user:password@provider.example",
            "https://provider.example/?token=PRIVATE",
            "https://provider.example/#fragment",
            "https://provider.example/%2fsecret",
            "https://provider.example/a/../../x",
            "https://127.0.0.1",
            "https://provider.example\n"
        ):
            if endpoint=="https://127.0.0.1":
                # Public-address guard applies after URL parsing.
                with mock.patch("xtream_expiry_refresh.socket.getaddrinfo",
                     return_value=[(socket.AF_INET,socket.SOCK_STREAM,6,"",("127.0.0.1",443))]):
                    with self.assertRaises(ProbeError):
                        resolve_public("127.0.0.1",443)
            else:
                with self.assertRaises(ProbeError, msg=endpoint):
                    parse_endpoint(endpoint)
        self.assertEqual(parse_endpoint("https://provider.example/a"),
                         ("provider.example",443,"/a"))

    def test_dns_mixed_public_private_is_rejected(self):
        answer=[
            (socket.AF_INET,socket.SOCK_STREAM,6,"",("8.8.8.8",443)),
            (socket.AF_INET,socket.SOCK_STREAM,6,"",("169.254.169.254",443))]
        with mock.patch("xtream_expiry_refresh.socket.getaddrinfo",
                        return_value=answer):
            with self.assertRaises(ProbeError):
                resolve_public("provider.example",443)

    def test_invalid_type_or_config_never_triggers_provider_call(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE customer_playlists SET config_json=? WHERE id=1",
                       (json.dumps({"playlist_type":"XTREAM","type":"M3U"}),))
        with self.assertRaises(ProbeError):
            probe(self.path,fetch=mock.Mock())

    def test_one_provider_network_error_does_not_leak_secrets(self):
        def fake(server,username,password):
            if username.endswith("2"):
                raise OSError("SECRET_PROVIDER_URL_PASSWORD")
            return {"user_info":{"username":username,"exp_date":"1792531200"}}
        result,rows=probe(self.path,fetch=fake,now=self.now)
        self.assertFalse(result["all_confirmed"])
        self.assertEqual(result["result_counts"]["provider_error"],1)
        self.assertNotIn("SECRET_PROVIDER",json.dumps(result))
        self.assertEqual(len(rows),1)

    def test_provider_transport_verifies_account_name_before_accepting(self):
        # Verify with a mock TLS socket not an actual Internet request.
        class Response:
            status=200
            def read(self,n):
                return b'{"user_info":{"username":"other","exp_date":"1792531200"}}'
        fake_conn=mock.Mock()
        fake_conn.getresponse.return_value=Response()
        with mock.patch("xtream_expiry_refresh.resolve_public",
                        return_value=(socket.AF_INET,"8.8.8.8")), \
             mock.patch("xtream_expiry_refresh.socket.socket"), \
             mock.patch("xtream_expiry_refresh.ssl.create_default_context"), \
             mock.patch("xtream_expiry_refresh.http.client.HTTPConnection",
                        return_value=fake_conn):
            with self.assertRaisesRegex(ProbeError,"provider_account_mismatch"):
                secure_fetch("https://provider.example","USER","PASSWORD")
            self.assertTrue(fake_conn.close.called)


if __name__=="__main__":
    unittest.main()
