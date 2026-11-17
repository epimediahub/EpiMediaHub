#!/usr/bin/env python3
"""Retry Snowfall's current trusted outros and check the requeued episodes."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from contextlib import closing

sys.path[:0] = ["/opt/epimediahub/provisioning", "/opt/episcene-learning/unified"]

from analysis_identity import _asset_identity, _columns, _source_list
from bridge import Episode
from catalogue_sources import CatalogueSources
from skip_automation import (
    TRUSTED_ONLINE_METHOD,
    promote_trusted_online,
    trusted_online_markers,
)
from skip_release import accept_pending
from trusted_external import resolve_external
from trusted_external_sync import CACHE, CATALOGUE_CACHE_TTL, PRODUCTION

SERIES_IDS = {"imdb_id": "tt6439752", "tvdb_id": 328092, "tmdb_id": 71694}
OUTROS = (2, 4, 7, 8)
REQUEUED = (1, 2, 3, 7)
ANALYSIS_UNIT = "epimediahub-skip-analysis.service"
WORKER_UNIT = "epimediahub-analysis-worker.service"


def assets_for_snowfall(db):
    sources = _source_list(db, _columns(db, "skip_assets"))
    matched = defaultdict(list)
    for asset in db.execute("""
        SELECT * FROM skip_assets WHERE playlist_id=8 AND media_type='episode'
        AND ((season=5 AND episode IN (2,4,7,8)) OR
             (season=6 AND episode IN (1,2,3,7)))
    """):
        identity, status = _asset_identity(db, asset, sources)
        if status == "ok" and all(
            not identity[key] or identity[key] == value for key, value in SERIES_IDS.items()
        ):
            matched[asset["season"], asset["episode"]].append((asset, identity))
    return {key: matches[0] for key, matches in matched.items() if len(matches) == 1}


def keep_transaction(action, arg, *_):
    if action == sqlite3.SQLITE_TRANSACTION and arg == "COMMIT":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def retry_outro(db, asset):
    with db:
        db.execute("BEGIN IMMEDIATE")
        current = db.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                             (asset["asset_key"],)).fetchone()
        if current is None or dict(current) != dict(asset):
            return "Episodendaten haben sich geändert."
        key = asset["asset_key"]
        duration = asset["duration_ms"]
        rows = db.execute("""
            SELECT r.*, e.record_id AS evidence_id, e.evidence_json, e.human_review
            FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
            WHERE r.asset_key=? AND r.segment_type='outro' AND ABS(r.duration_ms-?)<=2000
        """, (key, duration)).fetchall()
        if any(row["status"] == "approved" and not row["disabled"] for row in rows):
            return "Abspann bereits freigegeben."
        if any(row["status"] in ("approved", "rejected") or row["human_review"]
               or (row["status"] == "pending" and row["source"] in ("device", "manual"))
               for row in rows):
            return "Beim vorhandenen Prüfentscheid belassen."
        if db.execute("""
            SELECT 1 FROM skip_auto_blocks WHERE asset_key=? AND kind='outro'
            AND ABS(duration_ms-?)<=2000 LIMIT 1
        """, (key, duration)).fetchone():
            return "Abspann-Sperre vorhanden."

        verified = {
            (marker["source"], marker["start_ms"], marker["end_ms"])
            for marker in trusted_online_markers(db, current)
            if marker["segment_type"] == "outro"
        }
        candidates = [
            row for row in rows
            if row["status"] == "superseded" and not row["disabled"]
            and row["source"] in ("introdb", "theintrodb")
            and row["duration_ms"] == duration
            and row["source_key"] == current["source_key"]
            and (row["season"], row["episode"]) == (current["season"], current["episode"])
            and (row["source"], row["start_ms"], row["end_ms"]) in verified
        ]
        if len(candidates) != 1:
            return "Kein eindeutiger, aktuell bestätigter früherer Online-Vorschlag."
        record = candidates[0]
        if record["evidence_id"] is None:
            return "Der Nachweis des früheren Vorschlags fehlt."
        evidence = json.loads(record["evidence_json"] or "{}")
        if not isinstance(evidence, dict):
            return "Der Nachweis des früheren Vorschlags ist ungültig."
        evidence["method"] = TRUSTED_ONLINE_METHOD

        db.execute("UPDATE skip_auto_evidence SET evidence_json=? WHERE record_id=?",
                   (json.dumps(evidence), record["id"]))
        db.execute("UPDATE skip_records SET status='pending' WHERE id=?",
                   (record["id"],))
        db.set_authorizer(keep_transaction)
        try:
            accept_pending(db, asset_key=key, trusted_online_only=True)
        finally:
            db.set_authorizer(None)
        decision = db.execute("SELECT status,disabled FROM skip_records WHERE id=?",
                              (record["id"],)).fetchone()
        if decision is None or decision["status"] != "approved" or decision["disabled"]:
            db.rollback()
            return "Reguläre Freigabe weiterhin ausstehend."
        return f"Abspann freigegeben ({record['source']})."


def valid_duration(value):
    return isinstance(value, int) and 30000 <= value <= 86400000


def requeued_states(db):
    targets = assets_for_snowfall(db)
    states = {}
    for number in REQUEUED:
        target = targets.get((6, number))
        if target is None:
            states[number] = ("Zuordnung fehlt", None)
            continue
        asset, _ = target
        row = db.execute(
            "SELECT status FROM skip_jobs WHERE asset_key=? ORDER BY id DESC LIMIT 1",
            (asset["asset_key"],),
        ).fetchone()
        states[number] = (row["status"] if row else "Job fehlt", asset["duration_ms"])
    return states


def report_scheduler(db):
    for unit in (ANALYSIS_UNIT, WORKER_UNIT):
        result = subprocess.run(
            ["systemctl", "show", unit, "-p", "ActiveState", "-p", "SubState", "-p", "Result"],
            capture_output=True, text=True, timeout=10,
        )
        state = " | ".join(result.stdout.splitlines())
        print(f"{unit} | {state or f'systemctl Exit {result.returncode}'}", flush=True)
    result = subprocess.run(
        ["systemctl", "list-timers", "--all", "--no-pager", "epimediahub-skip-analysis.timer"],
        capture_output=True, text=True, timeout=10,
    )
    print(result.stdout.strip() or f"Timerabfrage Exit {result.returncode}", flush=True)

    targets = assets_for_snowfall(db)
    expected = {a["asset_key"] for (season, _), (a, _) in targets.items() if season == 6}
    try:
        from skip_schedule import select_job

        with closing(sqlite3.connect(PRODUCTION.as_uri() + "?mode=ro", uri=True, timeout=5)) as readonly:
            readonly.row_factory = sqlite3.Row
            readonly.execute("PRAGMA query_only=ON")
            selected, _ = select_job(readonly, 8, parallel=True)
        if selected is None:
            print("4K ANALYSE | Scheduler liefert aktuell keinen Job.", flush=True)
        elif selected["asset_key"] in expected:
            print("4K ANALYSE | Nächster ausgewählter Job gehört zu Snowfall Staffel 6.", flush=True)
        else:
            print("4K ANALYSE | Scheduler wählt aktuell einen anderen Job.", flush=True)
    except (ImportError, sqlite3.Error, TypeError, ValueError, KeyError, IndexError) as error:
        print(f"4K ANALYSE | Nächster Job nicht auslesbar ({type(error).__name__}).", flush=True)


def watch_analysis(db, seconds=180):
    states = requeued_states(db)
    if any(status == "queued" and not valid_duration(duration) for status, duration in states.values()):
        result = subprocess.run(
            ["systemctl", "start", "--no-block", ANALYSIS_UNIT],
            capture_output=True, text=True, timeout=15,
        )
        print(f"Analyse angefordert | systemctl Exit {result.returncode}", flush=True)
        if result.returncode:
            seconds = 0

    previous = {}
    deadline = time.monotonic() + seconds
    while True:
        for number, (status, duration) in states.items():
            if previous.get(number) != (status, duration):
                print(f"S06E{number:02d} | {status} | {duration or 0} ms", flush=True)
        waiting = any(status in ("queued", "running") and not valid_duration(duration)
                      for status, duration in states.values())
        if not waiting:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        previous = states
        time.sleep(min(10, remaining))
        states = requeued_states(db)

    report_scheduler(db)


def check_requeued(db, asset, identity, fetch):
    job = db.execute("SELECT status,detail FROM skip_jobs WHERE asset_key=? ORDER BY id DESC LIMIT 1",
                     (asset["asset_key"],)).fetchone()
    state = job["status"] if job else "Job fehlt"
    duration = asset["duration_ms"]
    result = f"{state} | {duration or 0} ms"
    if state == "failed":
        failure = re.search(r"\bHTTP(?: Error)?\s+([45]\d\d)\b", job["detail"] or "", re.I)
        if failure:
            result += f" | HTTP {failure[1]}"
    if not valid_duration(duration):
        return result
    if fetch.rate_limited:
        return result + " | TheIntroDB meldet ein API-Limit."
    online = resolve_external(Episode.from_dict({**identity, **SERIES_IDS}), CACHE,
                              fetch=fetch, cache_ttl=CATALOGUE_CACHE_TTL)
    if fetch.rate_limited:
        return result + " | TheIntroDB meldet ein API-Limit."
    if not online["trusted_segments"]:
        states = ", ".join(f"{name}={status}" for name, status in online["sources"].items())
        return result + f" | Quellenstatus {states}"
    with db:
        count = promote_trusted_online(db, asset)
    return result + f" | {count} neue Online-Freigaben"


def main():
    parser = argparse.ArgumentParser(description="Snowfall-Marker und Analysejobs prüfen")
    parser.add_argument("--analyse", action="store_true",
                        help="Reguläre Analyse anstoßen und bis zu drei Minuten beobachten")
    args = parser.parse_args()
    with closing(sqlite3.connect(PRODUCTION.as_uri() + "?mode=rw", uri=True, timeout=15)) as db:
        db.row_factory = sqlite3.Row
        if args.analyse:
            try:
                watch_analysis(db)
            except (OSError, subprocess.TimeoutExpired) as error:
                print(f"Analyse | {type(error).__name__}", flush=True)
        assets = assets_for_snowfall(db)
        fetch = CatalogueSources(CACHE)
        print("Snowfall | Freigabe und Analyse", flush=True)
        scopes = ((6, REQUEUED),) if args.analyse else ((5, OUTROS), (6, REQUEUED))
        for season, episodes in scopes:
            for number in episodes:
                target = assets.get((season, number))
                status = "Eindeutige Zuordnung fehlt."
                try:
                    if target is not None:
                        asset, identity = target
                        status = (retry_outro(db, asset) if season == 5
                                  else check_requeued(db, asset, identity, fetch))
                except (sqlite3.Error, OSError, ValueError, TypeError) as error:
                    status = f"{type(error).__name__} | {error}"
                print(f"S{season:02d}E{number:02d}", status, sep=" | ", flush=True)


if __name__ == "__main__":
    main()
