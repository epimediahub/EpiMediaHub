#!/usr/bin/env python3
"""Compare the staged IntroDB export against the current EpiScene release path."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path

from analysis_identity import BASE_REQUIRED, _asset_identity, _columns, _source_list
from bridge import Episode, KINDS
from trusted_external import _key

PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
SNAPSHOT = Path("/var/lib/episcene-learning/introdb-open-catalogue.sqlite3")
PLAYLISTS = {8: "4K ANALYSE", 10: "THE BEST"}
SNAPSHOT_APPLICATION_ID = 0x45504949
ALTERNATIVE_IDS = ("tmdb_id", "tvdb_id")
LOOKUP_STATES = ("bereits freigegeben", "vorhandene Entscheidung", "gesperrt",
                 "Online-Freigabe aus", "im Live-Cache bestätigt", "ohne Live-Cache-Nachweis")


def readonly(path):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db


def stamp(segment):
    return segment["segment_type"], segment["start_ms"], segment["end_ms"]


def staged_markers(path):
    with closing(readonly(path)) as db:
        if db.execute("PRAGMA application_id").fetchone()[0] != SNAPSHOT_APPLICATION_ID:
            raise ValueError("Datei ist kein EpiScene-IntroDB-Abgleich")
        info = dict(db.execute("SELECT key,value FROM export_info"))
        rows = db.execute("SELECT episode_identity,segments_json FROM introdb_candidates")
        markers = {row[0]: {stamp(segment) for segment in json.loads(row[1])
                            if segment["source"] == "introdb" and segment["trusted"] is True
                            and segment["segment_type"] in KINDS}
                   for row in rows}
    return info["generated_at"], markers


def alternative_keys(identity):
    return tuple((name, identity[name]) for name in ALTERNATIVE_IDS if identity[name])


def inspect_markers(db, asset, candidates, enabled, trusted_online_markers, report):
    asset_cut = (asset["asset_key"], asset["duration_ms"])
    records = db.execute("""
        SELECT r.segment_type, r.start_ms, r.end_ms, r.duration_ms, r.status,
               r.source, r.disabled, e.human_review
        FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
        WHERE r.asset_key=? AND ABS(r.duration_ms-?)<=2000
          AND r.segment_type IN ('intro','recap','outro')
    """, asset_cut).fetchall()
    visible = {stamp(row) for row in records if row["status"] == "approved"
               and not row["disabled"] and row["duration_ms"] == asset["duration_ms"]}
    protected = {row["segment_type"] for row in records
                 if row["status"] in ("approved", "rejected") or row["disabled"]
                 or row["human_review"] or (row["status"] == "pending"
                                            and row["source"] in ("device", "manual"))}
    blocks = {row[0] for row in db.execute("""
        SELECT kind FROM skip_auto_blocks WHERE asset_key=? AND ABS(duration_ms-?)<=2000
    """, asset_cut)}
    to_check = set()
    for marker in candidates:
        if marker in visible:
            report["bereits freigegeben"] += 1
        elif marker[0] in blocks:
            report["gesperrt"] += 1
        elif marker[0] in protected:
            report["vorhandene Entscheidung"] += 1
        elif not enabled:
            report["Online-Freigabe aus"] += 1
        else:
            to_check.add(marker)
    if to_check:
        active = {stamp(marker) for marker in trusted_online_markers(db, asset)
                  if marker["source"] == "introdb" and marker["status"] == "approved"}
        report["im Live-Cache bestätigt"] += len(to_check & active)
        report["ohne Live-Cache-Nachweis"] += len(to_check - active)


def inspect_catalogue(prod, staged, *, online_enabled, release_enabled, trusted_online_markers):
    report = {lane: Counter() for lane in PLAYLISTS}
    imdb_by_key = defaultdict(set)
    missing = {lane: Counter() for lane in PLAYLISTS}
    matched = set()
    with closing(readonly(prod)) as db:
        columns = _columns(db, "skip_assets")
        if not (BASE_REQUIRED | {"media_type", "source_key"}) <= columns:
            raise ValueError("Das Schema des EpiScene-Katalogs hat sich geändert")
        sources = _source_list(db, columns)
        enabled = {lane: online_enabled(db, lane, online=True) and release_enabled(db, lane)
                   for lane in PLAYLISTS}
        for asset in db.execute("""
            SELECT *, COUNT(*) OVER (PARTITION BY playlist_id, asset_key) AS copies
            FROM skip_assets WHERE media_type='episode' AND playlist_id IN (8,10)
        """):
            lane = asset["playlist_id"]
            counts = report[lane]
            identity, status = _asset_identity(db, asset, sources)
            if asset["copies"] != 1 or status == "conflicting_ids":
                counts["mehrdeutige Episoden"] += 1
                continue
            keys = alternative_keys(identity) if identity is not None else ()
            imdb = identity and identity["imdb_id"]
            if not imdb:
                missing[lane][keys] += 1
                continue
            for key in keys:
                imdb_by_key[key].add(imdb)
            try:
                episode = _key(Episode.from_dict(identity))
            except (TypeError, ValueError):
                continue
            candidates = staged.get(episode)
            if candidates:
                matched.add(episode)
                counts["Marker geprüft"] += len(candidates)
                inspect_markers(db, asset, candidates, enabled[lane], trusted_online_markers, counts)
    for lane, groups in missing.items():
        counts = report[lane]
        counts["IMDb fehlt"] = sum(groups.values())
        for keys, count in groups.items():
            choices = set().union(*(imdb_by_key[key] for key in keys))
            if len(choices) == 1:
                counts["lokale IMDb-Zuordnung"] += count
            elif len(choices) > 1:
                counts["widersprüchliche Zuordnung"] += count
            elif keys:
                counts["TMDB/TVDB-ID vorhanden"] += count
    return report, matched


def main():
    from skip_automation import enabled as online_enabled, trusted_online_markers
    from skip_release import enabled as release_enabled

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=PRODUCTION)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    args = parser.parse_args()
    generated, staged = staged_markers(args.snapshot)
    print("Prüfe die vorhandenen IntroDB-Kandidaten und Serien-IDs ...", flush=True)
    report, matched = inspect_catalogue(args.catalog, staged, online_enabled=online_enabled,
                                        release_enabled=release_enabled,
                                        trusted_online_markers=trusted_online_markers)
    print(f"IntroDB-Export {generated} | Folgenfassungen im aktuellen Katalog {len(matched)}/{len(staged)}")
    for lane, name in PLAYLISTS.items():
        counts = report[lane]
        marker_stats = ("Marker geprüft", *LOOKUP_STATES)
        id_stats = ("IMDb fehlt", "lokale IMDb-Zuordnung", "TMDB/TVDB-ID vorhanden",
                    "widersprüchliche Zuordnung", "mehrdeutige Episoden")
        for label, fields in (("Freigabe", marker_stats), ("IDs", id_stats)):
            print(f"{name} | {label} | " + " | ".join(f"{key} {counts[key]}" for key in fields))


if __name__ == "__main__":
    try:
        main()
    except (ImportError, AttributeError, IndexError, sqlite3.Error, OSError, KeyError, TypeError, ValueError) as error:
        raise SystemExit(f"IntroDB-Freigabeprüfung fehlgeschlagen: {error}") from None
