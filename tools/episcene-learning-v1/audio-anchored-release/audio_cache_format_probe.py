#!/usr/bin/env python3
"""Read-only bounded metadata survey of EpiScene's *actual* audio cache format.

No media, no production imports, no writes, no identifiers, no fingerprint
content output, no service/worker interactions. This is format discovery, NOT
a match or release diagnosis.
"""
from __future__ import annotations

from collections import Counter
import json
import math
import sys
from pathlib import Path
import sqlite3

DB = Path("/var/lib/epimediahub/provisioning.db")
PLAYLISTS = ((8, "4K ANALYSE"), (10, "THE BEST"))
KINDS = ("intro", "outro")
SAMPLES_PER_GROUP = 24
MAX_JSON_CHARS = 1_000_000

def structure(value):
    """Return a structural category and bounded element count, not contents."""
    if value is None: return ("NULL", 0)
    if not isinstance(value, str): return ("NON_TEXT", 0)
    if len(value) > MAX_JSON_CHARS: return ("TOO_LARGE_TO_PARSE", 0)
    try:
        decoded = json.loads(value)
    except (ValueError, TypeError):
        return ("NOT_JSON", 0)
    if isinstance(decoded, list):
        if not decoded: return ("LIST_EMPTY", 0)
        if all(type(x) is int for x in decoded): return ("LIST_INTEGER", len(decoded))
        if all(type(x) is str for x in decoded): return ("LIST_STRING", len(decoded))
        return ("LIST_MIXED", len(decoded))
    if isinstance(decoded, dict): return ("OBJECT", len(decoded))
    if isinstance(decoded, str): return ("STRING", len(decoded))
    return ("OTHER", 0)

def bucket_size(chars):
    if not isinstance(chars, int): return "unknown"
    if chars < 8640: return "<8640"
    if chars < 50000: return "8640-49999"
    if chars < 250000: return "50000-249999"
    return ">=250000"

def numeric_metadata(value):
    """Count numerical metadata only; nonnumeric SQLite text is never shown."""
    if type(value) in (int,float):
        numeric=float(value)
        if math.isfinite(numeric): return numeric
    if type(value) is str and 0 < len(value) <= 24:
        try:
            numeric=float(value.strip())
            if math.isfinite(numeric): return numeric
        except ValueError:
            pass
    return None


def meta_type(value):
    if value is None:return "NULL"
    if type(value) is int:return "INTEGER"
    if type(value) is float:return "REAL"
    if type(value) is str:
        return "TEXT_NUMERIC" if numeric_metadata(value) is not None else "TEXT_NONNUMERIC"
    return "OTHER"


def step_summary(step_types, values, ratios):
    def bounds(data):
        if not data:return None
        return dict(min=round(min(data),3), max=round(max(data),3),
                    median=round(sorted(data)[len(data)//2],3))
    return dict(
        types=dict(sorted(step_types.items())),
        numeric_step_ms=bounds(values),
        inferred_length_ms_per_word=bounds(ratios),
        note="Length/word ratio is diagnostic, NOT an authoritative fingerprint step.",
    )


def survey(con, playlist_id, kind):
    rows = con.execute("""
        SELECT w.step_ms,w.length_ms,w.offset_ms,w.words_json,
               a.duration_ms
        FROM skip_auto_windows w
        JOIN skip_assets a ON a.asset_key=w.asset_key
        WHERE a.playlist_id=? AND w.kind=? AND w.duration_ms=a.duration_ms
        ORDER BY w.created_at DESC,w.rowid DESC LIMIT ?
    """, (playlist_id,kind,SAMPLES_PER_GROUP)).fetchall()
    steps, lengths, shapes, sizes, counts, inconsistent = (
        Counter(), Counter(),Counter(),Counter(),Counter(),0)
    step_types=Counter()
    step_values=[]
    inferred_steps=[]
    for step, length, offset, words, duration in rows:
        step_types[meta_type(step)]+=1
        numeric=numeric_metadata(step)
        if numeric is not None:step_values.append(numeric)
        step = step if type(step) is int and 0 <= step <= 100000 else "unknown"
        steps[step] += 1
        lengths["<15s" if type(length) is int and length < 15000
                else "15-60s" if type(length) is int and length <= 60000
                else "60s-5m" if type(length) is int and length <= 300000
                else ">5m_or_invalid"] += 1
        shape,n=structure(words)
        shapes[shape]+=1
        sizes[bucket_size(len(words) if isinstance(words,str) else None)]+=1
        if n:
            counts["<720" if n < 720 else "720-1999" if n < 2000
                   else "2000-9999" if n < 10000 else ">=10000"] += 1
            if type(length) in (int,float) and math.isfinite(length) and length > 0:
                inferred_steps.append(length/n)
        if not (type(offset) is int and type(duration) is int
                and type(length) is int and 0<=offset
                and 0<length and offset+length<=duration+2000):
            inconsistent+=1
    return {
        "sampled": len(rows),
        "step_ms": dict(sorted(steps.items(),key=lambda kv:str(kv[0]))),
        "step_metadata": step_summary(step_types,step_values,inferred_steps),
        "window_duration": dict(sorted(lengths.items())),
        "json_shape": dict(sorted(shapes.items())),
        "json_char_length": dict(sorted(sizes.items())),
        "fingerprint_word_count": dict(sorted(counts.items())),
        "inconsistent_window_bounds": inconsistent,
    }

def run(path=DB):
    if not path.is_file() or path.is_symlink():
        raise RuntimeError("Production DB missing or symbolic link")
    with sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=15) as con:
        con.execute("PRAGMA query_only=ON")
        required = {
            "skip_auto_windows": {"asset_key","kind","step_ms","length_ms",
                                  "offset_ms","words_json","duration_ms","created_at"},
            "skip_assets": {"asset_key","playlist_id","duration_ms"},
        }
        for table, names in required.items():
            cols={r[1] for r in con.execute("PRAGMA table_info("+table+")")}
            if not names <= cols:
                raise RuntimeError("Unexpected database cache schema: "+table)
        con.execute("BEGIN")
        report={}
        for pid,name in PLAYLISTS:
            for kind in KINDS:
                report[f"{name} / {kind}"]=survey(con,pid,kind)
        con.rollback()
    return report

if __name__ == "__main__":
    report=run()
    if sys.argv[1:]==["--step-only"]:
        print("EPISCENE AUDIO CACHE – NUR ZEITABSTAND-METADATEN / READ ONLY")
        print(json.dumps({name:part["step_metadata"] for name,part in report.items()},
                         ensure_ascii=False,indent=2))
    elif not sys.argv[1:]:
        print("EPISCENE – AUDIO-CACHE-SPEICHERFORMAT / READ ONLY")
        print("Nur anonymisierte Strukturwerte, keine Fingerprints/IDs, keine Änderungen.")
        print(json.dumps(report,ensure_ascii=False,indent=2))
    else:
        raise SystemExit("Unsupported argument")
