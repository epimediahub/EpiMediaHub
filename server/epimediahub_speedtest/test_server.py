"""Local-only integration tests: never require real servers, DNS, or GitHub secrets."""
import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from server import MAX_TRANSFER, ONE_MIB, Server, State


class SpeedtestServiceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="epi-speedtest-")
        cls.payload = Path(cls.temp.name) / "payload"
        with cls.payload.open("wb") as file:
            file.truncate(128 * ONE_MIB)  # sparse, ~zero actual disk
        cls.server = Server("127.0.0.1", 0, State(cls.payload))
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(3)
        cls.temp.cleanup()

    def request(self, method, route, body=None, headers=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, route, body=body, headers=headers or {})
            response = conn.getresponse()
            status = response.status
            data = response.read()
            return status, data
        finally:
            conn.close()

    def session(self):
        code, raw = self.request("POST", "/v1/session", b"")
        self.assertEqual(200, code)
        return json.loads(raw)["session"]

    def test_health_and_nonexistent_path(self):
        code, raw = self.request("GET", "/v1/health")
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(raw)["status"], "ok")
        code, _ = self.request("GET", "/admin")
        self.assertEqual(code, 404)

    def test_rejects_unauthenticated_stream(self):
        code, _ = self.request("GET", "/v1/down?bytes=8192&stream=0")
        self.assertEqual(code, 403)

    def test_real_download_upload_and_four_distinct_stream_offsets(self):
        token = self.session()
        auth = {"Authorization": "Bearer " + token}
        for stream in range(4):
            code, raw = self.request("GET", f"/v1/down?bytes=262144&stream={stream}",
                                     headers=auth)
            self.assertEqual(200, code)
            self.assertEqual(262144, len(raw))
        payload = b"X" * (256 * 1024)
        code, raw = self.request("POST", "/v1/up", payload, auth)
        self.assertEqual(200, code)
        self.assertEqual(json.loads(raw)["received"], len(payload))

    def test_bounds_and_token_rejected_for_wrong_ip(self):
        token = self.session()
        auth = {"Authorization": "Bearer " + token}
        code, _ = self.request("GET", f"/v1/down?bytes={MAX_TRANSFER+1}&stream=0",
                                headers=auth)
        self.assertEqual(400, code)
        code, _ = self.request("GET", "/v1/down?bytes=8192&stream=4", headers=auth)
        self.assertEqual(400, code)
        headers = dict(auth, **{"X-Client-IP": "192.0.2.99"})
        code, _ = self.request("GET", "/v1/down?bytes=8192&stream=0", headers=headers)
        self.assertEqual(403, code)

    def test_fail_closed_after_session_budget(self):
        token = self.session()
        auth = {"Authorization": "Bearer " + token}
        # Test quota enforcement without transferring hundreds of MB.
        cls_state = self.server.state
        with cls_state.lock:
            cls_state.sessions[token]["download"] = 175 * ONE_MIB
        code, _ = self.request("GET", "/v1/down?bytes=2097152&stream=0", headers=auth)
        self.assertEqual(403, code)

    def test_rate_limit_for_sessions_is_enforced(self):
        ip = "198.51.100.25"
        for _ in range(6):
            code, _ = self.request("POST", "/v1/session", b"", {"X-Client-IP": ip})
            self.assertEqual(200, code)
        code, data = self.request("POST", "/v1/session", b"", {"X-Client-IP": ip})
        self.assertEqual(429, code)
        self.assertTrue(json.loads(data)["error"])

if __name__ == "__main__":
    unittest.main()
