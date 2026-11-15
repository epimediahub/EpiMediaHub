"""Synthetic tests for protected EpiScene worker contract/capacity inventory."""
import hashlib
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location(
    "preflight_worker_cpu_contracts",
    Path(__file__).with_name("preflight_worker_cpu_contracts.py"))
audit=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class Dummy:
    stdout="active\n"


class PreflightWorkerCpuTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        root=Path(self.temp.name)
        self.path=root/"worker.py"
        self.path.write_text("def select_job(job):\n    return job\n")
        self.db=root/"prod.db"
        with sqlite3.connect(self.db) as db:
            db.executescript("""
                CREATE TABLE skip_jobs(id INTEGER,asset_key TEXT,status TEXT);
                CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER);
                INSERT INTO skip_assets VALUES ('a',8),('b',10),('customer',42);
                INSERT INTO skip_jobs VALUES
                  (1,'a','running'),(2,'a','queued'),(3,'b','done'),
                  (4,'customer','queued'),(5,'a','private_status_do_not_print');
            """)

    def tearDown(self):
        self.temp.cleanup()

    def test_known_ast_shape_and_code_fingerprint(self):
        src=self.path.read_bytes()
        import ast
        ast_name=next(n for n in ast.walk(ast.parse(src.decode()))
                      if isinstance(n,ast.FunctionDef))
        shape=hashlib.sha256(ast.dump(ast_name,include_attributes=False).encode()).hexdigest()[:16]
        expected=hashlib.sha256(src).hexdigest()[:16]
        result=audit.file_contract(self.path,expected,{"select_job":{shape}})
        self.assertTrue(result["known_function_contracts_match"])
        self.assertTrue(result["baseline_sha16_match"])
        self.assertNotIn("return job",str(result))

    def test_function_revision_drift_is_flagged(self):
        result=audit.file_contract(self.path,"0"*16,{"select_job":{"f"*16}})
        self.assertFalse(result["known_function_contracts_match"])
        self.assertFalse(result["baseline_sha16_match"])

    def test_unexpected_symlink_rejected(self):
        alias=self.path.parent/"symlink.py"
        alias.symlink_to(self.path)
        self.assertEqual(audit.file_contract(alias)["state"],"unavailable")

    def test_aggregate_only_analysis_jobs(self):
        before=self.db.read_bytes()
        result=audit.job_counts(self.db)
        self.assertEqual(result["state"],"ok")
        self.assertEqual(result["playlist_job_status_totals"]["8"]["queued"],1)
        self.assertEqual(result["playlist_job_status_totals"]["10"]["done"],1)
        self.assertEqual(result["playlist_job_status_totals"]["8"]["other"],1)
        self.assertNotIn("private_status_do_not_print",str(result))
        self.assertNotIn("customer",str(result))
        self.assertEqual(self.db.read_bytes(),before)

    def test_service_names_are_fixed_and_errors_not_exposed(self):
        result=audit.service_status("epimediahub-analysis-worker.service",
                                   run=lambda *args,**kwargs:Dummy())
        self.assertEqual(result,"active")

    def test_no_new_worker_authorized(self):
        with patch.object(audit,"host_resources",return_value={
                "cpu_cores":4,
                "additional_offline_workers_safe_to_activate_without_benchmark":0}):
            with patch.object(audit,"service_status",return_value="active"):
                report=audit.collect(files={"scheduler":self.path},services=(),database=self.db)
        self.assertFalse(report["safe_to_enable_new_scheduler_hooks"])
        self.assertEqual(report["new_provider_connections"],0)
        self.assertEqual(report["worker_restarts"],0)
        self.assertEqual(report["database_writes"],0)

    def test_missing_database_does_not_create_file(self):
        missing=self.path.parent/"missing.sqlite3"
        self.assertEqual(audit.job_counts(missing)["state"],"unavailable")
        self.assertFalse(missing.exists())


if __name__=="__main__":
    unittest.main()
