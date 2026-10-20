#!/usr/bin/env python3
"""Daily *opt-in* Xtream HTTP expiry observer, no external PII output.

Reads active provisioning accounts read-only and persists a private
PRELIMINARY snapshot (NOT the verified HTTPS report publisher's cache).
One request/account/day, no retries or redirects. Opt-in must be present
on EVERY invocation, including systemd executions. HTTP remains insecure.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime,timezone
import http.client
import json
import os
from pathlib import Path
import socket
import sqlite3
import ssl
import sys
import time

from expiry_provider_adapter import xtream_expiry
from expiry_http_snapshot import (
    Observation,VALID_STATES,fingerprint,load_key_for_worker,replace_snapshot
)
from xtream_expiry_refresh import (
    DATABASE,ProbeError,read_accounts,player_compatible_http_fetch,
    secure_fetch,diagnostic_reason
)

CACHE=Path("/var/lib/epimediahub/admin-mobile/expiry-http.sqlite3")

class DailyRefreshUnavailable(RuntimeError):pass

def refresh(database=DATABASE,cache=CACHE,now=None,wait=lambda _:None,
            http_fetch=player_compatible_http_fetch,https_fetch=secure_fetch):
    """The two injectables make all tests fully offline."""
    if os.environ.get("EPIMEDIAHUB_XTREAM_DAILY_HTTP_APPROVED")!="YES":
        raise DailyRefreshUnavailable("explicit daily HTTP approval required")
    clock=now or datetime.now(timezone.utc)
    if clock.tzinfo is None or clock.utcoffset() is None:
        raise DailyRefreshUnavailable("timezone-aware clock required")
    accounts=read_accounts(database)
    key=load_key_for_worker(cache)
    rows=[]
    results=Counter()
    for index,(ident,values) in enumerate(accounts):
        if index:wait(0.7)
        if values is None:
            results["incomplete_credentials"]+=1
            continue
        endpoint,username,password=values
        config={"xtream_server":endpoint,
                "xtream_username":username,"xtream_password":password}
        identity=fingerprint(config,key)
        status="provider_error"
        expiry=None
        try:
            scheme=endpoint.split(":",1)[0].lower()
            if scheme=="http":
                info=http_fetch(endpoint,username,password)
            elif scheme=="https":
                info=https_fetch(endpoint,username,password)
            else:
                raise ProbeError("invalid_endpoint")
            extracted=xtream_expiry(info)
            if extracted.expires_on is None:
                status=("provider_date_undated" if extracted.status=="undated"
                        else "provider_date_unavailable")
            else:
                expiry=extracted.expires_on
                status="http_observed"
        except (ProbeError,OSError,ssl.SSLError,http.client.HTTPException,
                ValueError) as error:
            status=diagnostic_reason(error)
        # The stored state is never allowed to claim cryptographic verification.
        if status not in VALID_STATES:
            status="provider_error"
        rows.append(Observation(ident,expiry,clock,status,identity))
        results[status]+=1
    replace_snapshot(cache,rows)
    return {
        "active_xtream_accounts":len(accounts),
        "stored_account_statuses":len(rows),
        "dates_observed_over_unverified_transport":results["http_observed"],
        "unverified_or_unknown":len(accounts)-results["http_observed"],
        "result_counts":dict(sorted(results.items())),
        "cache_source":"preliminary_insecure_http",
        "automated_authoritative_pdf_enabled":False,
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true",required=True,
                        help="Exactly one operator-approved daily refresh")
    args=parser.parse_args()
    if not args.once:
        raise DailyRefreshUnavailable("once required")
    info=refresh(wait=time.sleep)
    print("INSECURE_XTREAM_DAILY_REFRESH_COMPLETE")
    print(json.dumps(info,sort_keys=True))

if __name__=="__main__":
    try:
        main()
    except (DailyRefreshUnavailable,ProbeError,sqlite3.Error,OSError,
            ValueError,PermissionError):
        # No exception messages: server names/passwords never hit journalctl.
        print("INSECURE_XTREAM_DAILY_REFRESH_UNAVAILABLE",file=sys.stderr)
        sys.exit(2)
