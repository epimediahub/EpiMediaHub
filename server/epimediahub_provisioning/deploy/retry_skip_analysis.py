#!/usr/bin/env python3
"""Requeue one existing analysis job; optionally refresh its derived reference cache."""
from __future__ import annotations

import argparse
import fcntl
import os
from pathlib import Path
import sqlite3
import sys


class RetryFailure(Exception):
    pass


def retry(db_path, job_id, fresh_reference=False):
    from skip_analysis import configured_source
    from skip_markers import now
    if not Path(db_path).is_file():
        raise RetryFailure("database_missing")
    con = sqlite3.connect(db_path, timeout=10)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    try:
        with con:
            con.execute("BEGIN IMMEDIATE")
            job = con.execute("""SELECT j.*,a.source_key,a.season,a.episode,a.playlist_id
              FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key
              WHERE j.id=?""", (job_id,)).fetchone()
            if job is None:
                raise RetryFailure("job_missing")
            result = dict(job_id=job["id"], season=job["season"], episode=job["episode"],
                          queued=False, cleared=0)
            if job["status"] in ("review", "done"):
                return result
            if job["status"] not in ("no_match", "no_reference", "failed", "queued"):
                raise RetryFailure("job_not_retryable")
            playlist = con.execute("""SELECT p.* FROM customer_playlists p
              JOIN skip_analysis_sources s ON s.playlist_id=p.id AND s.enabled=1
              WHERE p.id=?""", (job["playlist_id"],)).fetchone()
            if playlist is None:
                raise RetryFailure("source_disabled")
            configured_source(playlist)
            references = con.execute("""SELECT r.id,a.playlist_id FROM skip_records r
              JOIN skip_assets a ON a.asset_key=r.asset_key
              JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
              WHERE r.source_key=? AND r.season=? AND r.segment_type='intro'
              AND r.status='approved' AND r.disabled=0 AND r.asset_key<>?
              AND r.end_ms-r.start_ms BETWEEN 19000 AND 300000
              AND ABS(a.duration_ms-r.duration_ms)<=2000
              ORDER BY r.reviewed_at DESC LIMIT 3""",
              (job["source_key"], job["season"], job["asset_key"])).fetchall()
            if fresh_reference:
                if not references:
                    raise RetryFailure("reference_missing")
                for reference in references:
                    source = con.execute("SELECT * FROM customer_playlists WHERE id=?",
                                         (reference["playlist_id"],)).fetchone()
                    configured_source(source)
                    result["cleared"] += con.execute(
                        "DELETE FROM skip_fingerprints WHERE record_id=?",
                        (reference["id"],)).rowcount
            con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,detail='',updated_at=?
              WHERE id=?""", (now(), job["id"]))
            result["queued"] = True
        return result
    finally:
        con.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--job-id", type=int, required=True)
    parser.add_argument("--fresh-reference", action="store_true")
    parser.add_argument("--app-dir", type=Path, default=Path("/opt/epimediahub/provisioning"))
    parser.add_argument("--data-dir", type=Path,
                        default=Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub")))
    args = parser.parse_args()
    sys.path.insert(0, str(args.app_dir.resolve()))
    try:
        with (args.data_dir / "skip-analysis.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Der Analysedienst arbeitet gerade. Später erneut ausführen.")
                return 2
            result = retry(args.data_dir / "provisioning.db", args.job_id, args.fresh_reference)
        print(f"Auftrag {result['job_id']} | S{result['season']} E{result['episode']}")
        if result["queued"]:
            print("Erneut für den regulären Analysedienst eingeplant.")
            if args.fresh_reference:
                print("Referenzcache zur Neuberechnung zurückgesetzt:", result["cleared"])
        else:
            print("Auftrag bereits abgeschlossen oder Vorschläge zur Prüfung vorhanden.")
        print("Gespeicherte Zeitmarken und Freigaben bleiben erhalten.")
        return 0
    except RetryFailure as error:
        print("Erneutes Einplanen nicht möglich:", str(error))
    except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, ImportError):
        print("Erneutes Einplanen nicht möglich; Konfiguration oder Datenbank prüfen.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
