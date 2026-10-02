"""Real HTTP redirects and audio decoding with public-DNS fixture identities."""
from __future__ import annotations

import array
import contextlib
import ctypes.util
import errno
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import math
from pathlib import Path
import shutil
import socket
import ssl
import sys
import threading
import types
import unittest
from unittest import mock
import urllib.error
import urllib.request
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import skip_analysis as analysis


class ProviderRedirectTest(unittest.TestCase):
    def setUp(self):
        self.connections = []
        self.requests = []
        samples = array.array("h")
        rate = 11025
        for i in range(40 * rate):
            t = i / rate
            frequency = 180 + 17 * int(t) % 490
            samples.append(int(9000 * math.sin(2 * math.pi * frequency * t)))
        body = io.BytesIO()
        with wave.open(body, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(samples.tobytes())
        self.audio = body.getvalue()
        fixture = self

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_HEAD(self):
                self.respond(False)

            def do_GET(self):
                self.respond(True)

            def respond(self, send_body):
                fixture.requests.append((self.headers.get("Host"), self.path,
                                         dict(self.headers)))
                if self.path.startswith("/start"):
                    self.send_response(302)
                    self.send_header("Location", f"http://cdn.test:{fixture.cdn.server_port}/audio")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path.startswith("/private"):
                    self.send_response(302)
                    self.send_header("Location", f"http://private.test:{fixture.cdn.server_port}/audio")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path.startswith("/loop"):
                    self.send_response(302)
                    self.send_header("Location", f"http://cdn.test:{fixture.cdn.server_port}/loop")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                if self.path.startswith("/forbidden"):
                    self.send_error(403)
                    return
                start, end = 0, len(fixture.audio) - 1
                requested = self.headers.get("Range")
                if requested:
                    lower, upper = requested.removeprefix("bytes=").split("-")
                    start = int(lower)
                    end = min(int(upper) if upper else end, end)
                if start > end:
                    self.send_error(416)
                    return
                self.send_response(206 if requested else 200)
                self.send_header("Content-Length", str(end - start + 1))
                self.send_header("Accept-Ranges", "bytes")
                if requested:
                    self.send_header("Content-Range", f"bytes {start}-{end}/{len(fixture.audio)}")
                self.end_headers()
                if send_body:
                    try:
                        self.wfile.write(fixture.audio[start:end + 1])
                    except (BrokenPipeError, ConnectionResetError):
                        pass

        self.origin = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        self.cdn = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        self.threads = []
        for server in (self.origin, self.cdn):
            server.daemon_threads = True
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            self.threads.append(thread)
        self.url = f"http://origin.test:{self.origin.server_port}"
        real_dns = socket.getaddrinfo

        def fixture_dns(host, port, *args, **kwargs):
            addresses = {"origin.test": "93.184.216.34", "cdn.test": "93.184.216.35",
                         "private.test": "127.0.0.1"}
            if host in addresses:
                return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                         (addresses[host], port))]
            return real_dns(host, port, *args, **kwargs)

        def fixture_pin(cls, host, address, **kwargs):
            fixture.connections.append((host, address))
            connection = cls(host, **kwargs)
            connection._create_connection = (
                lambda target, timeout=None, source_address=None:
                socket.create_connection(("127.0.0.1", target[1]), timeout, source_address))
            return connection

        self.dns = mock.patch.object(analysis.socket, "getaddrinfo", fixture_dns)
        self.pin = mock.patch.object(analysis, "pinned_connection", fixture_pin)
        self.dns.start()
        self.pin.start()
        self.client = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.pin.stop()
        self.dns.stop()
        for server, thread in zip((self.origin, self.cdn), self.threads):
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def fetch(self, path, headers=None):
        with analysis.provider_proxy(self.url + path) as source:
            try:
                with self.client.open(urllib.request.Request(source, headers=headers or {}),
                                      timeout=5) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError:
                # This is the error the installed decoder passes to provider_proxy.
                raise ValueError("analysis_failed") from None

    def test_public_host_redirect_and_range_work(self):
        status, data = self.fetch("/start", {"Range": "bytes=12-45"})
        self.assertEqual(status, 206)
        self.assertEqual(data, self.audio[12:46])
        self.assertTrue(any("cdn.test" in host for host, _ in self.connections))
        cdn_headers = [headers for host, _, headers in self.requests
                       if host.startswith("cdn.test")][-1]
        self.assertEqual(cdn_headers["Range"], "bytes=12-45")

    @unittest.skipUnless(shutil.which("ffmpeg") and ctypes.util.find_library("chromaprint"),
                         "FFmpeg and Chromaprint required")
    def test_real_audio_probe_and_fingerprint_follow_redirect(self):
        with analysis.provider_proxy(self.url + "/start") as source:
            duration, _ = analysis.probe(source)
            words, step = analysis.fingerprint(source, 7000, 28000)
        self.assertEqual(duration, 40_000)
        self.assertGreater(len(words), 40)
        self.assertGreater(step, 0)

    def test_private_redirect_is_rejected_before_connection(self):
        with self.assertRaisesRegex(ValueError, "^unsafe_source$"):
            self.fetch("/private")
        self.assertFalse(any("private.test" in host for host, _ in self.connections))

    def test_redirect_loop_has_three_hop_limit(self):
        with self.assertRaisesRegex(ValueError, "^redirect_limit$"):
            self.fetch("/loop")
        self.assertLessEqual(len(self.connections), analysis.MAX_PROVIDER_REDIRECTS + 1)

    def test_http_failure_keeps_safe_category(self):
        with self.assertRaisesRegex(ValueError, "^provider_http_403$"):
            self.fetch("/forbidden")

    def test_private_multicast_mixed_dns_and_credentials_are_rejected(self):
        for addresses in (["127.0.0.1"], ["10.0.0.1"], ["169.254.169.254"],
                          ["100.64.0.1"], ["224.0.0.1"], ["::1"],
                          ["93.184.216.34", "192.168.1.1"],
                          ["93.184.216.34", "fd00::1"]):
            with self.subTest(addresses=addresses):
                answer = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                           (ip, 443)) for ip in addresses]
                with mock.patch.object(analysis.socket, "getaddrinfo", return_value=answer):
                    with self.assertRaisesRegex(ValueError, "^unsafe_source$"):
                        analysis.public_address("https://cdn.test/file", "cdn.test")
        for url in ("file:///etc/passwd", "ftp://cdn.test/file",
                    "https://name:password@cdn.test/file"):
            with self.assertRaises(ValueError):
                analysis.public_address(url, "cdn.test")

    def test_each_connection_revalidates_dns(self):
        def rebound(host, port, *_, **__):
            calls[0] += 1
            address = "93.184.216.34" if calls[0] == 1 else "127.0.0.1"
            return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                     (address, port))]
        calls = [0]
        # Only upstream lookups change; the local client still resolves normally.
        existing = analysis.socket.getaddrinfo
        def dns(host, port, *args, **kwargs):
            return rebound(host, port) if host == "origin.test" else existing(host, port, *args, **kwargs)
        with mock.patch.object(analysis.socket, "getaddrinfo", dns):
            with self.assertRaisesRegex(ValueError, "^unsafe_source$"):
                self.fetch("/audio")
        self.assertEqual(self.connections, [])

    def test_head_and_safe_headers_are_preserved_without_credentials(self):
        req = urllib.request.Request(self.url + "/start", method="HEAD", headers={
            "Range": "bytes=0-", "User-Agent": "fixture", "Accept-Encoding": "identity",
            "Authorization": "TEST_SECRET", "Cookie": "TEST_SECRET",
            "Referer": "https://origin.test/TEST_SECRET", "Host": "origin.test"})
        redirected = analysis.ProviderRedirect().redirect_request(
            req, None, 302, "", {}, f"http://cdn.test:{self.cdn.server_port}/audio")
        self.assertEqual(redirected.get_method(), "HEAD")
        forwarded = {key.lower(): value for key, value in redirected.header_items()}
        self.assertEqual(set(forwarded), {"range", "user-agent", "accept-encoding"})
        self.assertNotIn("TEST_SECRET", repr(forwarded))

    def test_https_downgrade_is_rejected(self):
        req = urllib.request.Request("https://origin.test/file")
        with self.assertRaisesRegex(ValueError, "^redirect_downgrade$"):
            analysis.ProviderRedirect().redirect_request(
                req, None, 302, "", {}, f"http://cdn.test:{self.cdn.server_port}/audio")

    def test_redirect_response_body_is_closed_without_reading(self):
        req = urllib.request.Request(self.url + "/start")
        req.timeout = 5
        response = mock.Mock()
        response.read.side_effect = AssertionError("Unbounded redirect-body read")
        handler = analysis.ProviderRedirect()
        handler.parent = mock.Mock()
        handler.http_error_302(req, response, 302, "",
                              {"Location": f"http://cdn.test:{self.cdn.server_port}/audio"})
        response.read.assert_not_called()
        response.close.assert_called_once()
        handler.parent.open.assert_called_once()


class PinnedConnectionTest(unittest.TestCase):
    def test_public_dns_keeps_all_validated_addresses_and_prefers_ipv4(self):
        answer = [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                   ("2001:4860:4860::8888", 443, 0, 0)),
                  (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                   ("3.4.5.6", 443)),
                  (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                   ("3.4.5.7", 443))]
        with mock.patch.object(analysis.socket, "getaddrinfo", return_value=answer):
            _, addresses = analysis.public_address("https://cdn.test/file", "cdn.test")
        self.assertEqual(addresses, ("3.4.5.6", "2001:4860:4860::8888", "3.4.5.7"))

    def test_failed_cdn_address_uses_the_next_pinned_address(self):
        connection = analysis.pinned_connection(http.client.HTTPSConnection, "cdn.test",
                                                ("93.184.216.34", "93.184.216.35"))
        good_socket = mock.Mock()
        with mock.patch.object(analysis.socket, "create_connection", side_effect=[
                ConnectionRefusedError(errno.ECONNREFUSED, "unavailable CDN node"), good_socket]) as connect:
            self.assertIs(connection._create_connection(("cdn.test", 443), 5), good_socket)
        self.assertEqual([c.args[0] for c in connect.call_args_list],
                         [("93.184.216.34", 443), ("93.184.216.35", 443)])
        self.assertEqual(connection.host, "cdn.test")
        self.assertTrue(connection._context.check_hostname)

    def test_missing_ipv6_route_can_fall_back_to_ipv4(self):
        connection = analysis.pinned_connection(http.client.HTTPConnection, "cdn.test",
                                                ("2001:4860:4860::8888", "93.184.216.34"))
        good_socket = mock.Mock()
        with mock.patch.object(analysis.socket, "create_connection", side_effect=[
                OSError(errno.ENETUNREACH, "no IPv6 route"), good_socket]) as connect:
            self.assertIs(connection._create_connection(("cdn.test", 80), 5), good_socket)
        self.assertEqual(connect.call_args_list[-1].args[0], ("93.184.216.34", 80))

    def test_ipv6_only_public_source_remains_supported(self):
        answer = [(socket.AF_INET6, socket.SOCK_STREAM, socket.IPPROTO_TCP, "",
                   ("2001:4860:4860::8888", 443, 0, 0))]
        with mock.patch.object(analysis.socket, "getaddrinfo", return_value=answer):
            _, addresses = analysis.public_address("https://cdn.test/file", "cdn.test")
        connection = analysis.pinned_connection(http.client.HTTPSConnection, "cdn.test", addresses)
        with mock.patch.object(analysis.socket, "create_connection") as connect:
            connection._create_connection(("cdn.test", 443), 5)
        self.assertEqual(connect.call_args.args[0], ("2001:4860:4860::8888", 443))

    def test_alternative_connections_share_one_deadline_and_source_binding(self):
        connection = analysis.pinned_connection(http.client.HTTPConnection, "cdn.test",
                                                ("93.184.216.34", "93.184.216.35"))
        good_socket = mock.Mock()
        with mock.patch.object(analysis.time, "monotonic", side_effect=[100, 100, 103]), \
                mock.patch.object(analysis.socket, "create_connection", side_effect=[
                    ConnectionRefusedError(), good_socket]) as connect:
            self.assertIs(connection._create_connection(("cdn.test", 80), 5, ("0.0.0.0", 0)), good_socket)
        self.assertEqual([c.args[1] for c in connect.call_args_list], [2.5, 2])
        self.assertEqual(connect.call_args.args[2], ("0.0.0.0", 0))

    def test_a_tcp_timeout_leaves_time_for_the_next_address(self):
        connection = analysis.pinned_connection(http.client.HTTPConnection, "cdn.test",
                                                ("93.184.216.34", "93.184.216.35"))
        good_socket = mock.Mock()
        with mock.patch.object(analysis.time, "monotonic", side_effect=[100, 100, 102.5]), \
                mock.patch.object(analysis.socket, "create_connection", side_effect=[
                    TimeoutError(), good_socket]) as connect:
            self.assertIs(connection._create_connection(("cdn.test", 80), 5), good_socket)
        self.assertEqual([c.args[1] for c in connect.call_args_list], [2.5, 2.5])

    def test_expired_deadline_does_not_start_another_connection(self):
        connection = analysis.pinned_connection(http.client.HTTPConnection, "cdn.test",
                                                ("93.184.216.34", "93.184.216.35"))
        with mock.patch.object(analysis.time, "monotonic", side_effect=[100, 100, 105]), \
                mock.patch.object(analysis.socket, "create_connection", side_effect=TimeoutError()) as connect:
            with self.assertRaises(TimeoutError):
                connection._create_connection(("cdn.test", 80), 5)
        self.assertEqual(connect.call_count, 1)

    def test_exhausted_pinned_addresses_do_not_resolve_the_host_again(self):
        connection = analysis.pinned_connection(http.client.HTTPConnection, "cdn.test",
                                                ("93.184.216.34", "93.184.216.35"))
        error = OSError(errno.ENETUNREACH, "no route")
        with mock.patch.object(analysis.socket, "create_connection", side_effect=error) as connect, \
                mock.patch.object(analysis.socket, "getaddrinfo") as resolve:
            with self.assertRaises(OSError) as caught:
                connection._create_connection(("cdn.test", 80), 5)
        self.assertIs(caught.exception, error)
        self.assertEqual(connect.call_count, 2)
        resolve.assert_not_called()

    def test_real_json_request_succeeds_when_the_first_cdn_address_is_unreachable(self):
        requests = []
        body = b'{"type":"tv","tmdb_id":8358}'

        class Provider(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                requests.append(self.headers["Host"])
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = ThreadingHTTPServer(("127.0.0.1", 0), Provider)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        real_dns, real_connect = socket.getaddrinfo, socket.create_connection
        attempts = []

        def dns(host, port, *args, **kwargs):
            if host == "cdn.test":
                return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))
                        for ip in ("93.184.216.34", "93.184.216.35")]
            return real_dns(host, port, *args, **kwargs)

        def connect(target, timeout=None, source_address=None):
            if target[0] == "93.184.216.34":
                attempts.append(target[0])
                raise OSError(errno.ENETUNREACH, "unreachable CDN address")
            if target[0] == "93.184.216.35":
                attempts.append(target[0])
                target = ("127.0.0.1", server.server_port)
            return real_connect(target, timeout, source_address)

        try:
            with mock.patch.object(analysis.socket, "getaddrinfo", side_effect=dns), \
                    mock.patch.object(analysis.socket, "create_connection", side_effect=connect):
                with analysis.provider_proxy(f"http://cdn.test:{server.server_port}/json") as source:
                    client = urllib.request.build_opener(urllib.request.ProxyHandler({}))
                    with client.open(source, timeout=5) as response:
                        self.assertEqual(response.status, 200)
                        self.assertEqual(response.read(), body)
            self.assertEqual(attempts, ["93.184.216.34", "93.184.216.35"])
            self.assertEqual(requests, [f"cdn.test:{server.server_port}"])
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=2)

    def test_connection_uses_validated_ip_and_keeps_tls_hostname(self):
        connection = analysis.pinned_connection(
            http.client.HTTPSConnection, "cdn.test", "93.184.216.35",
            context=ssl.create_default_context())
        with mock.patch.object(analysis.socket, "create_connection") as connect:
            connection._create_connection(("cdn.test", 443), timeout=5)
        self.assertEqual(connect.call_args.args[0], ("93.184.216.35", 443))
        self.assertEqual(connection.host, "cdn.test")
        self.assertTrue(connection._context.check_hostname)
        self.assertEqual(connection._context.verify_mode, ssl.CERT_REQUIRED)

    def test_dashboard_failure_text_never_copies_untrusted_error(self):
        try:
            import flask
        except ModuleNotFoundError:
            flask = types.ModuleType("flask")
            for name in ("abort", "jsonify", "redirect", "render_template", "url_for",
                         "request", "session"):
                setattr(flask, name, None)
            sys.modules["flask"] = flask
        from skip_analysis_worker import failure_detail
        self.assertIn("HTTP 403", failure_detail(ValueError("provider_http_403")))
        self.assertIn("öffentliche HTTP-Quelle", failure_detail(ValueError("unsafe_source")))
        self.assertNotIn("TEST_SECRET", failure_detail(ValueError(
            "https://provider.invalid/TEST_SECRET")))


if __name__ == "__main__":
    unittest.main()
