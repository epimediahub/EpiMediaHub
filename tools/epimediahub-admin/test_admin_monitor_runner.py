"""Admin monitoring runner passes only real lane data and refuses fake recovery."""
import tempfile
from pathlib import Path
import unittest
from unittest import mock

import admin_monitor_runner as runner


class RunnerTests(unittest.TestCase):
    def test_one_cycle_reads_only_production_db_and_keeps_other_metrics_unknown(self):
        with tempfile.TemporaryDirectory() as temp:
            directory=Path(temp)
            private=directory/"admin-mobile"
            private.mkdir(mode=0o700)
            private.chmod(0o700)
            db=directory/"provisioning.db"
            import sqlite3
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE witness(x INTEGER)")
            with mock.patch.object(runner,"gather",return_value={
                "sampled_at_epoch":1720000000,"analysis_lanes":[]
            }) as gather, mock.patch.object(
                runner,"run_once",return_value={"new_incident_generations":0}
            ) as monitor:
                result=runner.run(private,db,1720000000)
            self.assertEqual(gather.call_count,1)
            self.assertEqual(monitor.call_count,1)
            self.assertEqual(result["telemetry_coverage"],["analysis_lanes_8_10"])
            self.assertFalse(result["unavailable_telemetry_marked_healthy"])
            self.assertEqual((private/"analysis-metrics.json").stat().st_mode & 0o077,0)


if __name__=="__main__":
    unittest.main()
