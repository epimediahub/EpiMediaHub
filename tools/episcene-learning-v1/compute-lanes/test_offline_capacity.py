"""Capacity advice never opens streams or starts worker processes."""
from pathlib import Path
import importlib.util
import unittest

spec = importlib.util.spec_from_file_location("offline_capacity", Path(__file__).with_name("offline_capacity.py"))
capacity = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capacity)


class OfflineCapacityTests(unittest.TestCase):
    def test_four_core_host_with_headroom_allows_up_to_two(self):
        x = capacity.capacity(host_cpus=4, quota="max 100000",
                              available_memory=8_000_000_000,
                              current_analyzer_cpu_busy=0.4)
        self.assertEqual(x["extra_offline_compute_workers_advisory"], 2)
        self.assertEqual(x["new_provider_connections"], 0)

    def test_busy_cpu_disables_extra_lanes(self):
        x = capacity.capacity(host_cpus=16, available_memory=32_000_000_000,
                              current_analyzer_cpu_busy=0.85)
        self.assertEqual(x["extra_offline_compute_workers_advisory"], 0)

    def test_unknown_cpu_use_or_ram_disables_extra_lanes(self):
        x = capacity.capacity(host_cpus=8, available_memory=32_000_000_000)
        self.assertEqual(x["extra_offline_compute_workers_advisory"], 0)
        x = capacity.capacity(host_cpus=8, available_memory=0,
                              current_analyzer_cpu_busy=0.1)
        self.assertEqual(x["extra_offline_compute_workers_advisory"], 0)

    def test_cgroup_quota_is_respected(self):
        x = capacity.capacity(host_cpus=16, quota="200000 100000",
                              available_memory=32_000_000_000,
                              current_analyzer_cpu_busy=0.1)
        self.assertEqual(x["effective_cpu_cores"], 2)
        self.assertEqual(x["extra_offline_compute_workers_advisory"], 0)

    def test_invalid_params_fail(self):
        with self.assertRaises(ValueError):
            capacity.capacity(host_cpus=0, available_memory=0)


if __name__ == "__main__":
    unittest.main()
