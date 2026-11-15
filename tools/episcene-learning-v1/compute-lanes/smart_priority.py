#!/usr/bin/env python3
"""Read-only EpiScene priority proposals from authenticated manual feedback.

This is NOT a worker and never accesses IPTV streams, changes queue statuses,
or exports customer/playback credentials. A production scheduler must integrate
the proposals only after a separate version/contract gate passes.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3

PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
FEEDBACK = Path("/var/lib/episcene-learning/reference-round-40/feedback.sqlite3")
ANALYSIS_IDS = (8, 10)
TRUSTED = ("device_authenticated_direct", "admin_reviewed_machine")
MAX_PER_PLAYLIST = 2
MAX_DISTANCE = 4
MAX_MARKS_READ = 2000
MAX_EPISODES_PER_SOURCE = 32


def normalized(value):
    return " ".join(str(value or "").casefold().split())


def utc(value):
    try:
        v = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return v.astimezone(timezone.utc) if v.tzinfo else None
    except (TypeError, ValueError, OverflowError):
        return None


def connect_readonly(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Trusted local database unavailable")
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=8)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def check_schema(db, expected):
    for table, required in expected.items():
        existing = {r["name"] for r in db.execute("PRAGMA table_info(" + table + ")")}
        if not required <= existing:
            raise RuntimeError("Required EpiScene schema unavailable: " + table)


def proposals(production, feedback, *, now=None, days=14,
              max_per_playlist=MAX_PER_PLAYLIST, max_distance=MAX_DISTANCE):
    if max_per_playlist not in (1, 2) or not 1 <= max_distance <= 4:
        raise ValueError("Unsafe priority budget")
    now = now or datetime.now(timezone.utc)
    if not 1 <= days <= 30:
        raise ValueError("Unsafe feedback lookback")
    check_schema(feedback, {
        "feedback_versions": {"marker_id", "asset_key", "playlist_id", "season",
                              "episode", "kind", "decision", "active", "reviewed_at",
                              "provenance"},
    })
    check_schema(production, {
        "skip_records": {"id", "asset_key", "segment_type", "status"},
        "skip_assets": {"asset_key", "playlist_id", "title", "season", "episode",
                        "media_type"},
        "skip_jobs": {"id", "asset_key", "status"},
    })
    feedback.execute("BEGIN")
    production.execute("BEGIN")
    cutoff = now - timedelta(days=days)
    recent = feedback.execute("""
        SELECT marker_id,asset_key,playlist_id,season,episode,kind,reviewed_at
        FROM feedback_versions
        WHERE active=1 AND decision='positive'
          AND provenance IN (?,?)
        ORDER BY reviewed_at DESC,marker_id DESC LIMIT ?
    """, (*TRUSTED, MAX_MARKS_READ)).fetchall()
    families = defaultdict(set)
    checked = 0
    for f in recent:
        timestamp = utc(f["reviewed_at"])
        if timestamp is None or timestamp < cutoff or timestamp > now + timedelta(minutes=5):
            continue
        if (f["kind"] not in ("intro", "recap", "outro") or
                type(f["season"]) is not int or type(f["episode"]) is not int or
                f["season"] < 1 or f["episode"] < 1):
            continue
        row = production.execute("""
            SELECT a.title,a.playlist_id,a.season,a.episode,a.media_type,
                   r.status,r.segment_type
            FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
            WHERE r.id=? AND r.asset_key=? LIMIT 1
        """, (f["marker_id"], f["asset_key"])).fetchone()
        if not row or (row["status"] != "approved" or
                       row["segment_type"] != f["kind"] or
                       row["playlist_id"] != f["playlist_id"] or
                       row["season"] != f["season"] or
                       row["episode"] != f["episode"] or
                       row["media_type"] != "episode"):
            continue
        title = normalized(row["title"])
        if not title or len(title) > 180:
            continue
        # This only influences priority; it never transfers a timestamp
        # between provider cuts or creates a new analysis source.
        families[(title, f["season"])].add(f["episode"])
        checked += 1

    chosen = []
    counts = defaultdict(int)
    for (title, season), watched in sorted(families.items()):
        if len(chosen) >= max_per_playlist * len(ANALYSIS_IDS):
            break
        # Queue only episodes following observed manual marks (not past seasons).
        newest = max(watched)
        for playlist_id in ANALYSIS_IDS:
            if counts[playlist_id] >= max_per_playlist:
                continue
            candidates = production.execute("""
                SELECT j.id,a.episode,a.title
                  FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
                 WHERE j.status='queued' AND a.media_type='episode'
                   AND a.playlist_id=? AND a.season=?
                   AND a.episode>? AND a.episode<=?
                 ORDER BY a.episode,j.id LIMIT ?
            """, (playlist_id, season, newest, newest + max_distance,
                  MAX_EPISODES_PER_SOURCE)).fetchall()
            for row in candidates:
                if counts[playlist_id] >= max_per_playlist:
                    break
                if normalized(row["title"]) != title:
                    continue
                chosen.append({
                    "job_id": int(row["id"]), "playlist_id": playlist_id,
                    "episode": int(row["episode"]), "distance": row["episode"] - newest,
                })
                counts[playlist_id] += 1
    chosen.sort(key=lambda r: (r["distance"], r["playlist_id"], r["job_id"]))
    return {
        "mode": "READ_ONLY_SMART_PRIORITY_ADVISORY",
        "candidate_jobs": chosen,
        "authenticated_feedback_seen": checked,
        "series_seasons_seen": len(families),
        "analysis_streams_opened": 0, "queue_mutations": 0,
        "automatic_worker_install": False,
        "limit_per_analysis_playlist": max_per_playlist,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", type=Path, default=PRODUCTION)
    parser.add_argument("--feedback", type=Path, default=FEEDBACK)
    args = parser.parse_args()
    with connect_readonly(args.production) as prod, connect_readonly(args.feedback) as fb:
        result = proposals(prod, fb)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
