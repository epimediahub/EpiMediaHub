#!/usr/bin/env python3
"""One idempotent Europe/Berlin expiry-report publication cycle.

An operator MUST explicitly certify that the provider refresh covers the
active Xtream population before enabling this job in systemd/cron.
The command is NOT installed or run merely by adding it to GitHub.

Outputs no customer PII. PDF is stored mode 0600 inside private admin folder;
FCM outbox contains ONLY generic report type and deterministic report key.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time, timezone
import json
import os
from pathlib import Path
import stat
import tempfile
from zoneinfo import ZoneInfo

from expiry_cache import read_verified, Unavailable
from expiry_report_rows import linked_expiries
from expiry_report_calendar import upcoming_month_on_last_day, calendar_week_on_monday
from expiry_report_pdf import monthly_pdf
from mobile_registry import AdminMobileRegistry

BERLIN=ZoneInfo("Europe/Berlin")


def _private_dir(folder):
    folder=Path(folder)
    if folder.is_symlink():
        raise Unavailable("unsafe report folder")
    folder.mkdir(parents=True,mode=0o700,exist_ok=True)
    st=folder.stat()
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid()
            or st.st_mode & 0o077):
        raise Unavailable("private report folder required")
    return folder


def publish_once(data_dir:Path,provisioning:Path,now:datetime,
                 certified_source:bool=False, registry=None):
    """Generate only due periods, then enqueue a generic notification once.

    'certified_source' is a post-audit operator-controlled release gate;
    never infer full Xtream coverage merely because a cache contains records.
    """
    if not certified_source:
        raise Unavailable("PROVIDER_COVERAGE_NOT_CERTIFIED")
    if now.tzinfo is None:
        raise ValueError("timezone-aware clock required")
    now=now.astimezone(BERLIN)
    month=upcoming_month_on_last_day(now.date())
    week=calendar_week_on_monday(now.date())
    if month is None and week is None:
        return {"published":[],"queued_notification_kinds":[]}
    # Avoid misleading subscribers before providers finish the daily refresh.
    if now.time()<time(7):
        return {"published":[],"queued_notification_kinds":[]}
    folder=_private_dir(Path(data_dir)/"admin-mobile")
    observations=read_verified(folder/"expiry-cache.sqlite3")
    if not observations:
        raise Unavailable("NO_VERIFIED_PROVIDER_DATA")
    current=now.astimezone(timezone.utc)
    if not any(-300<=(current-o.observed_at).total_seconds()<=48*3600
               for o in observations):
        raise Unavailable("PROVIDER_DATA_STALE")
    records=linked_expiries(provisioning,observations,current)
    # A verified account may expire outside this period; an empty target
    # report is legitimate only if the PROVIDER source is certified complete.
    published=[]
    notifications=[]
    if month is not None:
        year,mo=month
        dest=_private_dir(folder/"expiry-reports")
        filename=f"expiry-{year:04d}-{mo:02d}.pdf"
        target=dest/filename
        if target.is_symlink():
            raise Unavailable("linked PDF report")
        if not target.exists():
            fd,temp=tempfile.mkstemp(prefix=".report-",suffix=".pdf",dir=dest)
            try:
                os.fchmod(fd,0o600)
                with os.fdopen(fd,"wb") as out:
                    monthly_pdf(records,year,mo,out)
                    out.flush()
                    os.fsync(out.fileno())
                # Never overwrite an existing authoritative report on rerun.
                if not target.exists():
                    os.link(temp,target)
                else:
                    meta=target.stat()
                    if meta.st_uid!=os.geteuid() or meta.st_mode & 0o077:
                        raise Unavailable("unsafe existing report file")
            finally:
                Path(temp).unlink(missing_ok=True)
        else:
            meta=target.stat()
            if meta.st_uid!=os.geteuid() or meta.st_mode & 0o077:
                raise Unavailable("unsafe existing report file")
        published.append(f"month:{year:04d}-{mo:02d}")
        event_date=now.date()
        epoch=int(datetime.combine(event_date,time.min,BERLIN).timestamp())
        notifications.append((f"expiry_month:{year:04d}-{mo:02d}",
                              "expiry_monthly",epoch))
    if week is not None:
        monday,_=week
        published.append("week:"+monday.isoformat())
        epoch=int(datetime.combine(monday,time.min,BERLIN).timestamp())
        notifications.append(("expiry_week:"+monday.isoformat(),
                              "expiry_weekly",epoch))
    if notifications:
        registry=registry or AdminMobileRegistry(folder/"registrations.sqlite3")
        registry.enqueue(notifications,int(current.timestamp()))
    return {"published":published,"queued_notification_kinds":[x[1] for x in notifications]}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--data-dir",type=Path,
                        default=Path("/var/lib/epimediahub"))
    parser.add_argument("--db",type=Path,
                        default=Path("/var/lib/epimediahub/provisioning.db"))
    args=parser.parse_args()
    # This is a deployment operator control, NOT inferred from cache contents.
    enabled=os.environ.get("EPIMEDIAHUB_EXPIRY_PROVIDER_COVERAGE_CERTIFIED")=="YES"
    result=publish_once(args.data_dir,args.db,datetime.now(timezone.utc),
                        certified_source=enabled)
    print(json.dumps(result,sort_keys=True))


if __name__=="__main__":
    main()
