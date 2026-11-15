#!/usr/bin/env python3
"""Compact, privacy-preserving ROOT CAUSE report for EpiScene visual release backlog.

Read-only. Uses the already tested release_gap_readonly and runtime_deadlines
modules. Never prints URLs, titles, individual marker IDs, asset keys, raw
logs, credentials, device IDs or customer details. No auto-approval, retries
or worker restarts.
"""
from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sqlite3

import release_gap_readonly as gaps
import runtime_deadlines as runtime

NAMES = {8: "4K ANALYSE (DE)", 10: "THE BEST (IT)"}
GAP_LABELS = {
    "NO_VISUAL_WINDOWS_FOR_ASSET_AND_KIND": "KEINE_GESPEICHERTEN_BILDFENSTER",
    "WINDOWS_BUT_WRONG_DURATION": "BILDFENSTER_MIT_FALSCHER_LAUFZEIT",
    "WINDOWS_BUT_NO_MATCHING_ASSET_REVISION": "BILDFENSTER_ALTE_ODER_FALSCHE_VERSION",
    "VISUAL_WINDOWS_BUT_FEWER_THAN_3_EPISODES": "ZU_WENIGE_UNABHAENGIGE_FOLGEN",
    "THREE_PLUS_EPISODES_HAVE_WINDOWS_CHECK_CONSENSUS_ENGINE": "BILDVERGLEICH_ODER_FREIGABEGATE_PRUEFEN",
}


def condense(gap_data, runtime_data):
    if gap_data.get("mode") != "EPISCENE_RELEASE_GAP_READ_ONLY":
        raise ValueError("unexpected_gap_report")
    if runtime_data.get("mode") != "EPISCENE_READ_ONLY_RUNTIME_TRIAGE":
        raise ValueError("unexpected_runtime_report")
    result = {
        "modus": "EPISCENE_VISUAL_ENGPASS_LESEND",
        "erlaubte_parallelitaet_anbieter": "unveraendert; max. 1 Stream je Analysequelle",
        "bewertung": {},
        "server_dienste": runtime_data.get("systemd", {}),
        "time_budget_vermutet_nicht_bewiesen": runtime_data.get("time_budget_suspected"),
        "keine_datenbank_aenderung": True,
        "keine_freigaben": True,
        "keine_dienstneustarts": True,
        "keine_anbieter_streams": True,
    }
    by_playlist = gap_data.get("window_to_pending_marker_gap", {})
    failures = gap_data.get("failed_jobs", {})
    job_info = runtime_data.get("jobs", {})
    source_phases = gap_data.get("pending_stage_by_playlist", {})
    cache = gap_data.get("visual_windows_by_playlist", {})
    for pid in (8, 10):
        key = str(pid)
        blockers = by_playlist.get(key, {})
        if not isinstance(blockers, dict):
            raise ValueError("unexpected_gap_blockers")
        counts = Counter({GAP_LABELS.get(k, "SONSTIGER_BELEGFEHLER"):int(v)
                          for k,v in blockers.items() if isinstance(v,int) and v>=0})
        dominant = sorted(counts.items(), key=lambda x:(-x[1],x[0]))
        total = sum(counts.values())
        detail = failures.get(key, {})
        kinds = gap_data.get("gap_by_segment_type", {}).get(key, {})
        result["bewertung"][key] = {
            "analysequelle": NAMES[pid],
            "betroffene_pending_markereintraege_im_bildpruefpfad": total,
            "haupt_engpaesse": dict(dominant),
            "groesster_nachpruefbarer_engpass": dominant[0][0] if dominant else "NICHT_ERMITTELT",
            "pending_phasen": source_phases.get(key, {}),
            "segmentarten_mit_engpaessen": {k:{
                GAP_LABELS.get(reason, "SONSTIGER_BELEGFEHLER"):n
                for reason,n in v.items() if reason in GAP_LABELS
            } for k,v in kinds.items()},
            "gespeicherte_bildfenster": cache.get(key, {}),
            "fehlgeschlagene_jobs_nach_ursache": detail.get("failed_reason_classes", {}),
            "letzte_24h_partial_jobs": job_info.get(key, {}).get("recent_partial"),
            "laenger_als_15_min_laufende_jobs": job_info.get(key, {}).get("running_over_15m"),
            "job_status_gesamtbestand": job_info.get(key, {}).get("status_counts", {}),
        }
    result["einschraenkung"] = (
        "Pending-Bildfenster-Zuordnung ist eine indikative Aggregation, "
        "keine Simulation der produktiven Freigabe, kein Beweis fuer "
        "wirklich vergleichbare Medienfassungen und keine Tagesrate. "
        "Bei 3+ Folgen muss der echte Konsens geprueft werden."
    )
    return result


def run(db_path=runtime.DB):
    db_path = Path(db_path)
    if db_path.is_symlink() or not db_path.is_file():
        raise RuntimeError("EXPECTED_PRODUCTION_DATABASE_NOT_AVAILABLE")
    with sqlite3.connect(db_path.resolve().as_uri()+"?mode=ro",
                         uri=True,timeout=20) as con:
        con.execute("PRAGMA query_only=ON")
        con.execute("BEGIN")
        gap_data = gaps.analyze(con)
    runtime_data = runtime.report(db_path)
    if (gap_data.get("production_db_modified") is not False or
            runtime_data.get("production_db_modified") is not False):
        raise RuntimeError("UNEXPECTED_READ_ONLY_CONTRACT")
    return condense(gap_data,runtime_data)


if __name__ == "__main__":
    try:
        print(json.dumps(run(), indent=2, ensure_ascii=False, sort_keys=True))
    except (OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        print("STOP: visual diagnostics could not verify running schema")
        raise SystemExit(2) from None
