"""Offline tests for EpiScene health-only remote gate, never opens a socket."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location(
 "diagnose_remote_health_gate",Path(__file__).with_name("diagnose_remote_health_gate.py"))
gate=importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FakeResponse:
    status=200
    def __init__(self,raw):self.raw=raw
    def read(self,n):return self.raw


class FakeHTTP:
    def __init__(self,host,port,timeout):self.host=host;self.port=port
    def request(self,method,path,headers):
        if method!="GET" or path!="/health":
            raise AssertionError("MUST_ONLY_GET_WORKER_HEALTH")
    def getresponse(self):
        return FakeResponse(b'{"status":"ok","protocol":"v1","versions":{"scene":"abc","audio":"def"},"capacity":2}')
    def close(self):pass


class RemoteHealthTests(unittest.TestCase):
    def test_one_health_get_without_secret_output(self):
        out=gate.compute_health("10.9.0.2",9999,"v1",{"scene":"abc","audio":"def"},
                                connection_factory=FakeHTTP)
        self.assertTrue(out["versions_match"])
        self.assertTrue(out["protocol_match"])
        self.assertEqual(out["task_capacity"],2)
        self.assertNotIn("10.9.0.2",str(out))
        self.assertNotIn("abc",str(out))
        self.assertNotIn("def",str(out))

    def test_mismatch_reports_component_names_only(self):
        out=gate.compute_health("10.9.0.2",9999,"v1",{"scene":"CHANGED","audio":"def"},
                                connection_factory=FakeHTTP)
        self.assertFalse(out["versions_match"])
        self.assertEqual(out["version_component_name_differences"],["scene"])
        self.assertNotIn("CHANGED",str(out))

    def test_refuse_public_and_invalid_endpoints(self):
        for host in ("8.8.8.8","malicious.com","::ffff:8.8.8.8"):
            out=gate.compute_health(host,9000,"v1",{})
            self.assertEqual(out["result"],"STOP_INVALID_OR_NONPRIVATE_COMPUTE_ENDPOINT")
        self.assertFalse(gate.only_compute_peer("8.8.8.8"))

    def test_network_failures_are_redacted(self):
        class Refused:
            def __init__(self,*args,**kw):
                raise ConnectionRefusedError("token SECRET credential")
        out=gate.compute_health("10.9.0.2",9999,"v1",{},connection_factory=Refused)
        self.assertEqual(out["result"],"CONNECTION_REFUSED")
        self.assertNotIn("SECRET",str(out))

    def test_remote_invalid_json_is_not_exported(self):
        class Bad(FakeHTTP):
            def getresponse(self):return FakeResponse(b'bad-JSON with password=x')
        out=gate.compute_health("10.9.0.2",9999,"v1",{},connection_factory=Bad)
        self.assertEqual(out["result"],"HEALTH_REPLY_UNAVAILABLE")
        self.assertNotIn("password",str(out))

    def test_private_worker_only_and_no_provider_calls(self):
        self.assertTrue(gate.only_compute_peer("10.8.0.2"))
        self.assertTrue(gate.only_compute_peer("100.80.90.9"))
        self.assertFalse(gate.only_compute_peer("8.8.4.4"))
        self.assertEqual(gate.classify_io_error(TimeoutError()),"TIMEOUT")


if __name__=="__main__":
    unittest.main()
