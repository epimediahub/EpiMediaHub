#!/usr/bin/env python3
"""Aggregate read-only EpiScene auto-release opportunities by unique record.

This is a DIAGNOSTIC, not an approval engine. In particular,
AUTO_CONFIRMED evidence is not sufficient to bypass skip_release.accept_pending.
No customer names, URLs, asset keys, record IDs, timestamps or source text are
printed. Distinguishes confirmed-but-pending candidates from repeated blocker
events in the daily logs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import sqlite3

DATABASE = Path("/var/lib/epimediahub/provisioning.db")
LANES = (8, 10)
KINDS = ("intro", "recap", "outro")
MACHINE = ("audio", "chapter", "theintrodb", "audio_repetition",
           "auto_audio", "episcene")


def table_exists(con, name):
    return con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,)).fetchone() is not None


def columns(con, name):
    return {row[1] for row in con.execute("PRAGMA table_info("+name+")")}


def require_schema(con):
    expected = {
        "skip_records": {"id", "asset_key", "status", "source", "segment_type",
                         "duration_ms"},
        "skip_assets": {"asset_key", "playlist_id"},
        "skip_auto_evidence": {"record_id", "evidence_json"},
        "skip_auto_blocks": {"asset_key", "kind", "duration_ms"},
    }
    for name, required in expected.items():
        if not table_exists(con, name) or not required <= columns(con, name):
            raise RuntimeError("EXPECTED_SCHEMA_UNAVAILABLE:"+name)


def normalized_evidence(raw):
    try:
        value = json.loads(raw or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def release_config(con):
    state = {p: [] for p in LANES}
    for table, role in (("skip_analysis_sources", "analysis_source"),
                        ("skip_auto_settings", "auto_discovery"),
                        ("skip_release_settings", "automatic_release")):
        if not table_exists(con, table) or not {"playlist_id", "enabled"} <= columns(con, table):
            for pid in LANES:
                state[pid].append(role+":UNKNOWN")
            continue
        enabled = {}
        for pid, value in con.execute(
            "SELECT playlist_id,MAX(enabled) FROM "+table+
            " WHERE playlist_id IN (8,10) GROUP BY playlist_id"
        ):
            enabled[pid] = value
        for pid in LANES:
            state[pid].append(role+(":ON" if enabled.get(pid)==1 else ":OFF_OR_ABSENT"))
    return state


def analyze(con):
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    if not con.in_transaction:
        con.execute("BEGIN")
    require_schema(con)
    configs = release_config(con)
    human_col = ("e.human_review" if "human_review" in
                 columns(con, "skip_auto_evidence") else "0")
    source_args = ",".join("?" for _ in MACHINE)
    rows = con.execute(f"""
        SELECT r.id, r.asset_key, a.playlist_id, r.segment_type,
               r.duration_ms, e.evidence_json, {human_col} AS human_review
        FROM skip_records r
        JOIN skip_assets a ON a.asset_key=r.asset_key
        LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
        WHERE a.playlist_id IN (8,10) AND r.status='pending'
          AND r.segment_type IN ('intro','recap','outro')
          AND r.source IN ({source_args})
        ORDER BY r.id
    """, MACHINE)
    grouped = {}
    for row in rows:
        grouped.setdefault(row["id"], []).append(row)
    blocks = defaultdict(list)
    for row in con.execute("""
        SELECT asset_key,kind,duration_ms FROM skip_auto_blocks
        WHERE kind IN ('intro','recap','outro')
    """):
        blocks[(row[0], row[1])].append(row[2])
    output = {}
    for pid in LANES:
        filtered = [records for records in grouped.values()
                    if records[0]["playlist_id"] == pid]
        reasons, kinds = Counter(), {kind: Counter() for kind in KINDS}
        distinct_assets = set()
        preconfirmed_assets = set()
        for matches in filtered:
            row = matches[0]
            distinct_assets.add(row["asset_key"])
            values = {(r["evidence_json"], r["human_review"]) for r in matches}
            if len(values)>1:
                reason = "INCONSISTENT_EVIDENCE_ROWS"
            else:
                evidence = normalized_evidence(row["evidence_json"])
                decision = evidence.get("decision")
                decision = decision if isinstance(decision, dict) else {}
                blocked = any(
                    abs((duration or 0)-(row["duration_ms"] or 0))<=2000
                    for duration in blocks.get(
                        (row["asset_key"], row["segment_type"]), ())
                )
                if blocked:
                    reason = "EXPLICIT_BLOCK"
                elif row["human_review"]:
                    reason = "AWAITING_HUMAN_REVIEW"
                elif evidence.get("audio_visual_disagreement") is True:
                    reason = "AUDIO_VISUAL_DISAGREEMENT"
                elif decision.get("status") == "NO_MATCH":
                    reason = "EXPLICIT_VISUAL_NO_MATCH"
                elif decision.get("status") == "AUTO_CONFIRMED":
                    reason = "VISUALLY_CONFIRMED_BUT_STILL_PENDING"
                    preconfirmed_assets.add(row["asset_key"])
                elif (evidence.get("episcene_required") is True or
                      evidence.get("method") == "episcene_consensus"):
                    reason = "VISUAL_EVIDENCE_NOT_CONFIRMED"
                else:
                    reason = "OTHER_PRODUCTION_GATE_OR_EVIDENCE"
            reasons[reason] += 1
            kinds[row["segment_type"]][reason] += 1
        output[str(pid)] = {
            "unique_pending_machine_markers": len(filtered),
            "unique_pending_assets": len(distinct_assets),
            "unique_visually_confirmed_pending_assets": len(preconfirmed_assets),
            "marker_blocker_categories": dict(sorted(reasons.items())),
            "by_kind": {kind: dict(sorted(counts.items()))
                        for kind, counts in kinds.items()},
            "settings": configs[pid],
        }
    return {
        "mode": "EPISCENE_UNIQUE_AUTO_RELEASE_FUNNEL_READ_ONLY",
        "analysis_playlists": output,
        "no_real_gate_simulated": True,
        "confirmed_but_pending_is_not_safe_to_auto_approve_without_original_gates": True,
        "production_db_modified": False,
        "marker_approvals_triggered": 0,
        "provider_requests": 0,
        "customer_identifiers_exported": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DATABASE)
    args = parser.parse_args()
    if args.database.is_symlink() or not args.database.is_file():
        raise SystemExit("STOP: DATABASE_UNAVAILABLE_OR_SYMLINK")
    with sqlite3.connect(
        args.database.resolve().as_uri()+"?mode=ro",
        uri=True, timeout=15
    ) as con:
        print(json.dumps(analyze(con), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
