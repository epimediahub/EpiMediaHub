#!/usr/bin/env python3
"""Conservative LOCAL CPU lane capacity advisory; never starts provider streams.

Capture/stream slots remain exactly one per analysis playlist. No workers are
spawned here. An audited analysis adapter can later run already-captured data
through separate bounded processes after validating memory and worker versions.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

RESERVED_CPUS = 2
MIN_MEMORY_PER_EXTRA_WORKER = 1_500_000_000
MAX_EXTRA_COMPUTE_WORKERS = 2


def cpu_quota_cores(value):
    fields = value.strip().split()
    if len(fields) != 2 or fields[0] == "max":
        return None
    try:
        quota, period = (int(x) for x in fields)
        if quota <= 0 or period <= 0:
            return None
        return quota / period
    except ValueError:
        return None


def capacity(*, host_cpus=None, quota=None, available_memory=None,
             current_analyzer_cpu_busy=None):
    cpus = int(host_cpus if host_cpus is not None else (os.cpu_count() or 1))
    if cpus < 1:
        raise ValueError("invalid_cpu_count")
    effective = float(cpus)
    if quota is not None:
        q = cpu_quota_cores(quota)
        if q is not None:
            effective = min(effective, q)
    memory = available_memory if available_memory is not None else 0
    if not isinstance(memory, int) or memory < 0:
        raise ValueError("invalid_memory")
    if current_analyzer_cpu_busy is not None and not (0 <= current_analyzer_cpu_busy <= 1):
        raise ValueError("invalid_cpu_usage")
    # Never authorize extra work when actual free RAM is unknown.
    cores_for_work = max(0, math.floor(effective) - RESERVED_CPUS)
    memory_budget = max(0, memory // MIN_MEMORY_PER_EXTRA_WORKER)
    extra = min(MAX_EXTRA_COMPUTE_WORKERS, cores_for_work, memory_budget)
    if current_analyzer_cpu_busy is None or current_analyzer_cpu_busy >= 0.80:
        extra = 0  # require measured headroom before enabling any extra lane
    return {
        "mode": "READ_ONLY_OFFLINE_COMPUTE_CAPACITY",
        "effective_cpu_cores": round(effective, 2),
        "extra_offline_compute_workers_advisory": int(extra),
        "stream_slots_4k": 1, "stream_slots_the_best": 1,
        "new_provider_connections": 0, "processes_started": 0,
        "requires_live_resource_measurement_and_adapter": True,
    }


def read_capacity():
    quota = None
    cgroup = Path("/sys/fs/cgroup/cpu.max")
    if cgroup.is_file():
        try:
            quota = cgroup.read_text(encoding="ascii")[:80]
        except (OSError, UnicodeError):
            pass
    memory = 0
    info = Path("/proc/meminfo")
    if info.is_file():
        try:
            for line in info.read_text(encoding="ascii").splitlines():
                if line.startswith("MemAvailable:"):
                    memory = int(line.split()[1]) * 1024
                    break
        except (OSError, UnicodeError, ValueError, IndexError):
            memory = 0
    # Do not infer service-specific CPU utilization from host-wide load.
    return capacity(quota=quota, available_memory=memory,
                    current_analyzer_cpu_busy=None)


if __name__ == "__main__":
    print(json.dumps(read_capacity(), sort_keys=True))
