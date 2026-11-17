#!/usr/bin/env python3
"""Match the ODbL IntroDB export against both EpiScene analysis playlists."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
from collections import Counter
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analysis_identity import BASE_REQUIRED, _asset_identity, _columns, _source_list
from bridge import Episode, KINDS, parse_introdb
from catalogue_sources import EXPORT_FILES, INTRODB_ATTRIBUTION, _download, _export_index
from trusted_external import _key, _promote
from trusted_external_sync import PRODUCTION

EXPORT_URL = "https://data.introdb.app/latest/"
PLAYLISTS = {8: "4K ANALYSE", 10: "THE BEST"}
SNAPSHOT_APPLICATION_ID = 0x45504949


def load_snapshot(download=_download):
    manifest = json.loads(download(EXPORT_URL + "manifest.json"))
    if manifest["schema_version"] != 1 or manifest["license"] != "ODbL-1.0":
        raise ValueError("Unbekanntes Exportformat oder unbekannte Lizenz")
    files = {row["name"]: row for row in manifest["files"]}
    data = []
    for name in EXPORT_FILES:
        binary = download(EXPORT_URL + name)
        info = files[name]
        if len(binary) != info["bytes"] or hashlib.sha256(binary).hexdigest() != info["sha256"]:
            raise ValueError(f"Prüfsumme stimmt nicht für {name}")
        data.append(binary)
    return manifest, _export_index(*data)


def match_catalogue(catalogue, index):
    report = {name: Counter() for name in PLAYLISTS.values()}
    entries = {}
    with closing(sqlite3.connect(catalogue.resolve().as_uri() + "?mode=ro", uri=True, timeout=10)) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        columns = _columns(db, "skip_assets")
        if not BASE_REQUIRED | {"media_type"} <= columns:
            raise ValueError("EpiScene-Episodenkatalog fehlt oder hat ein anderes Schema")
        sources = _source_list(db, columns)
        assets = db.execute("""
            SELECT *, COUNT(*) OVER (PARTITION BY playlist_id, asset_key) AS copies
            FROM skip_assets WHERE media_type='episode' AND playlist_id IN (8,10)
        """)
        for asset in assets:
            stats = report[PLAYLISTS[asset["playlist_id"]]]
            stats["Folgen"] += 1
            identity, status = _asset_identity(db, asset, sources)
            if asset["copies"] != 1 or status == "conflicting_ids":
                stats["Mehrdeutige Folge oder IDs"] += 1
                continue
            if not identity or not identity["imdb_id"]:
                stats["IMDb-ID fehlt"] += 1
                continue
            try:
                episode = Episode.from_dict(identity)
            except (TypeError, ValueError):
                stats["Laufzeit oder Episodendaten fehlen/sind ungültig"] += 1
                continue
            payload = index.get((episode.imdb_id, episode.season, episode.episode), {})
            markers, _ = _promote(parse_introdb(payload, episode),
                                  {kind for kind in KINDS if payload.get("no_" + kind)})
            if not markers:
                stats["Kein passender Marker"] += 1
                continue
            stats["Folgen mit Kandidaten"] += 1
            stats["Marker-Kandidaten"] += len(markers)
            entries[_key(episode)] = markers
    return report, entries


def save_snapshot(path, manifest, entries):
    if path.is_symlink() or path.exists():
        if path.is_symlink() or not path.is_file():
            raise ValueError("Ausgabe ist keine reguläre SQLite-Datei")
        with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as current:
            if current.execute("PRAGMA application_id").fetchone()[0] != SNAPSHOT_APPLICATION_ID:
                raise ValueError("Ausgabe gehört zu einer anderen Datenbank")
    with TemporaryDirectory(dir=path.parent) as temporary:
        staged = Path(temporary) / "introdb.sqlite3"
        with closing(sqlite3.connect(staged)) as db, db:
            db.execute(f"PRAGMA application_id={SNAPSHOT_APPLICATION_ID}")
            db.execute("CREATE TABLE export_info (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.executemany("INSERT INTO export_info VALUES (?,?)", (
                ("source", EXPORT_URL), ("generated_at", manifest["generated_at"]),
                ("license", manifest["license"]), ("attribution", INTRODB_ATTRIBUTION),
            ))
            db.execute("""CREATE TABLE introdb_candidates (
                episode_identity TEXT PRIMARY KEY, segments_json TEXT NOT NULL)""")
            db.executemany("INSERT INTO introdb_candidates VALUES (?,?)",
                           ((identity, json.dumps(markers)) for identity, markers in entries.items()))
        staged.chmod(0o600)
        os.replace(staged, path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=PRODUCTION)
    parser.add_argument("--output", type=Path, help="Optionale separate Kandidatendatenbank")
    args = parser.parse_args()
    try:
        manifest, index = load_snapshot()
        report, entries = match_catalogue(args.catalog, index)
        if args.output:
            save_snapshot(args.output, manifest, entries)
    except (OSError, EOFError, KeyError, TypeError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"IntroDB-Katalogabgleich fehlgeschlagen: {error}\n")
    print(INTRODB_ATTRIBUTION)
    print(f"Datenstand {manifest['generated_at']} | {len(entries)} eindeutige Folgenfassungen mit Kandidaten")
    for playlist, stats in report.items():
        print(f"{playlist} | " + " | ".join(f"{name} {count}" for name, count in stats.items())
              if stats else f"{playlist} | 0 Folgen")
    if args.output:
        print(f"Kandidaten gespeichert in {args.output}")


if __name__ == "__main__":
    main()
