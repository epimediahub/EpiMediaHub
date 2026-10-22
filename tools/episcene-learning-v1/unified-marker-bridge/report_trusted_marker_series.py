#!/usr/bin/env python3
"""Read-only EpiScene external marker report, with verified local series names.

Reads the trusted prefetch cache and only dedicated analysis playlists 8/10.
Never accesses customer playlists, changes databases, calls IPTV or external APIs.
Titles are matched by a canonical IMDb/TVDB/TMDb ID, season, episode and cut
duration, not by guessing from titles or provider names.
A cache hit does not prove a marker was displayed by an Android device.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
import json
import sqlite3
import sys
import time
from pathlib import Path

BASE = Path("/opt/episcene-learning/unified")
CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
PROD = Path("/var/lib/epimediahub/provisioning.db")
KINDS = frozenset(("intro", "recap", "outro"))
SOURCES = frozenset(("introdb", "theintrodb"))
IDS = ("imdb_id", "tvdb_id", "tmdb_id")
CUT_TOLERANCE_MS = 1500
PLAYLISTS = {8: "4K ANALYSE", 10: "THE BEST"}


def ro(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError("Expected an existing regular, non-symlink database")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=6)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only=ON")
    return conn


def accepted_entries(cache):
    output = []
    total = 0
    for row in cache.execute("SELECT identity,response,expires_at FROM trusted_external_cache"):
        total += 1
        try:
            key, data = json.loads(row["identity"]), json.loads(row["response"])
            if (not isinstance(key, list) or len(key) != 7 or
                    key[3] != "default" or not isinstance(data, dict)):
                continue
            ids = dict(zip(IDS, key[:3]))
            season, episode, duration = map(int, key[4:7])
            if not (0 <= season <= 100 and 1 <= episode <= 2000 and
                    30000 <= duration <= 86400000):
                continue
            segments = []
            for m in data.get("trusted_segments", []):
                if not isinstance(m, dict) or m.get("trusted") is not True:
                    continue
                if m.get("source") not in SOURCES or m.get("segment_type") not in KINDS:
                    continue
                a, b = m.get("start_ms"), m.get("end_ms")
                if type(a) is not int or type(b) is not int or not 0 <= a < b <= duration:
                    continue
                segments.append(m)
            if segments:
                output.append({
                    "ids": ids, "season": season, "episode": episode,
                    "duration": duration, "segments": segments,
                    "expires": int(row["expires_at"]),
                    "sources": data.get("sources", {}),
                })
        except (TypeError, ValueError, OverflowError, KeyError):
            continue
    return total, output


def canonical_match(reference, cache_ids):
    matched = False
    for key in IDS:
        a, b = reference.get(key), cache_ids.get(key)
        if not a or not b:
            continue
        if a != b:
            return False
        matched = True
    return matched


def series_matches(prod, entries):
    """Reuse the same authoritative source joins as the production prefetch."""
    from analysis_identity import _columns, _source_list, _asset_identity, _clean_id

    cols = _columns(prod, "skip_assets")
    required = {"playlist_id", "asset_key", "season", "episode", "duration_ms"}
    if not required <= cols:
        raise ValueError("Unexpected skip_assets schema")
    sources = _source_list(prod, cols)
    wanted = {key: {entry["ids"].get(key) for entry in entries
                    if entry["ids"].get(key)} for key in IDS}
    by_episode = defaultdict(list)
    for index, entry in enumerate(entries):
        by_episode[(entry["season"], entry["episode"])].append(index)

    # First find exact identity reference keys; this avoids doing thousands
    # of per-asset metadata queries against the real analysis inventory.
    indexed = defaultdict(set)
    for table, join_key, fields, tcols in sources:
        if table == "skip_assets":
            continue
        terms, values = [], []
        for field in fields:
            possibles = list(wanted[field])
            if not possibles:
                continue
            # Bounded SQL parameter lists, even after many hours of caching.
            for offset in range(0, len(possibles), 250):
                chunk = possibles[offset:offset + 250]
                terms.append(field + " IN (" + ",".join("?" for _ in chunk) + ")")
                values.extend(chunk)
        if not terms:
            continue
        extra = ""
        if table == "skip_records" and "status" in tcols:
            extra = " AND (status IS NULL OR status NOT IN ('rejected','superseded','disabled'))"
        sql = ("SELECT DISTINCT " + join_key + " FROM " + table +
               " WHERE (" + " OR ".join(terms) + ")" + extra)
        for row in prod.execute(sql, values):
            if row[0] is not None:
                indexed[join_key].add(row[0])

    linked = defaultdict(set)
    label_columns = [x for x in ("series_title", "series_name", "title", "name") if x in cols]
    for asset in prod.execute("SELECT * FROM skip_assets WHERE playlist_id IN (8,10)"):
        try:
            match_keys = by_episode.get((int(asset["season"]), int(asset["episode"])), ())
            if not match_keys:
                continue
            duration = int(asset["duration_ms"])
            if not any(abs(entries[i]["duration"] - duration) <= CUT_TOLERANCE_MS
                       for i in match_keys):
                continue
            direct = any(_clean_id(fld, asset[fld]) in wanted[fld]
                         for fld in IDS if fld in cols)
            related = (asset["asset_key"] in indexed["asset_key"] or
                       ("source_key" in cols and asset["source_key"] in indexed["source_key"]))
            if not (direct or related):
                continue
            identity, status = _asset_identity(prod, asset, sources)
            if identity is None or status != "ok":
                continue
            pid = int(asset["playlist_id"])
            label = next((str(asset[c]).strip() for c in label_columns
                          if asset[c] is not None and str(asset[c]).strip()), "(ohne Titel)")
            for index in match_keys:
                entry = entries[index]
                if (abs(entry["duration"] - duration) <= CUT_TOLERANCE_MS and
                        canonical_match(identity, entry["ids"])):
                    linked[index].add((PLAYLISTS[pid], label))
        except (TypeError, ValueError, OverflowError, KeyError):
            continue
    return linked


def clock(ms):
    s = ms // 1000
    return f"{s // 60:02}:{s % 60:02}"


def render(total, entries, linked):
    print("=== EpiScene: externe Serienmarker (nur lesend) ===")
    print("Cache-Eintraege:", total,
          "| Folgen mit vertrauenswuerdigen Markern:", len(entries))
    counts = Counter(m["source"] for entry in entries for m in entry["segments"])
    print("Marker nach gespeicherter Quelle: IntroDB =", counts["introdb"],
          "| TheIntroDB =", counts["theintrodb"])
    print("Hinweis: Der Cache ist playlistuebergreifend. Playlist-Zuordnung")
    print("nur bei eindeutigem Episoden-ID-/Laufzeit-Abgleich.")
    now = int(time.time())
    rows = []
    for index, entry in enumerate(entries):
        names = linked.get(index)
        if not names:
            fallback = next((f"{k}={v}" for k, v in entry["ids"].items() if v),
                            "(keine externe ID)")
            names = {("Playlist nicht zugeordnet", fallback)}
        for m in entry["segments"]:
            for playlist, title in sorted(names):
                rows.append((playlist, title, entry["season"], entry["episode"],
                             m["source"], m["segment_type"],
                             clock(m["start_ms"]), clock(m["end_ms"]),
                             "aktiv" if entry["expires"] > now else "abgelaufen"))
    rows.sort(key=lambda r: (r[0], r[1].casefold(), r[2], r[3], r[4], r[5]))
    print()
    print("Playlist | Serie/Folge | Quelle | Art | Anfang-Ende | Cache")
    print("-" * 88)
    for row in rows[:200]:
        pid, title, season, episode, source, kind, start, end, freshness = row
        print(f"{pid} | {title} S{season:02}E{episode:02} | "
              f"{'IntroDB' if source == 'introdb' else 'TheIntroDB'} | "
              f"{kind} | {start}-{end} | {freshness}")
    if len(rows) > 200:
        print(f"... weitere {len(rows) - 200} zugeordnete Zeilen ausgeblendet.")
    if not entries:
        print("Keine akzeptierten IntroDB/TheIntroDB-Marker im Cache gefunden.")
    print()
    print("Dies zeigt gespeicherte externe Marker, nicht deren tatsaechliche")
    print("Anzeige auf einem Fire TV. Bei Quellen-Uebereinstimmung kann die")
    print("gespeicherte Zuordnung einen von beiden Diensten ausweisen.")


def main():
    if not BASE.is_dir() or BASE.is_symlink():
        raise SystemExit("STOP: erwartete EpiScene-Installation fehlt.")
    sys.path.insert(0, str(BASE))
    with ro(CACHE) as cache:
        total, entries = accepted_entries(cache)
    if not entries:
        render(total, [], {})
        return
    with ro(PROD) as prod:
        linked = series_matches(prod, entries)
    render(total, entries, linked)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, sqlite3.Error) as exc:
        raise SystemExit(f"STOP: Bericht konnte nicht gelesen werden: {exc}")
