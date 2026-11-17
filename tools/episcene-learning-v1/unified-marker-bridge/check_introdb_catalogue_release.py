#!/usr/bin/env python3
"""Check the staged IntroDB export and optionally release live-cache matches."""
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


def protected_record(row):
    return (row["status"] in ("approved", "rejected") or row["disabled"]
            or row["human_review"] or (row["status"] == "pending"
                                      and row["source"] in ("device", "manual")))


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
    protected = {row["segment_type"] for row in records if protected_record(row)}
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
    if not to_check:
        return set()
    active = {stamp(marker) for marker in trusted_online_markers(db, asset)
              if marker["source"] == "introdb" and marker["status"] == "approved"}
    report["im Live-Cache bestätigt"] += len(to_check & active)
    report["ohne Live-Cache-Nachweis"] += len(to_check - active)
    return to_check & active


def inspect_catalogue(prod, staged, *, online_enabled, release_enabled,
                      trusted_online_markers, confirmed=None):
    report = {lane: Counter() for lane in PLAYLISTS}
    imdb_by_key = defaultdict(set)
    missing = {lane: Counter() for lane in PLAYLISTS}
    matched = set()
    staged_cuts = {tuple(json.loads(key)[4:7]) for key in staged} if confirmed is not None else None
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
            if staged_cuts is not None:
                try:
                    cut = tuple(int(asset[field]) for field in ("season", "episode", "duration_ms"))
                except (TypeError, ValueError):
                    continue
                if cut not in staged_cuts:
                    continue
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
                ready = inspect_markers(db, asset, candidates, enabled[lane],
                                        trusted_online_markers, counts)
                if confirmed is not None and ready:
                    confirmed.append((lane, asset["asset_key"], episode, ready))
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


def read_records(db, asset_key):
    return {row["id"]: dict(row) for row in db.execute("""
        SELECT r.*, e.human_review FROM skip_records r
        LEFT JOIN skip_auto_evidence e ON e.record_id=r.id WHERE r.asset_key=?
    """, (asset_key,))}


def defer_commit(action, operation, *_):
    if action == sqlite3.SQLITE_TRANSACTION and operation == "COMMIT":
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


class ReleaseConnection(sqlite3.Connection):
    verifying_release = False

    def commit(self):
        if not self.verifying_release:
            super().commit()


def release_episode(db, target, sources, automation, release):
    lane, asset_key, episode_key, candidates = target
    with db:
        db.execute("BEGIN IMMEDIATE")
        assets = db.execute("SELECT * FROM skip_assets WHERE asset_key=? LIMIT 2",
                            (asset_key,)).fetchall()
        if len(assets) != 1 or assets[0]["playlist_id"] != lane or assets[0]["media_type"] != "episode":
            return Counter({"Zuordnung geändert": len(candidates)})
        asset = assets[0]
        identity, status = _asset_identity(db, asset, sources)
        try:
            current_key = _key(Episode.from_dict(identity)) if status == "ok" else None
        except (TypeError, ValueError):
            current_key = None
        if current_key != episode_key:
            return Counter({"Zuordnung geändert": len(candidates)})
        enabled = automation.enabled(db, lane, online=True) and release.enabled(db, lane)
        lookup = automation.trusted_online_markers
        ready = inspect_markers(db, asset, candidates, enabled, lookup, Counter())
        result = Counter({"Status geändert": len(candidates) - len(ready)})
        if not ready:
            return result

        before = read_records(db, asset_key)

        def scoped_lookup(con, current):
            if current["asset_key"] != asset_key or current["duration_ms"] != asset["duration_ms"]:
                return []
            return [marker for marker in lookup(con, current) if marker["source"] == "introdb"
                    and marker["status"] == "approved" and stamp(marker) in ready]

        # The normal release method and its revalidation see only these exact matches.
        automation.trusted_online_markers = scoped_lookup
        db.verifying_release = True
        db.set_authorizer(defer_commit)
        try:
            automation.promote_trusted_online(db, asset)
        finally:
            db.set_authorizer(None)
            db.verifying_release = False
            automation.trusted_online_markers = lookup
        if not db.in_transaction:
            raise RuntimeError("Freigabetransaktion wurde vor der Ergebnisprüfung beendet")

        after = read_records(db, asset_key)
        approved = [row for record_id, row in after.items() if row["status"] == "approved"
                    and not row["disabled"] and row != before.get(record_id)]
        if (any(after.get(record_id) != row for record_id, row in before.items()
                if protected_record(row))
                or any(row["source"] != "introdb" or stamp(row) not in ready
                       or row["duration_ms"] != asset["duration_ms"] for row in approved)):
            db.rollback()
            result["zurückgerollt"] = len(ready)
            return result

        result["neu freigegeben"] = len({stamp(row) for row in approved})
        result["Freigabe weiterhin offen"] = len(ready) - result["neu freigegeben"]
        return result


def apply_release(prod, confirmed, automation, release):
    results = {lane: Counter() for lane in PLAYLISTS}
    print(f"Übergebe bestätigte IntroDB-Marker aus {len(confirmed)} Folgen an die reguläre Freigabe ...",
          flush=True)
    with closing(sqlite3.connect(prod.resolve().as_uri() + "?mode=rw", uri=True, timeout=12,
                                 factory=ReleaseConnection)) as db:
        db.row_factory = sqlite3.Row
        sources = _source_list(db, _columns(db, "skip_assets"))
        for index, target in enumerate(confirmed, start=1):
            lane, _, _, candidates = target
            try:
                results[lane].update(release_episode(db, target, sources, automation, release))
            except sqlite3.OperationalError as error:
                error_code = getattr(error, "sqlite_errorcode", sqlite3.SQLITE_ERROR)
                if (error_code & 0xff) not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                    raise
                results[lane]["Datenbank beschäftigt"] += len(candidates)
            if index % 50 == 0:
                print(f"Freigabe geprüft für {index}/{len(confirmed)} Folgen", flush=True)
    return results


def main():
    import skip_automation
    import skip_release

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=PRODUCTION)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--apply", action="store_true", help="Bestätigte IntroDB-Marker freigeben")
    args = parser.parse_args()
    generated, staged = staged_markers(args.snapshot)
    confirmed = [] if args.apply else None
    print("Prüfe die vorhandenen IntroDB-Kandidaten und Serien-IDs ...", flush=True)
    report, matched = inspect_catalogue(
        args.catalog, staged, online_enabled=skip_automation.enabled,
        release_enabled=skip_release.enabled, trusted_online_markers=skip_automation.trusted_online_markers,
        confirmed=confirmed,
    )
    print(f"IntroDB-Export {generated} | Folgenfassungen im aktuellen Katalog {len(matched)}/{len(staged)}")
    if args.apply:
        results = apply_release(args.catalog, confirmed, skip_automation, skip_release)
        fields = ("neu freigegeben", "Freigabe weiterhin offen", "Status geändert",
                  "Zuordnung geändert", "zurückgerollt", "Datenbank beschäftigt")
        for lane, name in PLAYLISTS.items():
            print(f"{name} | " + " | ".join(f"{key} {results[lane][key]}" for key in fields))
        return
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
    except (ImportError, AttributeError, IndexError, sqlite3.Error, OSError, KeyError,
            RuntimeError, TypeError, ValueError) as error:
        raise SystemExit(f"IntroDB-Freigabelauf fehlgeschlagen: {error}") from None
