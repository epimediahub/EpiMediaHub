#!/usr/bin/env python3
"""One bounded, idle-time analysis job per timer invocation."""
from __future__ import annotations

import argparse
import fcntl
import json
import re
import sqlite3
import time
from pathlib import Path

from skip_analysis import (configured_source, source_account, source_url, provider_proxy,
                           probe, fingerprint, matching_offset, chapter_candidates)
from skip_markers import add_record, now, valid_range


def failure_detail(error):
    code = str(error)
    reasons = {
        "unsafe_source": "Anbieterziel oder Weiterleitung ist keine erlaubte öffentliche HTTP-Quelle",
        "redirect_limit": "Anbieter leitet zu oft weiter (höchstens drei Schritte erlaubt)",
        "redirect_downgrade": "Anbieter leitet von HTTPS auf unverschlüsseltes HTTP weiter",
        "provider_timeout": "Anbieter antwortet beim Dateizugriff nicht rechtzeitig",
        "provider_dns": "Streaming-Host kann nicht aufgelöst werden",
        "provider_tls": "TLS-Verbindung zum Streaming-Host scheitert",
        "provider_connection": "Verbindung zum Streaming-Host scheitert",
        "analysis_input_limit": "Datenlimit für die Dateianalyse erreicht",
        "duration_unknown": "Laufzeit der Videodatei kann nicht ermittelt werden",
        "chromaprint_unavailable": "Audio-Fingerabdruckbibliothek fehlt",
        "fingerprint_failed": "Audio-Fingerabdruck kann nicht berechnet werden",
        "analysis_limit": "Zeit- oder Ausgabelimit der Audioanalyse erreicht",
        "analysis_failed": "Videodatei oder Audiospur kann nicht ausgewertet werden",
    }
    match = re.fullmatch(r"provider_http_([1-5][0-9]{2})", code)
    reason = ("Anbieter meldet HTTP " + match.group(1)) if match else reasons.get(code)
    return ((reason + "; eigene Zeitmarken bleiben nutzbar") if reason
            else "Analyse nicht möglich; eigene Zeitmarken bleiben nutzbar")


def busy_check(db, playlists):
    accounts = {source_account(row) for row in playlists}
    cache = [0.0, False]
    def busy():
        if time.monotonic() - cache[0] < 2:
            return cache[1]
        with db() as con:
            rows = con.execute("SELECT DISTINCT p.* FROM skip_presence s JOIN customer_playlists p ON p.id=s.playlist_id WHERE s.expires_at>?", (int(time.time()),)).fetchall()
        value = False
        for row in rows:
            try:
                value |= source_account(row) in accounts
            except ValueError:
                continue
        cache[:] = [time.monotonic(), value]
        return value
    return busy


def store_fingerprint(con, record, words, step):
    # The inner music excerpt helps avoid dialogue outside the title sequence.
    con.execute("INSERT OR REPLACE INTO skip_fingerprints VALUES(?,?,?,?,?,?)", (record["id"], json.dumps(words), step, 2000, record["end_ms"] - record["start_ms"], now()))


def analyze(db, job):
    with db() as con:
        asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (job["asset_key"],)).fetchone()
        playlist = con.execute("SELECT p.* FROM customer_playlists p JOIN skip_analysis_sources s ON s.playlist_id=p.id WHERE p.id=? AND s.enabled=1", (asset["playlist_id"],)).fetchone() if asset else None
        if playlist is None:
            return "disabled", "Analyse für diese Playlist ausgeschaltet"
        templates = con.execute("""SELECT r.*,a.playlist_id FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          WHERE r.source_key=? AND r.season=? AND r.segment_type='intro' AND r.status='approved' AND r.disabled=0
          AND r.end_ms-r.start_ms BETWEEN 19000 AND 300000 AND ABS(a.duration_ms-r.duration_ms)<=2000
          ORDER BY r.reviewed_at DESC LIMIT 3""", (asset["source_key"], asset["season"])).fetchall()
        template_playlists = [con.execute("SELECT * FROM customer_playlists WHERE id=?", (row["playlist_id"],)).fetchone() for row in templates]
    busy = busy_check(db, [playlist] + template_playlists)
    if busy():
        return "queued", "Wartet, bis die Wiedergabe beendet ist"
    data = dict(asset, imdb_id="", tmdb_id=0)
    proposals = 0
    with provider_proxy(source_url(playlist, asset), busy) as source:
        duration, chapters = probe(source, busy)
        if abs(duration - asset["duration_ms"]) > 2000:
            return "unmatched", "Videolaufzeit stimmt nicht mit der gemeldeten Folge überein"
        with db() as con:
            for kind, start, end in chapter_candidates(chapters, duration):
                add_record(con, data, kind, start, end, False, source="chapter")
                proposals += 1
        own = [row for row in templates if row["asset_key"] == asset["asset_key"]]
        if own:
            for record in own:
                words, step = fingerprint(source, record["start_ms"] + 2000, record["end_ms"] - record["start_ms"] - 4000, busy)
                with db() as con:
                    store_fingerprint(con, record, words, step)
            return "done", "Geprüftes Intro als Referenz gelernt"
        other = [row for row in templates if row["asset_key"] != asset["asset_key"]]
        if not other or duration < 19_000:
            return "review" if proposals else "no_reference", "Kapitelvorschläge zur Prüfung verfügbar" if proposals else "Zuerst ein Intro dieser Staffel markieren und freigeben"
        target, target_step = fingerprint(source, 0, min(600_000, duration), busy)
    for record, reference_playlist in zip(templates, template_playlists):
        if record["asset_key"] == asset["asset_key"]:
            continue
        with db() as con:
            stored = con.execute("SELECT * FROM skip_fingerprints WHERE record_id=?", (record["id"],)).fetchone()
            reference_asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (record["asset_key"],)).fetchone()
        if stored is None:
            with provider_proxy(source_url(reference_playlist, reference_asset), busy) as source:
                measured, _ = probe(source, busy)
                if abs(measured - record["duration_ms"]) > 2000:
                    continue
                words, step = fingerprint(source, record["start_ms"] + 2000, record["end_ms"] - record["start_ms"] - 4000, busy)
            with db() as con:
                store_fingerprint(con, record, words, step)
        else:
            words, step = json.loads(stored["words_json"]), stored["step_ms"]
        if abs(step - target_step) > .001:
            continue
        match = matching_offset(words, target, step)
        if match is None:
            continue
        offset, confidence = match
        start = offset - 2000 + 1000
        end = offset - 2000 + record["end_ms"] - record["start_ms"] - 1000
        if valid_range("intro", start, end, duration):
            with db() as con:
                add_record(con, data, "intro", start, end, False, source="audio", confidence=confidence)
            proposals += 1
    return ("review", "Vorschläge im Dashboard prüfen") if proposals else ("no_match", "Kein ausreichend eindeutiges Intro erkannt")


def process_one(db):
    with db() as con:
        # Limit aggregate traffic and processing on a Raspberry, irrespective of clients.
        count = con.execute("SELECT COUNT(*) FROM skip_jobs WHERE status NOT IN ('queued','disabled') AND substr(updated_at,1,10)=substr(?,1,10)", (now(),)).fetchone()[0]
        if count >= 24:
            return "daily_limit"
        con.execute("UPDATE skip_jobs SET status='queued' WHERE status='running' AND updated_at<?", (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 1800)),))
        job = con.execute("SELECT * FROM skip_jobs WHERE status='queued' AND attempts<3 ORDER BY updated_at,id LIMIT 1").fetchone()
        if job is None:
            return "idle"
        con.execute("UPDATE skip_jobs SET status='running',updated_at=? WHERE id=?", (now(), job["id"]))
    try:
        status, detail = analyze(db, job)
    except ValueError as error:
        if str(error) == "analysis_deferred":
            status, detail = "queued", "Wartet, bis die Wiedergabe beendet ist"
        else:
            status, detail = "failed", failure_detail(error)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, sqlite3.Error, OverflowError):
        status, detail = "failed", "Analyse nicht möglich; eigene Zeitmarken bleiben nutzbar"
    with db() as con:
        con.execute("UPDATE skip_jobs SET status=?,detail=?,attempts=attempts+?,updated_at=? WHERE id=?", (status, detail, 0 if status == "queued" else 1, now(), job["id"]))
    return status


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one bounded job")
    parser.parse_args()
    from app import BASE_DIR, db
    from wsgi import app
    with (Path(BASE_DIR) / "skip-analysis.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(0)
        print("skip_analysis_status=" + process_one(db))
