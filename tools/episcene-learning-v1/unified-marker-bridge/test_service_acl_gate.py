"""Test service-user read-only access gate without privileged system changes."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from patch_live_lookup import preflight


class ServiceAccountACLTests(unittest.TestCase):
    def test_non_root_read_access_probed_in_service_account(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            source = folder/"skip_markers.py"
            source.write_text("# fake source\n")
            (folder/"trusted-sources.sqlite3").write_bytes(b"sqlite-test-dummy")
            calls = []
            def command(*args):
                calls.append(args)
                if args[:5] == ("systemctl","show","-p","User","--value"):
                    return SimpleNamespace(returncode=0,stdout="apiworker\n")
                return SimpleNamespace(returncode=0,stdout="")
            with patch("patch_live_lookup._run",side_effect=command):
                info = preflight(source=source,data=folder)
            self.assertEqual(info["cache_access"], "least_privilege_read_verified")
            self.assertTrue(any(x[:3] == ("runuser","-u","apiworker") for x in calls))
            self.assertFalse(any(x[0] == "setfacl" for x in calls))

    def test_denied_service_access_stops_before_deployment(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            source=folder/"skip_markers.py"
            source.write_text("# fake\n")
            (folder/"trusted-sources.sqlite3").write_bytes(b"sqlite-test")
            def command(*args):
                if args[:5] == ("systemctl","show","-p","User","--value"):
                    return SimpleNamespace(returncode=0,stdout="apiworker\n")
                if args[0]=="runuser":
                    return SimpleNamespace(returncode=1,stdout="")
                return SimpleNamespace(returncode=0,stdout="")
            with patch("patch_live_lookup._run",side_effect=command):
                with self.assertRaisesRegex(ValueError,"cannot read trusted cache"):
                    preflight(source=source,data=folder)

    def test_invalid_service_account_name_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            folder=Path(td)
            source=folder/"skip_markers.py"
            source.write_text("# fake\n")
            (folder/"trusted-sources.sqlite3").write_bytes(b"sqlite-test")
            def command(*args):
                if args[:5] == ("systemctl","show","-p","User","--value"):
                    return SimpleNamespace(returncode=0,stdout="bad;username\n")
                return SimpleNamespace(returncode=0,stdout="")
            with patch("patch_live_lookup._run",side_effect=command):
                with self.assertRaisesRegex(ValueError,"unexpected API service account"):
                    preflight(source=source,data=folder)


if __name__=="__main__":
    unittest.main()
