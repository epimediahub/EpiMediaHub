#!/usr/bin/env python3
"""EpiScene bounded live throughput benchmark: strictly READ ONLY.

Reads CPU /proc counters, systemd cgroup CPU and aggregate analysis job
transitions. Never contacts IPTV providers, writes SQLite, or restarts workers.
One brief low-load snapshot alone cannot authorize extra offline workers.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

DATABASE=Path("/var/lib/epimediahub/provisioning.db")
CGROUP=Path("/sys/fs/cgroup")
UNITS={
    "analysis":"epimediahub-analysis-worker.service",
    "api":"epimediahub-provisioning.service",
    "priority":"episcene-customer-smart-priority.service",
    "learning":"episcene-customer-learning.service",
}
KINDS={"queued","running","done","review","no_match","no_reference",
       "failed","partial","disabled"}

def systemd(unit,property_name=None):
    if unit not in UNITS.values():
        raise ValueError("UNAUTHORIZED_UNIT")
    args=(["systemctl","is-active","--",unit] if property_name is None else
          ["systemctl","show","--property=ControlGroup","--value","--",unit])
    try:
        result=subprocess.run(args,capture_output=True,text=True,check=False,timeout=5)
        return result.stdout.strip() if result.returncode==0 else ""
    except (OSError,subprocess.TimeoutExpired):
        return ""

def service_usage(unit):
    group=systemd(unit,"ControlGroup")
    if (not group.startswith("/") or ".." in group.split("/") or
        not re.fullmatch(r"/[A-Za-z0-9_@./-]+",group)):
        return None
    path=CGROUP/group.lstrip("/")/"cpu.stat"
    try:
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(CGROUP.resolve()):
            return None
        items=dict(line.split()[:2] for line in path.read_text("ascii").splitlines()
                   if len(line.split())>=2)
        return int(items["usage_usec"]) if "usage_usec" in items else None
    except (OSError,UnicodeError,ValueError):
        return None

def cpu_sample():
    values=Path("/proc/stat").read_text("ascii").splitlines()[0].split()
    if not values or values[0]!="cpu" or len(values)<5:
        raise ValueError("PROC_CPU_STAT_UNAVAILABLE")
    n=[int(v) for v in values[1:]]
    return sum(n), n[3]+(n[4] if len(n)>4 else 0)

def mem_available_kib():
    try:
        for line in Path("/proc/meminfo").read_text("ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1])
    except (OSError,UnicodeError,ValueError,IndexError):
        pass
    return None

def read_jobs(database=DATABASE):
    if database.is_symlink() or not database.is_file():
        raise ValueError("PRODUCTION_DB_NOT_FOUND")
    with sqlite3.connect(database.resolve().as_uri()+"?mode=ro",
                         uri=True,timeout=8) as db:
        db.execute("PRAGMA query_only=ON")
        jobs={r[1] for r in db.execute("PRAGMA table_info(skip_jobs)")}
        assets={r[1] for r in db.execute("PRAGMA table_info(skip_assets)")}
        if not {"asset_key","status","attempts"}<=jobs or not {"asset_key","playlist_id"}<=assets:
            raise ValueError("ANALYSIS_SCHEMA_UNEXPECTED")
        data={str(pid):{"statuses":{},"attempts":0} for pid in (8,10)}
        for playlist,status,total,attempts in db.execute("""
            SELECT a.playlist_id,j.status,COUNT(*),COALESCE(SUM(j.attempts),0)
              FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
             WHERE a.playlist_id IN (8,10)
             GROUP BY a.playlist_id,j.status"""):
            part=data[str(playlist)]
            key=status if status in KINDS else "other"
            part["statuses"][key]=part["statuses"].get(key,0)+int(total)
            part["attempts"]+=int(attempts)
        return data

def calculate(begin,end,start_cpu,end_cpu,start_services,end_services,elapsed):
    total=end_cpu[0]-start_cpu[0]
    busy=total-(end_cpu[1]-start_cpu[1])
    host=(round(100*max(0,min(total,busy))/total,1) if total>0 else None)
    service={}
    for key in UNITS:
        x=start_services[key];y=end_services[key]
        service[key]=(round((y-x)/10000/elapsed,1)
                      if x is not None and y is not None and y>=x and elapsed>0
                      else None)
    changes={}
    work=0
    for pid in ("8","10"):
        a=begin[pid];b=end[pid]
        diff={status:b["statuses"].get(status,0)-a["statuses"].get(status,0)
              for status in ("queued","running","done","review","no_match",
                             "no_reference","failed","partial")}
        attempts=b["attempts"]-a["attempts"]
        changes[pid]={"status_changes":diff,"attempts_delta":attempts,
                      "queued_at_end":b["statuses"].get("queued",0)}
        work+=max(0,attempts)+max(0,diff["done"])
    # Never recommend an additional provider lane. An offline adapter must
    # be audited and separately benchmarked against cached, local data.
    if elapsed<55 or host is None:
        verdict="MEASUREMENT_INSUFFICIENT"
    elif work<=0:
        verdict="INCONCLUSIVE_NO_JOB_PROGRESS_DURING_SAMPLE"
    elif host<45:
        verdict="CPU_HEADROOM_OBSERVED_PROVIDER_OR_WAIT_MAY_DOMINATE"
    elif host>=80 and (service["analysis"] or 0)>=125:
        verdict="CPU_PRESSURE_OBSERVED_TEST_OFFLINE_CACHE_ADAPTER_SEPARATELY"
    else:
        verdict="MIXED_USAGE_MORE_OFFLINE_BENCHMARK_REQUIRED"
    return {"host_cpu_busy_percent":host,"unit_cpu_percent_of_one_core":service,
            "analysis":changes,"verdict":verdict}

def benchmark(seconds,database=DATABASE,sleeper=time.sleep,clock=time.monotonic,
              cpu=cpu_sample,jobs=read_jobs,units=service_usage,memory=mem_available_kib):
    if type(seconds) is not int or not 60<=seconds<=240:
        raise ValueError("MEASUREMENT_SECONDS_MUST_BE_60_TO_240")
    start_jobs=jobs(database)
    first_cpu=cpu()
    first_services={key:units(unit) for key,unit in UNITS.items()}
    start=clock()
    remaining=seconds
    mems=[memory()]
    while remaining>0:
        sleeper(min(10,remaining))
        remaining=seconds-(clock()-start)
        mems.append(memory())
    elapsed=clock()-start
    last_cpu=cpu()
    last_services={key:units(unit) for key,unit in UNITS.items()}
    final_jobs=jobs(database)
    measurements=calculate(start_jobs,final_jobs,first_cpu,last_cpu,
                           first_services,last_services,elapsed)
    valid=[x for x in mems if x is not None]
    return {
        "mode":"EPISCENE_MEASURED_THROUGHPUT_AND_CPU_READ_ONLY",
        "seconds_measured":round(elapsed,1),
        **measurements,
        "minimum_available_memory_gib":round(min(valid)/1048576,2) if valid else None,
        "playlist_provider_connection_caps":{"8":1,"10":1},
        "new_analysis_lanes":0,"new_offline_workers":0,
        "production_writes":0,"provider_requests":0,"worker_restarts":0,
        "customer_or_source_information_exported":False,
    }

def check(database=DATABASE):
    queued={pid:row["statuses"].get("queued",0) for pid,row in read_jobs(database).items()}
    return {"mode":"EPISCENE_CPU_BENCHMARK_PREFLIGHT","preflight":"PASS",
            "cpu_cores":os.cpu_count() or 1,"queued_jobs":queued,
            "api_active":systemd(UNITS["api"])=="active",
            "analysis_active":systemd(UNITS["analysis"])=="active",
            "production_writes":0,"provider_requests":0}

def main():
    p=argparse.ArgumentParser()
    m=p.add_mutually_exclusive_group(required=True)
    m.add_argument("--check",action="store_true")
    m.add_argument("--measure",action="store_true")
    p.add_argument("--seconds",type=int,default=90)
    opts=p.parse_args()
    try:
        output=check() if opts.check else benchmark(opts.seconds)
        print(json.dumps(output,sort_keys=True,indent=2))
        return 0
    except (ValueError,sqlite3.Error,OSError) as error:
        print(json.dumps({"status":"STOP_NO_CHANGES",
                          "reason":str(error) if isinstance(error,ValueError) else "READ_ONLY_SOURCE_UNAVAILABLE",
                          "production_writes":0},sort_keys=True))
        return 2

if __name__=="__main__":
    sys.exit(main())
