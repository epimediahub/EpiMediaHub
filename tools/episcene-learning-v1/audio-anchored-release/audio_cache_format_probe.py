#!/usr/bin/env python3
"""Read-only bounded metadata survey of EpiScene's *actual* audio cache format.

No media, no production imports, no writes, no identifiers, no fingerprint
content output, no service/worker interactions. This is format discovery, NOT
a match or release diagnosis.
"""
from __future__ import annotations

from collections import Counter
import json
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
    for step, length, offset, words, duration in rows:
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
        if not (type(offset) is int and type(duration) is int
                and type(length) is int and 0<=offset
                and 0<length and offset+length<=duration+2000):
            inconsistent+=1
    return {
        "sampled": len(rows),
        "step_ms": dict(sorted(steps.items(),key=lambda kv:str(kv[0]))),
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
    print("EPISCENE – AUDIO-CACHE-SPEICHERFORMAT / READ ONLY")
    print("Nur anonymisierte Strukturwerte, keine Fingerprints/IDs, keine Änderungen.")
    print(json.dumps(run(),ensure_ascii=False,indent=2))
