#!/usr/bin/env python3
"""Sequential, bounded idle-time analysis; one job or a short timer batch."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import sqlite3
import time
from datetime import datetime
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
        "fingerprint_incomplete": "Audioabschnitt konnte innerhalb der Anbieter- und Datenlimits nicht vollständig gelesen werden",
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
    # A review may change the marker while the provider is being decoded.
    # Never attach audio from that older marker version to the corrected one.
    con.execute("""INSERT OR REPLACE INTO skip_fingerprints
      SELECT ?,?,?,?,?,? FROM skip_records WHERE id=? AND status='approved'
      AND disabled=0 AND start_ms=? AND end_ms=? AND reviewed_at IS ?""",
      (record["id"], json.dumps(words), step, 2000,
       record["end_ms"] - record["start_ms"], now(), record["id"],
       record["start_ms"], record["end_ms"], record["reviewed_at"]))


def reusable_fingerprint(stored, record):
    if stored is None:
        return False
    try:
        learned = datetime.fromisoformat(stored["created_at"].replace("Z", "+00:00"))
        reviewed = datetime.fromisoformat(record["reviewed_at"].replace("Z", "+00:00"))
        return (stored["offset_ms"] == 2000
                and stored["length_ms"] == record["end_ms"] - record["start_ms"]
                and learned >= reviewed)
    except (AttributeError, ValueError, TypeError):
        return False


def reference_detail(con, asset):
    missing = con.execute("""SELECT r.season,r.episode FROM skip_records r
      LEFT JOIN skip_assets a ON a.asset_key=r.asset_key
      WHERE r.source_key=? AND r.season=? AND r.segment_type='intro'
      AND r.status='approved' AND r.disabled=0 AND a.asset_key IS NULL
      AND r.end_ms-r.start_ms BETWEEN 19000 AND 300000
      ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 1""",
      (asset["source_key"], asset["season"])).fetchone()
    if missing:
        return (f"Freigegebenes Intro vorhanden; Referenzfolge S{missing['season']} "
                f"E{missing['episode']} in der App einmal öffnen und wieder beenden")
    return "Zuerst ein Intro dieser Staffel markieren und freigeben"


def analyze(db, job, busy_factory=busy_check):
    from skip_automation import enabled, store_proposal, analyze as automatic_analyze
    with db() as con:
        automatic_asset = con.execute("SELECT playlist_id,media_type FROM skip_assets WHERE asset_key=?", (job["asset_key"],)).fetchone()
        automatic = automatic_asset and automatic_asset["media_type"] == "episode" and enabled(con, automatic_asset["playlist_id"])
    if automatic:
        return automatic_analyze(db, job, busy_factory)
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
    busy = busy_factory(db, [playlist] + template_playlists)
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
                proposals += bool(store_proposal(con, data, kind, start, end, 'chapter'))
        own = [row for row in templates if row["asset_key"] == asset["asset_key"]]
        if own:
            for record in own:
                words, step = fingerprint(source, record["start_ms"] + 2000, record["end_ms"] - record["start_ms"] - 4000, busy)
                with db() as con:
                    store_fingerprint(con, record, words, step)
            return "done", "Geprüftes Intro als Referenz gelernt"
        other = [row for row in templates if row["asset_key"] != asset["asset_key"]]
        if not other or duration < 19_000:
            with db() as con:
                detail = reference_detail(con, asset)
            return "review" if proposals else "no_reference", "Kapitelvorschläge zur Prüfung verfügbar" if proposals else detail
        target, target_step = fingerprint(source, 0, min(600_000, duration), busy)
    for record, reference_playlist in zip(templates, template_playlists):
        if record["asset_key"] == asset["asset_key"]:
            continue
        with db() as con:
            stored = con.execute("SELECT * FROM skip_fingerprints WHERE record_id=?", (record["id"],)).fetchone()
            reference_asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (record["asset_key"],)).fetchone()
        if not reusable_fingerprint(stored, record):
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
        # The matched excerpt begins two seconds inside the approved intro.
        # Project its exact reviewed boundaries; do not crop another second.
        start = offset - 2000
        end = start + record["end_ms"] - record["start_ms"]
        # Allow only grid rounding at the beginning/end of the actual file.
        if -target_step / 2 <= start < 0:
            start = 0
        if duration < end <= duration + target_step / 2:
            end = duration
        if valid_range("intro", start, end, duration):
            with db() as con:
                proposals += bool(store_proposal(con, data, 'intro', start, end, 'audio', confidence))
    return ("review", "Vorschläge im Dashboard prüfen") if proposals else ("no_match", "Kein ausreichend eindeutiges Intro erkannt")


def process_one(db, *, exclude_job_ids=(), on_claim=None, deadline=None):
    from skip_catalogue import advance as catalogue_advance, daily_limit, preferred_inventory_pending
    # Inventory must keep progressing even after today's audio quota is used.
    catalogue_advance(db, busy_check)
    from skip_automation import refresh_online_one
    online_status = refresh_online_one(db, busy_check)
    with db() as con:
        # Limit aggregate traffic and processing on a Raspberry, irrespective of clients.
        count = con.execute("SELECT COUNT(*) FROM skip_jobs WHERE status NOT IN ('queued','disabled') AND substr(updated_at,1,10)=substr(?,1,10)", (now(),)).fetchone()[0]
        day = now()[:10]
        con.execute("INSERT OR IGNORE INTO skip_analysis_budget VALUES(?,?)", (day, count))
        con.execute("UPDATE skip_analysis_budget SET count=MAX(count,?) WHERE day=?", (count, day))
        budget = con.execute("SELECT count FROM skip_analysis_budget WHERE day=?", (day,)).fetchone()[0]
        if budget >= daily_limit(con):
            return "daily_limit"
    from skip_automation import discover_one
    discover_one(db, busy_check)
    with db() as con:
        con.execute("UPDATE skip_jobs SET status='queued' WHERE status='running' AND updated_at<?", (time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(time.time() - 1800)),))
        excluded = tuple(exclude_job_ids)
        exclusion = " AND j.id NOT IN (" + ",".join("?" for _ in excluded) + ")" if excluded else ""
        job = con.execute("""SELECT j.* FROM skip_jobs j
          JOIN skip_assets a ON a.asset_key=j.asset_key
          LEFT JOIN skip_language_priority l ON l.asset_key=j.asset_key
          LEFT JOIN skip_catalogue_priority p ON p.asset_key=j.asset_key
          WHERE j.status='queued' AND j.attempts<3""" + exclusion + """
          ORDER BY CASE WHEN a.media_type='episode' THEN COALESCE(l.priority,1) ELSE 1 END,
          COALESCE(p.priority,1),j.updated_at,j.id LIMIT 1""", excluded).fetchone()
        if job is None:
            return online_status if online_status == 'online_checked' else "idle"
        language = con.execute("SELECT priority FROM skip_language_priority WHERE asset_key=?", (job['asset_key'],)).fetchone()
        if not language or language[0] != 0:
            preferred_jobs = con.execute("""SELECT 1 FROM skip_jobs pj
              JOIN skip_assets pa ON pa.asset_key=pj.asset_key
              JOIN skip_language_priority pl ON pl.asset_key=pa.asset_key AND pl.priority=0
              JOIN skip_analysis_sources ps ON ps.playlist_id=pa.playlist_id AND ps.enabled=1
              JOIN skip_auto_settings px ON px.playlist_id=pa.playlist_id AND px.enabled=1
              JOIN customer_playlists pp ON pp.id=pa.playlist_id
              JOIN customers pc ON pc.id=pp.customer_id AND pc.enabled=1
              WHERE pj.status='queued' AND pj.attempts<3 LIMIT 1""").fetchone()
            if preferred_inventory_pending(con) or preferred_jobs:
                return 'preferred_pending'
        con.execute("UPDATE skip_jobs SET status='running',updated_at=? WHERE id=?", (now(), job["id"]))
    if on_claim is not None:
        on_claim(job["id"])
    try:
        if deadline is None:
            status, detail = analyze(db, job)
        else:
            def bounded_busy(db, playlists):
                playback_busy = busy_check(db, playlists)
                def check():
                    return time.monotonic() >= deadline or playback_busy()
                return check
            status, detail = analyze(db, job, busy_factory=bounded_busy)
    except ValueError as error:
        if str(error) == "analysis_deferred":
            status, detail = "queued", "Wartet, bis die Wiedergabe beendet ist"
        else:
            status, detail = "failed", failure_detail(error)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, sqlite3.Error, OverflowError):
        status, detail = "failed", "Analyse nicht möglich; eigene Zeitmarken bleiben nutzbar"
    if status == "queued" and deadline is not None and time.monotonic() >= deadline:
        detail = "Zeitbudget des Laufs erreicht; vorhandene Audiofenster bleiben für den nächsten Lauf erhalten"
    with db() as con:
        from skip_release import accept_pending
        accepted = accept_pending(con, asset_key=job['asset_key'])
        if accepted and status == 'review':
            status, detail = 'done', f'{accepted} erkannte Abschnitt(e) automatisch freigegeben; Zeiten später korrigierbar'
        con.execute("UPDATE skip_jobs SET status=?,detail=?,attempts=attempts+?,updated_at=? WHERE id=?", (status, detail, 0 if status == "queued" else 1, now(), job["id"]))
        if status not in ('queued', 'disabled'):
            con.execute("INSERT INTO skip_analysis_budget VALUES(?,1) ON CONFLICT(day) DO UPDATE SET count=count+1", (day,))
            con.execute("DELETE FROM skip_catalogue_priority WHERE asset_key=?", (job["asset_key"],))
        con.execute("DELETE FROM skip_analysis_budget WHERE day<?", (time.strftime("%Y-%m-%d", time.gmtime(time.time() - 31 * 86400)),))
    return status


def process_batch(db, max_jobs=4, max_seconds=600, report=None):
    """No parallel provider connections, no repeated busy job in the same batch.

    Each job still applies the existing language order, traffic budget and
    live-playback checks. Audio/proxy operations also check the shared deadline;
    systemd retains a final hard service timeout for a stalled provider.
    """
    if not 1 <= max_jobs <= 8 or not 1 <= max_seconds <= 600:
        raise ValueError("invalid_batch_limits")
    deadline, claimed, statuses = time.monotonic() + max_seconds, set(), []
    for _ in range(max_jobs):
        if time.monotonic() >= deadline:
            break
        status = process_one(db, exclude_job_ids=claimed, on_claim=claimed.add, deadline=deadline)
        statuses.append(status)
        if report is not None:
            report(status)
        if status in ("idle", "daily_limit", "preferred_pending", "catalogue_pending"):
            break
    return statuses


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Process at most one bounded job")
    parser.add_argument("--batch", action="store_true", help="Process a short sequential batch")
    parser.add_argument("--max-jobs", type=int, default=4)
    parser.add_argument("--max-seconds", type=int, default=600)
    args = parser.parse_args()
    if args.once and args.batch:
        parser.error("choose --once or --batch")
    if not 1 <= args.max_jobs <= 8 or not 1 <= args.max_seconds <= 600:
        parser.error("max-jobs must be 1..8 and max-seconds must be 1..600")
    data_dir = Path(os.environ.get("EPIMEDIAHUB_DATA_DIR", "/var/lib/epimediahub"))
    data_dir.mkdir(parents=True, exist_ok=True)
    with (data_dir / "skip-analysis.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(0)
        # Importing the application runs schema migrations. Those writes must
        # also be protected against another worker or an ongoing installation.
        from app import db
        from wsgi import app
        from skip_progress import refresh as refresh_progress
        with db() as con:
            refresh_progress(con, budget=.5)
        def report(status):
            with db() as con:
                refresh_progress(con, budget=.5)
            print("skip_analysis_status=" + status, flush=True)
        if args.batch:
            process_batch(db, args.max_jobs, args.max_seconds, report)
        else:
            report(process_one(db))
