#!/usr/bin/env python3
"""Post-deployment EpiScene customer marker verification, read-only.

Counts customer-scoped provenance and approved/pending outcomes without
ever exporting identities, provider URLs, marker time ranges or episode names.
This is not a substitute for a live device/playback submission test.
"""
from __future__ import annotations
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

DB=Path("/var/lib/epimediahub/provisioning.db")
ROOT=Path("/opt/epimediahub/provisioning")
EXPECTED={
 "skip_analysis.py":"10b8537eb3df3b3a4744959e51150b86046f26c8aa625a4bdf4ac9331c3cea5b",
 "skip_markers.py":"2c79ae7f574cfb596e51d81f547063c6fa92b8ed7479352cf115a4cd219a8e18",
}
SERVICES=("epimediahub-provisioning.service","epimediahub-analysis-worker.service")
TABLES={
 "skip_customer_asset_claims":{"customer_id","playlist_id","asset_key"},
 "skip_customer_marker_provenance":{"record_id","customer_id","playlist_id","asset_key"},
 "skip_records":{"id","status","source","device_id","customer_id"},
}

def diagnostic(database=DB,root=ROOT,active=None):
    if database.is_symlink() or not database.is_file():
        raise ValueError("DB_UNAVAILABLE")
    db=sqlite3.connect(database.resolve().as_uri()+"?mode=ro",uri=True,timeout=8)
    try:
        db.execute("PRAGMA query_only=ON")
        for name,required in TABLES.items():
            actual={r[1] for r in db.execute("PRAGMA table_info("+name+")")}
            if not required<=actual:
                raise ValueError("SCOPE_SCHEMA_MISSING_"+name)
        db.execute("BEGIN")
        claims=db.execute("SELECT COUNT(*) FROM skip_customer_asset_claims").fetchone()[0]
        results=Counter()
        for status,num in db.execute("""
          SELECT r.status,COUNT(*) FROM skip_customer_marker_provenance p
          JOIN skip_records r ON r.id=p.record_id
          WHERE r.source='device' AND p.customer_id=r.customer_id
          GROUP BY r.status"""):
            results[status if status in ("approved","pending","rejected","superseded")
                    else "other"]+=int(num)
        total=db.execute("SELECT COUNT(*) FROM skip_customer_marker_provenance").fetchone()[0]
    finally:
        db.close()
    hashes={}
    for name,expected in EXPECTED.items():
        path=root/name
        if path.is_symlink() or not path.is_file():
            hashes[name]="missing"
        else:
            hashes[name]=("match" if hashlib.sha256(path.read_bytes()).hexdigest()==expected
                          else "DRIFT")
    if active is None:
        def active(service):
            try:
                return subprocess.run(["systemctl","is-active","--quiet",service],
                                      check=False,timeout=5).returncode==0
            except (OSError,subprocess.TimeoutExpired):
                return False
    services={service:bool(active(service)) for service in SERVICES}
    return {
      "mode":"CUSTOMER_MARKER_POST_INSTALL_READ_ONLY",
      "source_versions":hashes,
      "services_active":services,
      "customer_asset_claims":claims,
      "scoped_marker_provenance_total":total,
      "scoped_marker_status_counts":dict(results),
      "all_versions_match":all(v=="match" for v in hashes.values()),
      "both_services_active":all(services.values()),
      "legacy_pending_not_modified":True,
      "database_writes":0,"worker_restarts":0,
      "identity_or_token_data_returned":False,
    }

def main():
    try:
        result=diagnostic()
    except (ValueError,sqlite3.Error,OSError):
        print(json.dumps({"status":"STOP_READ_ONLY","reason":"DB_OR_SCHEMA_UNAVAILABLE",
                          "database_writes":0},sort_keys=True))
        return 2
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0 if result["all_versions_match"] and result["both_services_active"] else 2

if __name__=="__main__":
    sys.exit(main())
