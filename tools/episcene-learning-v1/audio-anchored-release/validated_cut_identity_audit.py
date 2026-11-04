#!/usr/bin/env python3
"""Read-only check: are three USER-verified playback cuts represented by analysis assets?

This deliberately does NOT import production code, fetch provider media, inspect
customer playlist credentials, write marker approvals or claim that a series
title/season/episode proves identical content across playlist providers.

Only local /var/lib/epimediahub/provisioning.db is examined. A missing main
playlist entry is NOT a problem with playback; it means that this DB cannot
verify the playback-to-analysis cut correspondence.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

DB=Path("/var/lib/epimediahub/provisioning.db")
TIME_TOLERANCE_MS=2000
DURATION_TOLERANCE_MS=1500
SCAN_LIMIT=5000

@dataclass(frozen=True)
class Known:
    name: str
    playlist_id: int
    season: int
    episode: int
    kind: str
    start_ms: int
    end_ms: int

CONFIRMED = (
    Known("Navy CIS",8,13,4,"intro",133000,161000),
    Known("Navy CIS",8,13,9,"outro",2483000,2512000),
    Known("One Piece",10,20,895,"intro",0,117000),
)

def columns(con,table):
    return {r[1] for r in con.execute("PRAGMA table_info("+table+")")}

def show_name(name,label):
    """Title may find a *candidate*, but never prove same version."""
    text=" ".join((label or "").casefold().split())
    if name=="Navy CIS":
        return ("navy cis" in text or "ncis" in text)
    if name=="One Piece":
        return "one piece" in text
    return False

def label_expression(cols):
    fields=[c for c in ("series_title","series_name","title","name") if c in cols]
    if not fields: return "'' AS display_title"
    # Known constant metadata columns only, never stream URLs/credentials.
    return "COALESCE("+",".join("NULLIF("+c+",'')" for c in fields)+",'') AS display_title"

def load_candidates(con,cols,item):
    query=(
        "SELECT asset_key,playlist_id,source_key,duration_ms,season,episode,"
        +label_expression(cols)+" FROM skip_assets "
        "WHERE season=? AND episode=? AND media_type='episode' "
        "LIMIT ?"
    )
    rows=con.execute(query,(item.season,item.episode,SCAN_LIMIT+1)).fetchall()
    if len(rows)>SCAN_LIMIT:
        return None
    return [x for x in rows if show_name(item.name,x["display_title"])]

def evidence_record(con,item,asset):
    row=con.execute("""
       SELECT COUNT(*) FROM skip_records
       WHERE asset_key=? AND segment_type=?
         AND ABS(start_ms-?)<=?
         AND ABS(end_ms-?)<=?
         AND ABS(duration_ms-?)<=?
         AND status NOT IN ('disabled','rejected','superseded')
    """,(asset["asset_key"],item.kind,item.start_ms,TIME_TOLERANCE_MS,
         item.end_ms,TIME_TOLERANCE_MS,asset["duration_ms"],
         DURATION_TOLERANCE_MS)).fetchone()
    return int(row[0])

def cache_window(con,item,asset):
    return con.execute("""
        SELECT offset_ms,step_ms,words_json,length_ms
        FROM skip_auto_windows
        WHERE asset_key=? AND kind=? AND duration_ms=?
        ORDER BY created_at DESC LIMIT 1
    """,(asset["asset_key"],item.kind,asset["duration_ms"])).fetchone()

def content_window_identical(a,b):
    """Exact cached window equality is strong *segment* evidence, not full-cut proof."""
    if a is None or b is None:
        return False
    if not (isinstance(a["words_json"],str)
            and isinstance(b["words_json"],str)
            and len(a["words_json"]) <= 256_000
            and len(b["words_json"]) <= 256_000):
        return False
    if not (a["step_ms"]==b["step_ms"]
            and a["offset_ms"]==b["offset_ms"]
            and a["length_ms"]==b["length_ms"]):
        return False
    try:
        left=json.loads(a["words_json"])
        right=json.loads(b["words_json"])
    except (ValueError,TypeError):
        return False
    if not (isinstance(left,list) and isinstance(right,list)
            and len(left)>120 and len(left)<=10000):
        return False
    return left==right

def compare(analysis,other,original_cache,other_cache):
    duration_close=(isinstance(analysis["duration_ms"],int)
                    and isinstance(other["duration_ms"],int)
                    and abs(analysis["duration_ms"]-other["duration_ms"])
                    <=DURATION_TOLERANCE_MS)
    same_asset=analysis["asset_key"]==other["asset_key"]
    same_source=bool(analysis["source_key"]) and analysis["source_key"]==other["source_key"]
    same_cache=content_window_identical(original_cache,other_cache)
    if same_asset and duration_close and same_cache:
        return "MATCHING_ASSET_AND_CACHED_AUDIO_WINDOW"
    if same_source and duration_close and same_cache:
        return "MATCHING_SOURCE_AND_CACHED_AUDIO_WINDOW"
    if same_cache and duration_close:
        return "MATCHING_CACHED_AUDIO_WINDOW_ONLY"
    if same_asset and duration_close:
        return "SAME_ASSET_KEY_BUT_NO_AUDIO_PROOF"
    if same_source and duration_close:
        return "SAME_SOURCE_AND_DURATION_NO_AUDIO_PROOF"
    if duration_close:
        return "SAME_TITLE_EPISODE_AND_DURATION_ONLY"
    return "TITLE_EPISODE_ONLY_OR_DIFFERENT_DURATION"

def audit(con,item):
    cols=columns(con,"skip_assets")
    candidates=load_candidates(con,cols,item)
    if candidates is None:
        return {"result":"TOO_MANY_ROWS_TO_IDENTIFY_SAFELY"}
    analysis=[a for a in candidates if a["playlist_id"]==item.playlist_id]
    others=[a for a in candidates if a["playlist_id"]!=item.playlist_id]
    matched_records=sum(evidence_record(con,item,a) for a in analysis)
    analysis_cache={a["asset_key"]:cache_window(con,item,a) for a in analysis}
    with_cache=sum(w is not None for w in analysis_cache.values())
    comparisons={}
    for a in analysis[:10]:
        for other in others[:50]:
            w=cache_window(con,item,other)
            status=compare(a,other,analysis_cache[a["asset_key"]],w)
            comparisons[status]=comparisons.get(status,0)+1
    status=(
        "NO_ANALYSIS_ASSET" if not analysis else
        "NO_MATCHING_ANALYSIS_MARKER" if not matched_records else
        "NO_OTHER_PLAYLIST_ASSET_IN_THIS_DB" if not others else
        "CANDIDATE_CORRELATIONS_ONLY_NOT_APPROVED"
    )
    return {
        "result":status,
        "analysis_asset_count":len(analysis),
        "matching_analysis_marker_rows":matched_records,
        "analysis_audio_windows_available":with_cache,
        "other_playlist_candidate_count":len(others),
        "other_playlist_ids":sorted(set(int(a["playlist_id"]) for a in others))
                               if len(others)<15 else "more_than_14_candidates",
        "evidence_comparisons":dict(sorted(comparisons.items())),
        "playback_to_analysis_fully_verified":False,
    }

def run(path=DB):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("STOP: Production DB missing or symbolic link")
    with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=15) as con:
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA query_only=ON")
        required={
            "skip_assets":{"asset_key","playlist_id","source_key","duration_ms","season","episode","media_type"},
            "skip_records":{"asset_key","segment_type","start_ms","end_ms","duration_ms","status"},
            "skip_auto_windows":{"asset_key","kind","duration_ms","offset_ms",
                                 "step_ms","words_json","length_ms","created_at"},
        }
        for table,needed in required.items():
            if not needed<=columns(con,table):
                raise RuntimeError("STOP: Unrecognized schema: "+table)
        con.execute("BEGIN")
        result={}
        for item in CONFIRMED:
            key=f"{item.name} S{item.season} E{item.episode} {item.kind}"
            result[key]=audit(con,item)
        con.rollback()
    return result

if __name__=="__main__":
    print("EPISCENE – 3 NUTZERBESTAETIGTE MARKER / IDENTITAETSABGLEICH (READ ONLY)")
    print("Keine Titelzuordnung als Inhaltsbeweis. Keine Freigaben, keine Worker-Aenderungen.")
    print(json.dumps(run(),ensure_ascii=False,indent=2))
