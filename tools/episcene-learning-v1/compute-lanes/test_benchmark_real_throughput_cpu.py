"""Synthetic regression checks for measured EpiScene CPU/throughput pilot."""
import importlib.util
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

SPEC=importlib.util.spec_from_file_location(
    "benchmark_real_throughput_cpu",
    Path(__file__).with_name("benchmark_real_throughput_cpu.py"))
bench=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bench)

class RealCapacityTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.db=Path(self.tmp.name)/"test.sqlite3"
        with sqlite3.connect(self.db) as c:
            c.executescript("""
              CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER);
              CREATE TABLE skip_jobs(asset_key TEXT,status TEXT,attempts INTEGER);
              INSERT INTO skip_assets VALUES('a',8),('b',10),('private-asset',55);
              INSERT INTO skip_jobs VALUES('a','queued',0),('b','done',1),
                ('private-asset','PRIVATE_STATUS',4);
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_aggregate_jobs_protect_private_playlists(self):
        before=self.db.read_bytes()
        result=bench.read_jobs(self.db)
        self.assertEqual(result["8"]["statuses"]["queued"],1)
        self.assertEqual(result["10"]["statuses"]["done"],1)
        self.assertNotIn("private-asset",str(result))
        self.assertNotIn("PRIVATE_STATUS",str(result))
        self.assertEqual(self.db.read_bytes(),before)

    def test_valid_cpu_and_usage_delta(self):
        begin={pid:{"statuses":{},"attempts":0} for pid in ("8","10")}
        end={pid:{"statuses":{},"attempts":0} for pid in ("8","10")}
        begin["10"]["statuses"]={"queued":1,"done":0}
        end["10"]["statuses"]={"queued":0,"done":1}
        end["10"]["attempts"]=1
        units={key:100_000 for key in bench.UNITS}
        next_units={key:1_100_000 for key in bench.UNITS}
        r=bench.calculate(begin,end,(1000,600),(2000,1500),units,next_units,90)
        self.assertEqual(r["host_cpu_busy_percent"],10.)
        self.assertEqual(r["analysis"]["10"]["status_changes"]["done"],1)
        self.assertEqual(r["verdict"],"CPU_HEADROOM_OBSERVED_PROVIDER_OR_WAIT_MAY_DOMINATE")
        self.assertEqual(r["unit_cpu_percent_of_one_core"]["analysis"],1.1)

    def test_no_job_progress_does_not_authorize_extra_workers(self):
        start={pid:{"statuses":{"queued":2},"attempts":0} for pid in ("8","10")}
        units={key:100 for key in bench.UNITS}
        r=bench.calculate(start,start,(1000,500),(2000,1400),units,units,90)
        self.assertEqual(r["verdict"],"INCONCLUSIVE_NO_JOB_PROGRESS_DURING_SAMPLE")

    def test_single_command_records_progress_without_writes(self):
        now=[0.]
        def clock():return now[0]
        def sleep(step):now[0]+=step
        def counted(database):
            return {"8":{"statuses":{"queued":1},"attempts":0},
                    "10":{"statuses":{"done":2 if now[0]>=90 else 1},
                          "attempts":2 if now[0]>=90 else 1}}
        def readcpu():return (2000,1800) if now[0]>=90 else (1000,900)
        def svc(unit):return 2_000_000 if now[0]>=90 else 1_000_000
        r=bench.benchmark(90,self.db,sleeper=sleep,clock=clock,
                          jobs=counted,cpu=readcpu,units=svc,memory=lambda:5_000_000)
        self.assertEqual(r["analysis"]["10"]["status_changes"]["done"],1)
        self.assertEqual(r["production_writes"],0)
        self.assertEqual(r["worker_restarts"],0)
        self.assertEqual(r["provider_requests"],0)
        self.assertEqual(r["new_analysis_lanes"],0)
        self.assertEqual(r["new_offline_workers"],0)

    def test_duration_guard(self):
        with self.assertRaisesRegex(ValueError,"60_TO_240"):
            bench.benchmark(8,self.db)
        with self.assertRaisesRegex(ValueError,"60_TO_240"):
            bench.benchmark(999,self.db)

    def test_missing_db_never_created(self):
        p=Path(self.tmp.name)/"missing.sqlite3"
        with self.assertRaisesRegex(ValueError,"PRODUCTION_DB_NOT_FOUND"):
            bench.read_jobs(p)
        self.assertFalse(p.exists())

    def test_no_arbitrary_unit_probe(self):
        with self.assertRaisesRegex(ValueError,"UNAUTHORIZED_UNIT"):
            bench.systemd("some-other-unit")

    def test_unknown_job_status_not_exported(self):
        with sqlite3.connect(self.db) as c:
            c.execute("UPDATE skip_jobs SET status='PRIVATE-ACCOUNT' WHERE asset_key='a'")
        r=bench.read_jobs(self.db)
        self.assertEqual(r["8"]["statuses"]["other"],1)
        self.assertNotIn("PRIVATE-ACCOUNT",str(r))

if __name__=="__main__":
    unittest.main()
