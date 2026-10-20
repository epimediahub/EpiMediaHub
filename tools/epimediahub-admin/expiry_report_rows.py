"""Join provider-confirmed expirations with admin-assigned customer/playlist names.

The upstream expiry refresh MUST validate the provider account and associate
its response with a particular customer_playlists.id. Never assume identical
playlist names or shared provider endpoints imply the same customer expiry.

This module does not call external providers or retrieve config_json/secrets.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from expiry_report_pdf import Expiry

MAX_OBSERVATIONS = 10000
MAX_AGE = timedelta(hours=48)
CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class VerifiedPlaylistExpiry:
    playlist_id: int
    expires_on: date
    observed_at: datetime


def linked_expiries(database: Path,
                    verified: list[VerifiedPlaylistExpiry],
                    now_utc: datetime,
                    reseller_id: int | None = None) -> list[Expiry]:
    """Only a fresh, independently verified provider expiry is reportable.

    Unknown/invalid provider expiry is intentionally absent, never replaced
    with annual app-license expiry, VPN expiry, or analysis-source expiry.
    """
    if now_utc.tzinfo is None or now_utc.utcoffset() is None:
        raise ValueError("timezone-aware UTC clock required")
    now_utc = now_utc.astimezone(timezone.utc)
    # Only bind reseller_id from the server-authorized session scope.
    # Never accept an arbitrary reseller id from an untrusted mobile request.
    if reseller_id is not None and (
        type(reseller_id) is not int or reseller_id < 1 or reseller_id >= 2**63
    ):
        raise ValueError("invalid reseller scope")
    if len(verified) > MAX_OBSERVATIONS:
        raise ValueError("too many provider observations")
    p = Path(database)
    if p.is_symlink() or not p.is_file():
        raise ValueError("provisioning database unavailable")
    accepted = {}
    for entry in verified:
        if not isinstance(entry, VerifiedPlaylistExpiry):
            raise ValueError("invalid provider observation")
        if (type(entry.playlist_id) is not int or entry.playlist_id <= 0
                or entry.playlist_id >= 2**63
                or type(entry.expires_on) is not date
                or entry.observed_at.tzinfo is None
                or entry.observed_at.utcoffset() is None):
            raise ValueError("invalid provider observation")
        age = now_utc-entry.observed_at.astimezone(timezone.utc)
        if age > MAX_AGE or age < -CLOCK_SKEW:
            continue
        if entry.playlist_id in accepted:
            raise ValueError("ambiguous duplicate playlist expiry observation")
        accepted[entry.playlist_id] = entry.expires_on
    if not accepted:
        return []
    conn = sqlite3.connect(p.resolve().as_uri() + "?mode=ro",
                           uri=True, timeout=8)
    try:
        conn.execute("PRAGMA query_only=ON")
        records=[]
        ids=sorted(accepted)
        for start in range(0,len(ids),500):
            chunk=ids[start:start+500]
            placeholders=",".join("?" for _ in chunk)
            # Select names and ids only; never select provider URLs/credentials.
            scoped = (
                " AND c.reseller_id=?" if reseller_id is not None else ""
            )
            query = (
                "SELECT p.id,c.name,p.name FROM customer_playlists p "
                "JOIN customers c ON c.id=p.customer_id "
                "WHERE p.enabled=1 AND c.enabled=1 AND p.id IN ("
                + placeholders + ")" + scoped
            )
            args = chunk + ([reseller_id] if reseller_id is not None else [])
            rows=conn.execute(query,args).fetchall()
            for row in rows:
                playlist_id, customer, playlist = row
                if (not isinstance(customer,str) or not customer.strip()
                        or not isinstance(playlist,str) or not playlist.strip()
                        or len(customer)>200 or len(playlist)>200
                        or any(ord(ch)<32 for ch in customer+playlist)):
                    continue
                records.append(Expiry(customer,playlist,accepted[playlist_id]))
        return sorted(records,key=lambda x:(x.playlist.casefold(),x.day,
                                            x.customer.casefold()))
    finally:
        conn.close()
