"""Redacted EpiScene local worker launch diagnostics tests."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location(
    "inspect_local_worker_launch",Path(__file__).with_name("inspect_local_worker_launch.py"))
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class SafeLaunchInventory(unittest.TestCase):
    def test_only_reports_allowed_bind_peer_modes(self):
        raw="path=/usr/bin/python ; argv[]=/usr/bin/python -m skip_remote_worker --bind 127.0.0.1 --peer 127.0.0.1 --port 8790 ; secret=NEVER_EXPORT"
        result=mod.flags(raw,"10.87.26.1","10.87.26.2")
        self.assertEqual(result["bind_option"],"loopback")
        self.assertEqual(result["peer_option"],"loopback")
        self.assertTrue(result["port_is_8790"])
        self.assertNotIn("NEVER_EXPORT",str(result))
        self.assertNotIn("10.87.26.2",str(result))

    def test_known_private_peer_labels(self):
        result=mod.flags("--bind 10.87.26.1 --peer 10.87.26.2 --port=8790",
                          "10.87.26.1","10.87.26.2")
        self.assertEqual(result["bind_option"],"configured_worker_ip")
        self.assertEqual(result["peer_option"],"configured_client_ip")

    def test_ast_ignores_environment_values_and_unknown_text(self):
        with tempfile.TemporaryDirectory() as t:
            path=Path(t)/"skip_remote_client.py"
            path.write_text("import os\nSERVER_IP='secret-do-not-print'\n"
                            "value=os.getenv('EPISCENE_REMOTE_BIND', 'some-secret')\n")
            x=mod.source_summary(path)
            self.assertEqual(x["state"],"parsed")
            self.assertEqual(x["environment_override_variable_names"],["EPISCENE_REMOTE_BIND"])
            self.assertNotIn("secret-do-not-print",str(x))
            self.assertNotIn("some-secret",str(x))

    def test_cannot_query_other_systemd_properties(self):
        with self.assertRaisesRegex(ValueError,"INVALID_PROPERTY"):
            mod.show("EnvironmentCredential")

    def test_no_symlink_file_read(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t)/"client.py"
            p.write_text("SERVER_IP=1")
            link=Path(t)/"link.py"
            link.symlink_to(p)
            self.assertEqual(mod.source_summary(link)["state"],"unavailable")


if __name__=="__main__":
    unittest.main()
