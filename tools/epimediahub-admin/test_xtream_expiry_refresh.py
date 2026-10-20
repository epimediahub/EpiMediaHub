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
    ProbeError,ProviderHttpError,diagnostic_reason,
    read_accounts,parse_endpoint,resolve_public,
    probe,secure_fetch,check_https_upgrade,_https_upgrade_host,
    https_tls_handshake_only, _plaintext_origin, player_compatible_http_fetch, main
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
        self.assertEqual(summary["result_counts"]["provider_date_undated"],1)
        self.assertEqual(len(rows),1)

    def test_diagnostics_report_only_ordinal_positions_and_safe_statuses(self):
        def fake(server,username,password):
            if username.endswith("1"):
                return {"user_info":{"username":username,"exp_date":"1792531200"}}
            raise ProviderHttpError(403)
        result,dates=probe(self.path,fetch=fake,now=self.now,
                           diagnostics=True)
        self.assertEqual(result["confirmed"],1)
        self.assertEqual(result["result_counts"]["provider_http_4xx"],1)
        self.assertEqual(result["account_checks"],[
            {"position":1,"status":"confirmed"},
            {"position":2,"status":"provider_http_4xx"}])
        self.assertTrue(result["account_positions_are_not_ids"])
        self.assertEqual(len(dates),1)
        serialized=json.dumps(result)
        for secret in ["PRIVATE_USER","PRIVATE_PASSWORD","SECRET_NAME",
                       "provider.example","1792531200"]:
            self.assertNotIn(secret,serialized)

    def test_diagnostic_status_classification_no_raw_provider_text(self):
        self.assertEqual(diagnostic_reason(ProviderHttpError(503)),
                         "provider_http_5xx")
        self.assertEqual(diagnostic_reason(ProviderHttpError(302)),
                         "provider_http_other")
        self.assertEqual(diagnostic_reason(TimeoutError("SECRET")),
                         "provider_timeout")
        self.assertEqual(diagnostic_reason(
            ConnectionRefusedError("SECRET")),"provider_connection_refused")
        self.assertEqual(diagnostic_reason(
            ProbeError("password PRIVATE")),"provider_error")

    def test_diagnose_http_requires_same_explicit_operator_opt_in(self):
        with mock.patch("xtream_expiry_refresh.sys.argv",
                        ["refresh","--diagnose-http"]), \
             mock.patch.dict("xtream_expiry_refresh.os.environ",
                             {"EPIMEDIAHUB_XTREAM_HTTP_PROBE_APPROVED":"NO"}), \
             mock.patch("xtream_expiry_refresh.probe") as run:
            with self.assertRaisesRegex(ProbeError,
                                        "plaintext_http_requires_explicit_operator_approval"):
                main()
            run.assert_not_called()

    def test_http_transport_is_explicit_and_never_automatically_enabled(self):
        with mock.patch("xtream_expiry_refresh.sys.argv",
                        ["refresh","--probe-http"]), \
             mock.patch.dict("xtream_expiry_refresh.os.environ",
                             {"EPIMEDIAHUB_XTREAM_HTTP_PROBE_APPROVED":"NO"}), \
             mock.patch("xtream_expiry_refresh.probe") as run:
            with self.assertRaisesRegex(ProbeError,
                                        "plaintext_http_requires_explicit_operator_approval"):
                main()
            run.assert_not_called()

    def test_http_origin_validation_is_strict(self):
        self.assertEqual(_plaintext_origin("http://provider.example:8080/path"),
                         ("provider.example",8080,"/path"))
        self.assertEqual(_plaintext_origin("http://provider.example"),
                         ("provider.example",80,""))
        for origin in ("https://provider.example",
                       "http://provider.example:25",
                       "http://user:secret@provider.example",
                       "http://provider.example?token=SECRET",
                       "http://provider.example/a/../../b",
                       "http://provider.example/#fragment",
                       "file:///etc/passwd",
                       "http://provider.example:abc"):
            with self.subTest(origin=origin):
                with self.assertRaises(ProbeError):
                    _plaintext_origin(origin)

    def test_http_transport_pins_public_ip_checks_username_and_no_redirects(self):
        class FakeResponse:
            status=200
            def read(self,n):
                return b'{"user_info":{"username":"USER","exp_date":"1792531200"}}'
        conn=mock.MagicMock()
        conn.getresponse.return_value=FakeResponse()
        sock=mock.MagicMock()
        with mock.patch("xtream_expiry_refresh.resolve_public",
                        return_value=(socket.AF_INET,"8.8.8.8")), \
             mock.patch("xtream_expiry_refresh.socket.socket",
                        return_value=sock), \
             mock.patch("xtream_expiry_refresh.http.client.HTTPConnection",
                        return_value=conn):
            value=player_compatible_http_fetch(
                "http://provider.example:8080","USER","PASSWORD")
        self.assertEqual(value["user_info"]["username"],"USER")
        sock.connect.assert_called_once_with(("8.8.8.8",8080))
        conn.request.assert_called_once()
        args,kwargs=conn.request.call_args
        self.assertEqual(args[0],"GET")
        self.assertIn("username=USER",args[1])
        self.assertIn("password=PASSWORD",args[1])
        self.assertNotIn("PASSWORD",repr(value))
        conn.close.assert_called_once()

        conn=mock.MagicMock()
        conn.getresponse.return_value=mock.Mock(status=302)
        with mock.patch("xtream_expiry_refresh.resolve_public",
                        return_value=(socket.AF_INET,"8.8.8.8")), \
             mock.patch("xtream_expiry_refresh.socket.socket"), \
             mock.patch("xtream_expiry_refresh.http.client.HTTPConnection",
                        return_value=conn):
            with self.assertRaisesRegex(ProbeError,"provider_http_error"):
                player_compatible_http_fetch(
                    "http://provider.example","USER","PASSWORD")

    def test_http_transport_rejects_private_destination_before_socket(self):
        with mock.patch("xtream_expiry_refresh.resolve_public",
                        side_effect=ProbeError("non_public_provider_address")), \
             mock.patch("xtream_expiry_refresh.socket.socket") as socket_mock:
            with self.assertRaises(ProbeError):
                player_compatible_http_fetch(
                    "http://provider.example","USER","PASSWORD")
            socket_mock.assert_not_called()

    def test_https_check_deduplicates_origin_and_never_passes_credentials(self):
        with sqlite3.connect(self.path) as db:
            db.execute("UPDATE customer_playlists SET config_json=json_set("
                       "config_json,'$.xtream_server','http://provider.example:8080')"
                       " WHERE id IN (1,2)")
        seen=[]
        def handshake(origin):
            seen.append(origin)
            self.assertEqual(origin,"http://provider.example:8080")
            return True
        summary=check_https_upgrade(self.path,handshake=handshake)
        self.assertEqual(summary["accounts_with_valid_https_tls"],2)
        self.assertEqual(summary["distinct_origins_checked"],1)
        self.assertEqual(seen,["http://provider.example:8080"])
        self.assertEqual(summary["http_requests_sent"],0)
        self.assertFalse(summary["provider_credentials_sent"])
        self.assertFalse(summary["customer_data_written"])
        self.assertNotIn("PRIVATE_PASSWORD",json.dumps(summary))
        self.assertNotIn("SECRET_NAME",json.dumps(summary))

    def test_https_check_rejects_invalid_and_internal_origins(self):
        for url in ("https://user:pass@provider.example",
                    "http://provider.example/?token=secret",
                    "http://provider.example/#key",
                    "file:///etc/passwd",
                    "http://provider.example/../../x",
                    "http://provider.example:abc",
                    "http://provider.example/%2e%2e"):
            with self.subTest(url=url):
                with self.assertRaises(ProbeError):
                    _https_upgrade_host(url)
        self.assertEqual(_https_upgrade_host(
            "http://provider.example:8080/live"),"provider.example")
        with mock.patch("xtream_expiry_refresh.resolve_public",
                        side_effect=ProbeError("non_public_provider_address")), \
             mock.patch("xtream_expiry_refresh.socket.socket") as sock:
            summary=check_https_upgrade(self.path,
                 handshake=https_tls_handshake_only)
            self.assertEqual(summary["result_counts"]["unsafe_or_invalid_origin"],2)
            self.assertFalse(sock.called)

    def test_tls_handshake_sends_no_http_request(self):
        sock=mock.MagicMock()
        tls=mock.MagicMock()
        tls.__enter__.return_value=tls
        ctx=mock.MagicMock()
        ctx.wrap_socket.return_value=tls
        with mock.patch("xtream_expiry_refresh.resolve_public",
                        return_value=(socket.AF_INET,"8.8.8.8")), \
             mock.patch("xtream_expiry_refresh.socket.socket",
                        return_value=sock), \
             mock.patch("xtream_expiry_refresh.ssl.create_default_context",
                        return_value=ctx):
            self.assertTrue(https_tls_handshake_only(
                "http://provider.example:8080"))
        sock.connect.assert_called_once_with(("8.8.8.8",443))
        ctx.wrap_socket.assert_called_once_with(
            sock,server_hostname="provider.example")
        self.assertFalse(tls.send.called)
        self.assertFalse(tls.sendall.called)

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
        self.assertEqual(result["result_counts"]["provider_transport_error"],1)
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
