"""No-host-mutating tests for guarded WAL sync service repair."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import types
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "repair_unified_sqlite_wal", Path(__file__).with_name("repair_unified_sqlite_wal.py"))
fix = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fix)


class GuardTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "bridge.py"
        self.source.write_text("def hello(): return 1")
        self.drop_dir = self.root / "unit.d"
        self.drop_file = self.drop_dir / "90-episcene-sqlite-wal.conf"
        self.props = {
            "User": "root", "ProtectSystem": "strict",
            "ActiveState": "failed",
            "ReadWritePaths": "/var/lib/episcene-learning",
            "ExecStart": ("{ path=/usr/bin/python3 ; argv[]=/usr/bin/python3 "
                          + str(self.source) + " sync-verified "
                          "--production /var/lib/epimediahub/provisioning.db ; }"),
            "FragmentPath": "/etc/systemd/system/episcene-unified-sync.service",
        }
        self.patches = [
            patch.object(fix.os, "geteuid", return_value=0),
            patch.object(fix, "UNIT_SOURCE", self.source),
            patch.object(fix, "PINNED_BRIDGE_SHA256",
                         hashlib.sha256(self.source.read_bytes()).hexdigest()),
            patch.object(fix, "DROPIN_DIR", self.drop_dir),
            patch.object(fix, "DROPIN", self.drop_file),
            patch.object(fix, "WRITE_ROOT", self.root),
        ]
        for p in self.patches:
            p.start()

    def tearDown(self):
        for p in reversed(self.patches):
            p.stop()
        self.tmp.cleanup()

    def test_expected_unit_and_exact_bridge_hash_pass(self):
        self.assertTrue(fix.validate(self.props))

    def test_reject_incompatible_worker_version(self):
        self.source.write_text("def hello(): return 2")
        with self.assertRaisesRegex(fix.Stop, "VERSION_DRIFT"):
            fix.validate(self.props)

    def test_no_mutation_if_service_runs_as_non_root(self):
        self.props["User"] = "epimediahub"
        with self.assertRaisesRegex(fix.Stop, "SERVICE_IDENTITY"):
            fix.validate(self.props)
        self.assertFalse(self.drop_file.exists())

    def test_no_mutation_if_correct_write_access_already_present(self):
        self.props["ReadWritePaths"] += " /var/lib/epimediahub"
        with self.assertRaisesRegex(fix.Stop, "WRITE_PATH_ALREADY_ALLOWED"):
            fix.validate(self.props)

    def test_single_allowlist_dropin_is_the_only_written_change(self):
        created = fix.install_dropin()
        self.assertTrue(created)
        self.assertEqual(self.drop_file.read_text(), fix.CONTENT)
        self.assertNotIn("ExecStart=", fix.CONTENT)
        self.assertNotIn("Restart=", fix.CONTENT)
        # Restoring tests simulate daemon-reload; never call systemctl on CI.
        fake = types.SimpleNamespace(returncode=0)
        with patch.object(fix, "command", return_value=fake):
            self.assertTrue(fix.undo(created))
        self.assertFalse(self.drop_file.exists())

    def test_existing_dropin_never_overwritten(self):
        self.drop_dir.mkdir()
        self.drop_file.write_text("existing")
        with self.assertRaisesRegex(fix.Stop, "EXISTING_DROPIN"):
            fix.validate(self.props)
        self.assertEqual(self.drop_file.read_text(), "existing")

    def test_worker_not_restarted_and_rollback_on_service_failure(self):
        def props(service):
            return {"ActiveState": "active"} if service == fix.WORKER else self.props
        calls = []
        def fake_cmd(*args, **kwargs):
            calls.append(args)
            return types.SimpleNamespace(returncode=1 if "start" in args else 0)
        with patch.object(fix, "properties", side_effect=props), \
             patch.object(fix, "local_db_preflight"), \
             patch.object(fix, "marker_count", return_value=313), \
             patch.object(fix, "command", side_effect=fake_cmd):
            result = fix.run(apply=True)
        self.assertFalse(result["applied"])
        self.assertTrue(result["rolled_back"])
        self.assertEqual(result["stop_reason"], "SYNC_START_FAILED")
        self.assertFalse(self.drop_file.exists())
        starts = [cmd for cmd in calls if "start" in cmd]
        self.assertEqual(starts, [("systemctl", "start", fix.SERVICE)])
        self.assertNotIn(fix.WORKER, " ".join(" ".join(x) for x in starts))


if __name__ == "__main__":
    unittest.main()
