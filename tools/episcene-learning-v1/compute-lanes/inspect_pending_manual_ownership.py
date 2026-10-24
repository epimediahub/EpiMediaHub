#!/usr/bin/env python3
"""EpiScene manual-label triage for normal vs analysis playlists.

Read-only SQLite inspection. Emits aggregate reason counts only; never prints
user/customer/playlist IDs (apart from public analysis IDs), episode titles,
source URLs, marker times, stream IDs, provider configurations or credentials.
Does not import production modules or contact IPTV providers.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3

DB = Path("/var/lib/epimediahub/provisioning.db")
SOURCE = Path("/opt/epimediahub/provisioning/skip_markers.py")
RELEASE = Path("/opt/episcene-learning/safe_release_rollout.py")
ANALYSIS_IDS = (8, 10)


def ro_db(path=DB):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Production DB unavailable")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                         uri=True, timeout=8)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def columns(db, table):
    if table not in ("skip_records", "skip_assets", "devices",
                     "customers", "customer_playlists", "skip_analysis_sources"):
        return set()
    return {row["name"] for row in db.execute("PRAGMA table_info("+table+")")}


def summary(db):
    needed = {
        "skip_records": {"id", "asset_key", "source", "status", "device_id",
                         "customer_id", "source_key", "media_type", "season",
                         "episode", "title", "duration_ms", "segment_type"},
        "skip_assets": {"asset_key", "playlist_id", "source_key",
                        "media_type", "season", "episode", "title", "duration_ms"},
        "devices": {"id", "customer_id", "enabled"},
        "customers": {"id", "enabled"},
        "customer_playlists": {"id", "customer_id"},
    }
    missing = sorted(name for name, fields in needed.items()
                     if not fields.issubset(columns(db, name)))
    if missing:
        return {"status": "SCHEMA_NEEDS_REVIEW",
                "affected_table_names": missing,
                "changes_made": 0}
    db.execute("BEGIN")
    rows = db.execute("""
        SELECT r.id,r.asset_key,r.device_id,r.customer_id,
               r.source_key,r.media_type,r.season,r.episode,r.title,
               r.duration_ms,r.segment_type,
               a.playlist_id,a.source_key AS asset_source,
               a.media_type AS asset_type,a.season AS asset_season,
               a.episode AS asset_episode,a.title AS asset_title,
               a.duration_ms AS asset_duration,
               d.id AS device_exists,d.customer_id AS device_owner,
               d.enabled AS device_enabled,
               c.enabled AS customer_enabled,
               p.id AS playlist_exists,
               p.customer_id AS playlist_owner
        FROM skip_records r
        LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
        LEFT JOIN devices d ON d.id=r.device_id
        LEFT JOIN customers c ON c.id=r.customer_id
        LEFT JOIN customer_playlists p ON p.id=a.playlist_id
        WHERE r.status='pending' AND r.source='device'
    """).fetchall()
    counts = defaultdict(Counter)
    labels = defaultdict(Counter)
    for r in rows:
        kind = "analysis" if r["playlist_id"] in ANALYSIS_IDS else "other_or_unmapped"
        c = counts[kind]
        c["total"] += 1
        if r["playlist_id"] is None:
            c["missing_asset_registration"] += 1
        elif r["playlist_exists"] is None:
            c["missing_playlist_mapping"] += 1
        elif r["playlist_id"] not in ANALYSIS_IDS:
            c["normal_playlist_without_analysis_registration"] += 1
        if r["device_exists"] is None:
            c["device_reference_missing"] += 1
        elif r["device_enabled"] != 1:
            c["device_disabled"] += 1
        if r["customer_id"] is None:
            c["marker_customer_missing"] += 1
        if r["customer_enabled"] != 1:
            c["customer_disabled_or_missing"] += 1
        if (r["device_owner"] is not None and r["customer_id"] is not None
                and r["device_owner"] != r["customer_id"]):
            c["device_owner_mismatch"] += 1
        if (r["playlist_owner"] is not None and r["customer_id"] is not None
                and r["playlist_owner"] != r["customer_id"]):
            c["playlist_owner_mismatch"] += 1
        if (r["playlist_exists"] is not None and
                r["device_exists"] is not None and
                r["device_enabled"] == 1 and r["customer_enabled"] == 1 and
                r["device_owner"] == r["customer_id"] ==
                r["playlist_owner"]):
            c["all_ownership_checks_pass"] += 1
        if r["playlist_id"] is not None:
            keys = ("source_key", "media_type", "season", "episode")
            matching = all(r[key] == r[{
                "source_key":"asset_source", "media_type":"asset_type",
                "season":"asset_season", "episode":"asset_episode"}[key]]
                for key in keys)
            matching &= (isinstance(r["title"], str) and
                         isinstance(r["asset_title"], str) and
                         r["title"].strip().casefold() ==
                         r["asset_title"].strip().casefold())
            matching &= (type(r["duration_ms"]) is int and
                         type(r["asset_duration"]) is int and
                         abs(r["duration_ms"]-r["asset_duration"]) <= 500)
            c["matching_asset_metadata" if matching
              else "asset_metadata_mismatch"] += 1
        segment = r["segment_type"]
        if segment in ("intro", "recap", "outro"):
            labels[kind][segment] += 1
        else:
            labels[kind]["unrecognized_kind"] += 1
    return {"status": "READ_ONLY_SUCCESS",
            "pending_manual": {group: dict(c) for group, c in counts.items()},
            "segment_types": {group: dict(c) for group, c in labels.items()},
            "reason_counts_overlap": True,
            "playlist_names_exported": False,
            "customer_or_device_data_exported": False,
            "production_writes": 0, "provider_requests": 0}


def source_fingerprints(files=None):
    files = files or {"manual_handler": SOURCE, "safe_release": RELEASE}
    result = {}
    for name, path in files.items():
        try:
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2_000_000:
                result[name] = {"status": "unavailable"}
                continue
            raw = path.read_bytes()
            result[name] = {
                "status": "present",
                "sha256_prefix": hashlib.sha256(raw).hexdigest()[:16],
                "has_manual_authenticator": (
                    b"verified_manual_submission" in raw
                    if name == "manual_handler" else None)}
        except OSError:
            result[name] = {"status": "unreadable"}
    return result


def main():
    try:
        with ro_db() as db:
            result = summary(db)
        result["source_fingerprints"] = source_fingerprints()
        print(json.dumps(result, indent=2, sort_keys=True))
    except (OSError, sqlite3.Error, ValueError):
        print(json.dumps({"status": "READ_ONLY_STOP",
                          "reason": "DATABASE_UNAVAILABLE_OR_UNEXPECTED_SCHEMA",
                          "production_writes": 0}))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
