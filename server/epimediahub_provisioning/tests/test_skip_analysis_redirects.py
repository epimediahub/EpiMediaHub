"""Real HTTP redirects and audio decoding with public-DNS fixture identities."""
from __future__ import annotations

import array
import contextlib
import ctypes.util
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
                          ["93.184.216.34", "192.168.1.1"]):
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
