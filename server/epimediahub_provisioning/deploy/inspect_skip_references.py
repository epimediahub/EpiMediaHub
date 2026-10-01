#!/usr/bin/env python3
"""Read-only marker/file association check; never prints URLs or credentials."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


def inspect(db_path, season=None, episode=None):
    con = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    con.row_factory = sqlite3.Row
    try:
        filters, values = [], []
        for field, value in (("a.season", season), ("a.episode", episode)):
            if value is not None:
                filters.append(field + "=?")
                values.append(value)
        where = " WHERE " + " AND ".join(filters) if filters else ""
        target = con.execute("""SELECT a.*,j.id job_id,j.status job_status
          FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key"""
          + where + " ORDER BY j.id DESC LIMIT 1", values).fetchone()
        if target is None:
            print("Kein passender Analyseauftrag vorhanden.")
            return
        print(f"Referenzprüfung: Auftrag {target['job_id']} | S{target['season']} E{target['episode']}")
        rows = con.execute("""SELECT r.*,a.asset_key registered_asset,a.duration_ms file_duration,
          COALESCE(s.enabled,0) analysis_enabled FROM skip_records r
          LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
          LEFT JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id
          WHERE r.segment_type='intro' AND r.status='approved'
          AND (r.source_key=? OR (r.title=? AND r.year=?))
          ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 20""",
          (target["source_key"], target["title"], target["year"])).fetchall()
        if not rows:
            print("Keine freigegebene Introreferenz für diese Serienzuordnung gefunden.")
            return
        available = 0
        for row in rows:
            print(f"Freigegebenes Intro: S{row['season']} E{row['episode']}")
            registered = row["registered_asset"] is not None
            same = row["source_key"] == target["source_key"] and row["season"] == target["season"]
            length_ok = 19000 <= row["end_ms"] - row["start_ms"] <= 300000 and not row["disabled"]
            runtime_ok = registered and abs(row["file_duration"] - row["duration_ms"]) <= 2000
            print("  Serienzuordnung und Staffel passen:", "ja" if same else "nein")
            print("  Zeitmarke als Audioreferenz geeignet:", "ja" if length_ok else "nein")
            print("  Referenzdatei für Analyse registriert:", "ja" if registered else "nein")
            if registered:
                print("  Analyse der Referenzplaylist aktiviert:", "ja" if row["analysis_enabled"] else "nein")
                print("  Gespeicherte Laufzeit passt:", "ja" if runtime_ok else "nein")
            if same and length_ok and not registered:
                print(f"  Nächster Schritt: S{row['season']} E{row['episode']} in der App einmal öffnen und wieder beenden.")
            available += bool(same and length_ok and runtime_ok and row["analysis_enabled"])
        print("Nutzbare registrierte Referenzen:", available)
        print("Die gespeicherten Zeitmarken wurden nicht verändert.")
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("/var/lib/epimediahub"))
    parser.add_argument("--season", type=int)
    parser.add_argument("--episode", type=int)
    args = parser.parse_args()
    try:
        inspect(args.data_dir / "provisioning.db", args.season, args.episode)
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError):
        print("Referenzprüfung konnte nicht abgeschlossen werden.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
