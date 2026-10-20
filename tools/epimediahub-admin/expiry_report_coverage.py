"""Authenticated, read-only account coverage view for Admin V2.

Unknown/missing/stale provider observations are NOT interpreted as subscriptions
without expiration dates. This preview neither authorizes PDF publication nor
performs any network or database write. Never return IPTV config credentials.
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import json
import hmac

from expiry_cache import read_verified, Unavailable
from expiry_report_rows import MAX_AGE, CLOCK_SKEW
from expiry_http_snapshot import (read_snapshot,get_key_for_preview,
                                  fingerprint,InsecureSnapshotUnavailable)


class CoveragePreviewUnavailable(RuntimeError):
    pass


def preview(database: Path, cache: Path, now: datetime) -> dict:
    if now.tzinfo is None or now.utcoffset() is None:
        raise CoveragePreviewUnavailable("invalid clock")
    now=now.astimezone(timezone.utc)
    database=Path(database)
    if database.is_symlink() or not database.is_file():
        raise CoveragePreviewUnavailable("database not available")

    # A missing cache is not evidence of no expiry: list ALL as unverified.
    # An unsafe/unreadable existing cache fails closed instead.
    if Path(cache).is_symlink():
        raise CoveragePreviewUnavailable("unsafe cache")
    verified=[]
    if Path(cache).exists():
        try:
            verified=read_verified(cache)
        except (Unavailable,sqlite3.Error,ValueError,OSError) as exc:
            raise CoveragePreviewUnavailable("cache could not be verified") from None

    provisional_path=Path(cache).with_name("expiry-http.sqlite3")
    provisional={}
    provisional_key=None
    try:
        provisional=read_snapshot(provisional_path,now)
        if provisional:
            provisional_key=get_key_for_preview(provisional_path)
    except (InsecureSnapshotUnavailable,sqlite3.Error,OSError,ValueError):
        # Bad or modified HTTP snapshot must never silently become verified.
        raise CoveragePreviewUnavailable("preliminary snapshot cannot be trusted") from None

    observed={}
    for row in verified:
        if row.playlist_id in observed:
            raise CoveragePreviewUnavailable("duplicate provider record")
        observed[row.playlist_id]=row

    con=sqlite3.connect(database.resolve().as_uri()+"?mode=ro",
                        uri=True,timeout=8)
    try:
        con.execute("PRAGMA query_only=ON")
        rows=con.execute("""
            SELECT p.id,c.name,p.name,p.config_json
            FROM customer_playlists p
            JOIN customers c ON c.id=p.customer_id
            WHERE p.enabled=1 AND c.enabled=1
            ORDER BY p.id LIMIT 10001
        """).fetchall()
    finally:
        con.close()
    if len(rows)>10000:
        raise CoveragePreviewUnavailable("too many customer playlists")

    group=defaultdict(list)
    confirmed=0
    http_observed=0
    for playlist_id, customer, playlist, config_json in rows:
        if (type(playlist_id) is not int or playlist_id<1 or
            not all(isinstance(x,str) and x.strip() and len(x)<=200
                    and not any(ord(ch)<32 for ch in x)
                    for x in (customer,playlist))):
            raise CoveragePreviewUnavailable("invalid account record")
        record=observed.get(playlist_id)
        day=None
        if record is not None:
            age=now-record.observed_at.astimezone(timezone.utc)
            if -CLOCK_SKEW<=age<=MAX_AGE:
                day=record.expires_on.isoformat()
                confirmed+=1
        status="confirmed" if day else "unverified"
        reason=None
        if day is None and playlist_id in provisional:
            pre_day,pre_status,digest=provisional[playlist_id]
            # An account may have been reassigned or credentials rotated since
            # the last HTTP poll. Never attach the old date to the new account.
            try:
                config=json.loads(config_json)
                fresh=fingerprint(config,provisional_key)
                same=hmac.compare_digest(fresh,digest)
            except (TypeError,ValueError,InsecureSnapshotUnavailable):
                same=False
            if same:
                if pre_day is not None and pre_status=="http_observed":
                    day=pre_day.isoformat()
                    status="http_observed"
                    http_observed+=1
                else:
                    reason=pre_status
        group[playlist].append({
            "customer":customer,
            "expires_on":day,
            "status":status,
            "provider_reason":reason,
        })
    return {
        "active_accounts":len(rows),
        "confirmed_accounts":confirmed,
        "http_observed_accounts":http_observed,
        "unverified_accounts":len(rows)-confirmed-http_observed,
        "snapshot_complete":bool(rows) and len(rows)==confirmed,
        "source":"verified_plus_preliminary_http_distinguished",
        "network_requests":0,
        "as_of_utc":now.isoformat(),
        "playlists":[{
            "name":name,
            "entries":sorted(group[name],key=lambda x:(
                x["expires_on"] is None,x["expires_on"] or "",
                x["customer"].casefold()))
        } for name in sorted(group,key=str.casefold)],
    }
