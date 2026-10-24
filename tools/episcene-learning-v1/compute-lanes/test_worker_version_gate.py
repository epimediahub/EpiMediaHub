"""Worker compatibility gate tests; all files and services are synthetic."""
from pathlib import Path
import hashlib
import importlib.util
import tempfile
import unittest
from unittest.mock import patch

MOD = Path(__file__).with_name("worker_version_gate.py")
spec = importlib.util.spec_from_file_location("worker_version_gate", MOD)
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class FakeProcess:
    def __init__(self, out="active"):
        self.stdout = out
        self.returncode = 0


class WorkerVersionGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.components = {}
        for role in gate.CORE:
            script = self.root / (role + ".py")
            script.write_text("def run():\n    return 42\n", encoding="utf-8")
            self.components[role] = {
                "path": str(script),
                "sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
            }
        self.manifest = {
            "schema": 1,
            "integration_test_run": "synthetic-qa-1",
            "components": self.components,
            "services": ["test-episcene-analysis.service"],
        }

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_hash_and_active_service_pass(self):
        with patch.object(gate, "ALLOWED", (self.root,)):
            value = gate.verify(self.manifest, executor=lambda *a, **k: FakeProcess())
        self.assertTrue(value["compatible_for_considered_rollout"])
        self.assertEqual(value["production_writes"], 0)

    def test_single_mismatched_worker_blocks_rollout(self):
        (self.root / "scene.py").write_text("def run():\n    return 43\n")
        with patch.object(gate, "ALLOWED", (self.root,)):
            value = gate.verify(self.manifest, executor=lambda *a, **k: FakeProcess())
        self.assertFalse(value["compatible_for_considered_rollout"])
        self.assertEqual(value["components"]["scene"]["status"], "DRIFT")

    def test_inactive_service_blocks_rollout(self):
        with patch.object(gate, "ALLOWED", (self.root,)):
            value = gate.verify(self.manifest, executor=lambda *a, **k: FakeProcess("inactive"))
        self.assertFalse(value["compatible_for_considered_rollout"])

    def test_missing_component_blocks_rollout(self):
        del self.manifest["components"]["analysis_worker"]
        with patch.object(gate, "ALLOWED", (self.root,)):
            with self.assertRaises(ValueError):
                gate.verify(self.manifest, executor=lambda *a, **k: FakeProcess())

    def test_symlink_is_rejected(self):
        target = self.root / "scene.py"
        target.unlink()
        target.symlink_to(self.root / "scheduler.py")
        with patch.object(gate, "ALLOWED", (self.root,)):
            value = gate.verify(self.manifest, executor=lambda *a, **k: FakeProcess())
        self.assertFalse(value["compatible_for_considered_rollout"])

    def test_manifest_cannot_scan_outside_known_deployment_roots(self):
        with self.assertRaises(ValueError):
            gate.validate_manifest(self.manifest)


if __name__ == "__main__":
    unittest.main()
