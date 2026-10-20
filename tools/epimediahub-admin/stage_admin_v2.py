#!/usr/bin/env python3
"""Read-only pinned staging for a guarded Admin V2 Hetzner upgrade.

Only writes a private /root staging folder. No production or customer data
is touched, and no service is stopped/restarted by this preflight.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

COMMIT="a695f09bb8280fe9fc97683c97082b1b49b3d75d"
BLOBS={
  "mobile_flask.py": "81a45fc7d121cbf375c287bac5a30069f1874412",
  "native_management_data.py": "4d67cdaa5f9c58669c7777e7597b874fa772787d",
  "native_management_actions.py": "b807214cff0faaec984bb70818e1e342a37f1d60",
  "native_management_edits.py": "d9927f0ce961ac38c93dffc8edfbf56f6613139f",
  "native_legacy_bridge.py": "6d9f01480938dbc5938efea273ee0d5aa9287698",
  "native_delete_confirmation.py": "66eaece0bc0fb7b208452a304da0bd7646fad728",
  "native_marker_review.py": "fb3a99e3294a28939d583be6c34781223bd21f0f",
  "expiry_report_core.py": "07e20e45270fc9fe187ae000e25eb124c9e226c9",
  "expiry_cache.py": "c5ff343c193deab3fffecb1c82a7828cdf9ebe82",
  "expiry_provider_adapter.py": "89205c04fa068d05e7c75b146b357b04801c0934",
  "expiry_report_rows.py": "8665119affa32f84614228f00d4cfb1fa4883303",
  "expiry_report_coverage.py": "bd42029cdc8d88d622fe7b8c844e42a30e029723",
  "expiry_report_calendar.py": "cccf054b86aef5370c9b3a8a02b3eb3a3f566c9a",
  "expiry_report_pdf.py": "cc478a1be6332b5752c0c1acb3c80ec35ec53524",
  "expiry_report_publish.py": "e754d703177b1161b41699b887083d6632788fe8",
  "xtream_expiry_refresh.py": "5ce20e939111ed18a0f4c70bcdd6401d18104683",
  "expiry_http_snapshot.py": "a94f5e31b4cf3a610ebaa5de17ff15b4873d6272",
  "expiry_http_worker.py": "2b94299b6d629cbcc70dcbf02e86a691cc328003",
  "upgrade_native_management_backend.py": "6b1bb6dadbb2151a14f57090c75dfd6780554ec8",
  "install_daily_xtream_http.py": "531d0a94cb054702dcde61f6a328085d21a1968e"
}
DIRECTORY=Path("/root/epimediahub-admin-v2-stage")
BASE="https://raw.githubusercontent.com/epimediahub/EpiMediaHub/"+COMMIT+"/tools/epimediahub-admin/"
MAX_BYTES=160000

def git_blob(data):
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\x00"+data).hexdigest()

def main():
    cli=argparse.ArgumentParser()
    cli.add_argument("--check",action="store_true",required=True)
    cli.parse_args()
    if os.geteuid()!=0 or DIRECTORY.is_symlink():
        raise RuntimeError("root and unlinked staging directory required")
    os.umask(0o077)
    DIRECTORY.mkdir(mode=0o700,parents=True,exist_ok=True)
    if DIRECTORY.stat().st_mode&0o077:
        raise RuntimeError("unsafe staging directory permissions")
    completed=0
    for name,expected in BLOBS.items():
        if "/" in name or name.startswith("."):
            raise RuntimeError("invalid module name")
        path=DIRECTORY/name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise RuntimeError("unsafe existing staging module")
        if path.exists():
            data=path.read_bytes()
            if git_blob(data)!=expected:
                raise RuntimeError("staging file differs from pinned source")
        else:
            with urllib.request.urlopen(BASE+name,timeout=20) as response:
                data=response.read(MAX_BYTES+1)
            if len(data)>MAX_BYTES or git_blob(data)!=expected:
                raise RuntimeError("download integrity mismatch")
            ast.parse(data.decode("utf-8"),filename=name)
            fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,"wb") as stream:
                stream.write(data)
        completed+=1
    print("ADMIN_V2_PINNED_MODULES_STAGED="+str(completed))
    print("STAGED_SOURCE_COMMIT="+COMMIT)
    print("NO_CUSTOMER_DATA_OR_PRODUCTION_MODULES_CHANGED")
    result=subprocess.run(
        [sys.executable,str(DIRECTORY/"upgrade_native_management_backend.py"),
         "--check"],
        timeout=45,capture_output=True,text=True)
    if result.stdout:
        print(result.stdout.strip()[:1400])
    if result.returncode:
        print("ADMIN_V2_NATIVE_PREFLIGHT_REQUIRES_REVIEW")
        raise RuntimeError("native preflight did not pass")
    print("ADMIN_V2_NATIVE_PREFLIGHT_PASSED")
    print("NO_SERVICES_RESTARTED_OR_TIMERS_INSTALLED")

if __name__=="__main__":
    try:
        main()
    except Exception:
        print("ADMIN_V2_STAGING_OR_PREFLIGHT_STOPPED; PRODUCTION_UNCHANGED",
              file=sys.stderr)
        sys.exit(2)
