"""Reviewed skip markers bound to one provider file and its measured runtime.

Device proposals are private pending records. An authenticated administrator can
enable bounded automatic publishing with independent evidence for each file.
No provider URL or password is accepted here.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from datetime import datetime, timezone

from flask import abort, jsonify, redirect, render_template, request, session, url_for

KEY = re.compile(r"^[a-f0-9]{64}$")
KINDS = {"intro": 300_000, "recap": 300_000, "outro": 900_000}


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def migrate(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS skip_records(
      id INTEGER PRIMARY KEY AUTOINCREMENT, submission_key TEXT NOT NULL UNIQUE,
      asset_key TEXT NOT NULL, source_key TEXT NOT NULL, media_type TEXT NOT NULL,
      title TEXT NOT NULL, year TEXT NOT NULL DEFAULT '', season INTEGER NOT NULL DEFAULT 0,
      episode INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL,
      segment_type TEXT NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
      disabled INTEGER NOT NULL DEFAULT 0, imdb_id TEXT NOT NULL DEFAULT '', tmdb_id INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'pending', source TEXT NOT NULL DEFAULT 'device', confidence REAL NOT NULL DEFAULT 1,
      device_id INTEGER REFERENCES devices(id) ON DELETE SET NULL,
      customer_id INTEGER REFERENCES customers(id) ON DELETE SET NULL,
      created_at TEXT NOT NULL, reviewed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_skip_asset ON skip_records(asset_key,duration_ms,status);
    CREATE INDEX IF NOT EXISTS idx_skip_source ON skip_records(source_key,status);
    CREATE INDEX IF NOT EXISTS idx_skip_dashboard ON skip_records(status,source_key,season,episode);
    CREATE TABLE IF NOT EXISTS skip_identities(
      source_key TEXT PRIMARY KEY, imdb_id TEXT NOT NULL DEFAULT '', tmdb_id INTEGER NOT NULL DEFAULT 0,
      title TEXT NOT NULL, year TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS skip_rate(device_id INTEGER NOT NULL, action TEXT NOT NULL, window INTEGER NOT NULL,
      count INTEGER NOT NULL, PRIMARY KEY(device_id,action,window));
    CREATE TABLE IF NOT EXISTS skip_assets(
      asset_key TEXT PRIMARY KEY, source_key TEXT NOT NULL, playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
      stream_id TEXT NOT NULL, extension TEXT NOT NULL, media_type TEXT NOT NULL,
      duration_ms INTEGER NOT NULL, season INTEGER NOT NULL, episode INTEGER NOT NULL,
      title TEXT NOT NULL, year TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS skip_analysis_sources(
      playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
      enabled INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS skip_presence(
      device_id INTEGER PRIMARY KEY REFERENCES devices(id) ON DELETE CASCADE,
      playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE, expires_at INTEGER NOT NULL
    );
    CREATE TABLE IF NOT EXISTS skip_jobs(
      id INTEGER PRIMARY KEY AUTOINCREMENT, asset_key TEXT NOT NULL UNIQUE REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
      status TEXT NOT NULL DEFAULT 'queued', attempts INTEGER NOT NULL DEFAULT 0,
      detail TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS skip_fingerprints(
      record_id INTEGER PRIMARY KEY REFERENCES skip_records(id) ON DELETE CASCADE,
      words_json TEXT NOT NULL, step_ms REAL NOT NULL, offset_ms INTEGER NOT NULL,
      length_ms INTEGER NOT NULL, created_at TEXT NOT NULL
    );
    """)
    from skip_automation import migrate as migrate_automation
    migrate_automation(con)


def integer(body, key, low, high, default=None):
    value = body.get(key, default)
    if type(value) is not int or not low <= value <= high:
        raise ValueError(key)
    return value


def descriptor(body):
    if not isinstance(body, dict):
        raise ValueError("body")
    if any(key in body for key in ("url", "stream_url", "password", "username", "headers")):
        raise ValueError("unexpected_credentials")
    for key in ("asset_key", "source_key"):
        if not isinstance(body.get(key), str) or not KEY.fullmatch(body[key]):
            raise ValueError(key)
    kind = body.get("media_type")
    if kind not in ("episode", "movie"):
        raise ValueError("media_type")
    season = integer(body, "season", 0, 1000, 0)
    episode = integer(body, "episode", 0, 10000, 0)
    if kind == "episode" and episode == 0:
        raise ValueError("episode")
    if kind == "movie" and (season or episode):
        raise ValueError("movie_numbering")
    title = body.get("title", "")
    if not isinstance(title, str) or not 1 <= len(title.strip()) <= 180:
        raise ValueError("title")
    year = body.get("year", "")
    if not isinstance(year, str) or (year and not re.fullmatch(r"(?:19|20)\d{2}", year)):
        raise ValueError("year")
    imdb = body.get("imdb_id", "")
    if not isinstance(imdb, str) or (imdb and not re.fullmatch(r"tt\d{7,10}", imdb)):
        raise ValueError("imdb_id")
    return dict(asset_key=body["asset_key"], source_key=body["source_key"], media_type=kind,
                title=title.strip(), year=year, season=season, episode=episode,
                duration_ms=integer(body, "duration_ms", 5000, 86_400_000), imdb_id=imdb,
                tmdb_id=integer(body, "tmdb_id", 0, 100_000_000, 0))


def valid_range(kind, start, end, duration, disabled=False):
    return kind in KINDS and (disabled or (0 <= start < end <= duration and 5000 <= end - start <= KINDS[kind]))


def add_record(con, data, kind, start, end, disabled, device=None, source="device", confidence=1.0):
    key_data = [device["id"] if device else None, data["asset_key"], data["source_key"], data["duration_ms"], kind, start, end, disabled, source, data["imdb_id"], data["tmdb_id"]]
    key = hashlib.sha256(json.dumps(key_data, separators=(",", ":")).encode()).hexdigest()
    con.execute("""INSERT OR IGNORE INTO skip_records(
      submission_key,asset_key,source_key,media_type,title,year,season,episode,duration_ms,
      segment_type,start_ms,end_ms,disabled,imdb_id,tmdb_id,status,source,confidence,device_id,customer_id,created_at)
      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,?,?,?,?)""",
      (key, *(data[k] for k in ("asset_key", "source_key", "media_type", "title", "year", "season", "episode", "duration_ms")),
       kind, start, end, int(disabled), data["imdb_id"], data["tmdb_id"], source, confidence,
       device["id"] if device else None, device["customer_id"] if device else None, now()))
    return con.execute("SELECT id,status FROM skip_records WHERE submission_key=?", (key,)).fetchone()


def timecode(ms):
    total = max(0, ms // 1000)
    return f"{total // 3600:02d}:{total // 60 % 60:02d}:{total % 60:02d}" + (f".{ms % 1000:03d}" if ms % 1000 else "")


def parse_time(value):
    value = str(value).strip()
    if re.fullmatch(r"\d+(?:\.\d{1,3})?", value):
        return round(float(value) * 1000)
    parts = value.split(":")
    if len(parts) not in (2, 3) or any(not re.fullmatch(r"\d{1,3}", p) for p in parts[:-1]) or not re.fullmatch(r"\d{1,2}(?:\.\d{1,3})?", parts[-1]) or any(float(p) >= 60 for p in parts[1:]):
        raise ValueError("time")
    return round(sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts))) * 1000)


def page_number(value, default=1):
    return int(value) if re.fullmatch(r"[1-9]\d{0,6}", str(value)) else default


def media_groups(rows):
    """Group exact source identities, with numeric season/episode ordering."""
    groups = {}
    for raw in rows:
        row = dict(raw)
        key = row["source_key"]
        group = groups.setdefault(key, dict(source_key=key, title=row["title"], year=row.get("year", ""),
                                          media_type=row.get("media_type", "episode"), seasons={}, count=0))
        group["count"] += 1
        season = group["seasons"].setdefault(row["season"], dict(season=row["season"], episodes={}))
        episode = season["episodes"].setdefault(row["episode"], dict(episode=row["episode"], rows=[]))
        episode["rows"].append(row)
    result = sorted(groups.values(), key=lambda g: (g["title"].casefold(), g["year"], g["source_key"]))
    for group in result:
        group["seasons"] = sorted(group["seasons"].values(), key=lambda s: s["season"])
        for season in group["seasons"]:
            season["episodes"] = sorted(season["episodes"].values(), key=lambda e: e["episode"])
            for episode in season['episodes']:
                versions = list(dict.fromkeys((row.get('asset_key'), row.get('duration_ms')) for row in episode['rows']))
                episode['version_count'] = len(versions)
                for row in episode['rows']:
                    row['version_count'] = len(versions)
                    row['version_number'] = versions.index((row.get('asset_key'),row.get('duration_ms'))) + 1
    return result


def marker_browser(con, state, source_key="", season=None, page=1, episode_page=1):
    """Page series first; load marker forms only for the selected season."""
    total = con.execute("SELECT COUNT(*) FROM (SELECT source_key FROM skip_records WHERE status=? GROUP BY source_key)", (state,)).fetchone()[0]
    pages = max(1, (total + 19) // 20)
    page = min(page_number(page), pages)
    summary = """SELECT source_key,MIN(title) title,MIN(year) year,MIN(media_type) media_type,
      COUNT(*) count,COUNT(DISTINCT CAST(season AS TEXT)||':'||CAST(episode AS TEXT)) episode_count
      FROM skip_records WHERE status=?"""
    groups = [dict(row) for row in con.execute(summary + " GROUP BY source_key ORDER BY LOWER(MIN(title)),MIN(year),source_key LIMIT 20 OFFSET ?", (state, (page - 1) * 20))]
    selected = con.execute(summary + " AND source_key=? GROUP BY source_key", (state, source_key)).fetchone() if KEY.fullmatch(source_key) else None
    if selected and not any(g["source_key"] == source_key for g in groups):
        groups.insert(0, dict(selected))
    episode_page = page_number(episode_page)
    for group in groups:
        group.update(selected=bool(selected and group["source_key"] == source_key), seasons=[], movie_rows=[])
        if not group["selected"]:
            continue
        if group["media_type"] == "movie":
            group["movie_pages"] = max(1, (group["count"] + 49) // 50)
            episode_page = min(episode_page, group["movie_pages"])
            group["movie_rows"] = con.execute("SELECT * FROM skip_records WHERE status=? AND source_key=? ORDER BY id DESC LIMIT 50 OFFSET ?", (state, source_key, (episode_page - 1) * 50)).fetchall()
            continue
        seasons = con.execute("SELECT season,COUNT(*) count,COUNT(DISTINCT episode) episode_count FROM skip_records WHERE status=? AND source_key=? GROUP BY season ORDER BY season", (state, source_key)).fetchall()
        for raw in seasons:
            item = dict(raw, selected=raw["season"] == season, episodes=[], pages=max(1, (raw["episode_count"] + 24) // 25))
            if item["selected"]:
                episode_page = min(episode_page, item["pages"])
                numbers = [row[0] for row in con.execute("SELECT episode FROM skip_records WHERE status=? AND source_key=? AND season=? GROUP BY episode ORDER BY episode LIMIT 25 OFFSET ?", (state, source_key, season, (episode_page - 1) * 25))]
                if numbers:
                    placeholders = ",".join("?" for _ in numbers)
                    records = con.execute("SELECT * FROM skip_records WHERE status=? AND source_key=? AND season=? AND episode IN (" + placeholders + ") ORDER BY episode,CASE segment_type WHEN 'intro' THEN 0 WHEN 'recap' THEN 1 ELSE 2 END,id DESC", (state, source_key, season, *numbers)).fetchall()
                    item["episodes"] = media_groups(records)[0]["seasons"][0]["episodes"]
            group["seasons"].append(item)
    return dict(groups=groups, total=total, pages=pages, page=page, episode_page=episode_page,
                source_key=source_key if selected else "", season=season)


def wake_reference_jobs(con, source_key, season=None):
    sql = """UPDATE skip_jobs SET status='queued',attempts=0,updated_at=?
      WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE source_key=?"""
    params = [now(), source_key]
    if season is not None:
        sql += " AND season=?"
        params.append(season)
    sql += ") AND status IN ('no_reference','no_match','review')"
    con.execute(sql, params)


def review_record(con, row, decision, start, end, disabled, wake=True):
    """Shared single/bulk review: invalidate fingerprints and retain human decisions."""
    record_id = row['id']
    if decision == 'approve':
        con.execute("""UPDATE skip_records SET status='superseded',reviewed_at=? WHERE id<>?
          AND asset_key=? AND segment_type=? AND ABS(duration_ms-?)<=2000 AND status='approved'""",
          (now(), record_id, row['asset_key'], row['segment_type'], row['duration_ms']))
        if wake:
            wake_reference_jobs(con, row['source_key'])
    con.execute('DELETE FROM skip_fingerprints WHERE record_id=?', (record_id,))
    con.execute('DELETE FROM skip_auto_reference_checks WHERE record_id=?', (record_id,))
    con.execute('UPDATE skip_records SET status=?,start_ms=?,end_ms=?,disabled=?,reviewed_at=? WHERE id=?',
                ('approved' if decision == 'approve' else 'rejected', start, end, int(disabled), now(), record_id))
    con.execute('UPDATE skip_auto_evidence SET human_review=1 WHERE record_id=?', (record_id,))
    from skip_automation import retire_proposals
    retire_proposals(con, row, row['segment_type'], record_id)
    if decision == 'reject' or disabled:
        con.execute('INSERT OR REPLACE INTO skip_auto_blocks VALUES(?,?,?,?)',
                    (row['asset_key'], row['segment_type'], row['duration_ms'], now()))
    else:
        con.execute('DELETE FROM skip_auto_blocks WHERE asset_key=? AND kind=? AND ABS(duration_ms-?)<=2000',
                    (row['asset_key'], row['segment_type'], row['duration_ms']))


def approve_pending_scope(con, source_key, season=None):
    """Approve the whole selected series/season, with one effective marker per file/section."""
    from skip_release import approve_scope
    return approve_scope(con, source_key, season)


def install(app, db):
    from app import digest, web_auth
    from skip_analysis import register_asset, authorized_playlist, source_account
    with db() as con:
        migrate(con)

    def device(con):
        token = request.headers.get("Authorization", "")
        if not token.startswith("Bearer ") or not token[7:].strip():
            abort(401)
        row = con.execute("SELECT d.*,c.enabled customer_enabled FROM devices d JOIN customers c ON c.id=d.customer_id WHERE d.session_token_hash=?", (digest(token[7:].strip()),)).fetchone()
        if row is None or not row["enabled"] or not row["customer_enabled"]:
            abort(401)
        return row

    def body():
        if not request.is_json or (request.content_length or 0) > 16_000:
            abort(413 if (request.content_length or 0) > 16_000 else 415)
        return request.get_json(silent=True)

    def rate(con, row, action, limit):
        window = int(time.time()) // 60
        con.execute("DELETE FROM skip_rate WHERE window<?", (window - 5,))
        con.execute("INSERT INTO skip_rate VALUES(?,?,?,1) ON CONFLICT(device_id,action,window) DO UPDATE SET count=count+1", (row["id"], action, window))
        return con.execute("SELECT count FROM skip_rate WHERE device_id=? AND action=? AND window=?", (row["id"], action, window)).fetchone()[0] <= limit

    @app.post("/v1/device/skip/submit")
    def v082_skip_submit():
        raw = body()
        try:
            data = descriptor(raw)
            kind = raw.get("segment_type")
            off = raw.get("disabled", False)
            if type(off) is not bool:
                raise ValueError("disabled")
            start = integer(raw, "start_ms", 0, data["duration_ms"], 0)
            end = integer(raw, "end_ms", 0, data["duration_ms"], 0)
            if not valid_range(kind, start, end, data["duration_ms"], off):
                raise ValueError("range")
        except (ValueError, TypeError):
            return jsonify(error="invalid_skip_marker"), 400
        with db() as con:
            row = device(con)
            if not rate(con, row, "submit", 30):
                return jsonify(error="rate_limited"), 429
            registered = register_asset(con, raw, data, row)
            saved = add_record(con, data, kind, start, end, off, row)
            from skip_release import enabled as release_enabled
            asset = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (data['asset_key'],)).fetchone() if registered else None
            if (asset and release_enabled(con, asset['playlist_id']) and saved['status'] == 'pending'
                    and all(asset[key] == data[key] for key in ('source_key','media_type','season','episode','duration_ms'))):
                record = con.execute('SELECT * FROM skip_records WHERE id=?', (saved['id'],)).fetchone()
                review_record(con, record, 'approve', start, end, off)
                saved = dict(id=saved['id'], status='approved')
            return jsonify(id=saved["id"], status=saved["status"]), 200

    @app.post("/v1/device/skip/lookup")
    def v082_skip_lookup():
        raw = body()
        try:
            data = descriptor(raw)
        except (ValueError, TypeError):
            return jsonify(error="invalid_media_descriptor"), 400
        with db() as con:
            row = device(con)
            if not rate(con, row, "lookup", 60):
                return jsonify(error="rate_limited"), 429
            records = con.execute("""SELECT * FROM skip_records WHERE asset_key=? AND media_type=? AND season=? AND episode=?
              AND ABS(duration_ms-?)<=2000 AND status='approved' ORDER BY reviewed_at DESC,id DESC""",
              (data["asset_key"], data["media_type"], data["season"], data["episode"], data["duration_ms"])).fetchall()
            identity = con.execute("SELECT imdb_id,tmdb_id FROM skip_identities WHERE source_key=?", (data["source_key"],)).fetchone()
            registered = register_asset(con, raw, data, row)
            seen = set(); segments = []
            for record in records:
                if record["segment_type"] in seen:
                    continue
                seen.add(record["segment_type"])
                segments.append({k: record[k] for k in ("segment_type", "start_ms", "end_ms", "duration_ms", "status", "source") } | {"disabled": bool(record["disabled"])})
            return jsonify(asset_key=data["asset_key"], source_key=data["source_key"], duration_ms=data["duration_ms"],
                           segments=segments, identity=dict(identity) if identity else {}, analysis="available" if registered else "unavailable")

    @app.post("/v1/device/skip/presence")
    def v082_skip_presence():
        raw = body()
        with db() as con:
            row = device(con)
            try:
                playlist = authorized_playlist(con, row, integer(raw, "playlist_id", 1, 2_147_483_647))
            except (ValueError, TypeError):
                playlist = None
            if playlist is None:
                return jsonify(error="playlist_not_available"), 404
            con.execute("INSERT INTO skip_presence VALUES(?,?,?) ON CONFLICT(device_id) DO UPDATE SET playlist_id=excluded.playlist_id,expires_at=excluded.expires_at", (row["id"], playlist["id"], int(time.time()) + 70))
        return jsonify(status="recorded")

    def csrf():
        supplied = request.form.get("csrf", "")
        known = session.get("skip_csrf", "")
        if not known or not secrets.compare_digest(supplied, known):
            abort(403)

    @app.get("/admin/skip")
    def v082_skip_dashboard():
        guard = web_auth()
        if guard:
            return guard
        session.setdefault("skip_csrf", secrets.token_urlsafe(32))
        state = request.args.get("state", "pending")
        if state not in ("pending", "approved", "rejected", "superseded"):
            state = "pending"
        with db() as con:
            raw_season = request.args.get("season", "")
            season = int(raw_season) if re.fullmatch(r"\d{1,4}", raw_season) and int(raw_season) <= 1000 else None
            browser = marker_browser(con, state, request.args.get("series", ""), season,
                                     request.args.get("page", "1"), request.args.get("episode_page", "1"))
            sources = con.execute("SELECT p.id,p.name,c.name customer_name,COALESCE(s.enabled,0) enabled,COALESCE(a.enabled,0) automatic,COALESCE(a.online_enabled,0) online_enabled,COALESCE(r.enabled,1) auto_accept FROM customer_playlists p JOIN customers c ON c.id=p.customer_id LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id LEFT JOIN skip_auto_settings a ON a.playlist_id=p.id LEFT JOIN skip_release_settings r ON r.playlist_id=p.id ORDER BY c.name,p.name LIMIT 200").fetchall()
            jobs = con.execute("SELECT j.*,a.title,a.year,a.source_key,a.media_type,a.season,a.episode FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key ORDER BY j.id DESC LIMIT 20").fetchall()
            online_status = con.execute("SELECT o.detail,a.title,a.year,a.source_key,a.media_type,a.season,a.episode FROM skip_auto_online o JOIN skip_assets a ON a.asset_key=o.asset_key ORDER BY o.checked_at DESC LIMIT 10").fetchall()
            tmdb_ready = bool(con.execute("SELECT 1 FROM skip_auto_metadata_config WHERE name='tmdb_api_key'").fetchone() or os.environ.get("EPIMEDIAHUB_TMDB_API_KEY"))
            from skip_catalogue import dashboard as catalogue_dashboard, daily_limit
            catalogues = catalogue_dashboard(con)
            audio_limit = daily_limit(con)
            from skip_progress import overview
            progress = overview(con, request.args.get('progress_filter','all'), request.args.get('progress_search',''), request.args.get('progress_page','1'))
        selected_episode = page_number(request.args.get("episode", ""), 0)
        return render_template("skip_markers.html", browser=browser, sources=sources, job_groups=media_groups(jobs), online_groups=media_groups(online_status), tmdb_ready=tmdb_ready, catalogues=catalogues, audio_limit=audio_limit, progress=progress, state=state, selected_episode=selected_episode, csrf=session["skip_csrf"], timecode=timecode, notice=request.args.get("notice", ""))

    def return_to_marker(row, notice):
        state = request.form.get("return_state", "pending")
        if state not in ("pending", "approved", "rejected", "superseded"):
            state = "pending"
        return redirect(url_for("v082_skip_dashboard", state=state, series=row["source_key"],
                                season=row["season"], episode=row["episode"],
                                page=page_number(request.form.get("return_page", "1")),
                                episode_page=page_number(request.form.get("return_episode_page", "1")),
                                _anchor="episode-" + str(row["episode"]), notice=notice))

    @app.post("/admin/skip/<int:record_id>/review")
    def v082_skip_review(record_id):
        guard = web_auth()
        if guard:
            return guard
        csrf()
        decision = request.form.get("decision")
        if decision not in ("approve", "reject"):
            abort(400)
        with db() as con:
            row = con.execute("SELECT * FROM skip_records WHERE id=?", (record_id,)).fetchone()
            if row is None:
                abort(404)
            off = request.form.get("disabled") == "1"
            try:
                start = parse_time(request.form.get("start", timecode(row["start_ms"])))
                end = parse_time(request.form.get("end", timecode(row["end_ms"])))
            except ValueError:
                abort(400)
            if decision == "approve" and not valid_range(row["segment_type"], start, end, row["duration_ms"], off):
                abort(400)
            review_record(con, row, decision, start, end, off)
        return return_to_marker(row, "Zeitmarke freigegeben" if decision == "approve" else "Vorschlag abgelehnt")

    @app.post('/admin/skip/bulk-review')
    def v082_skip_bulk_review():
        guard = web_auth()
        if guard:
            return guard
        csrf()
        source_key = request.form.get('source_key', '')
        scope = request.form.get('scope', '')
        if not KEY.fullmatch(source_key) or scope not in ('series', 'season'):
            abort(400)
        raw_season = request.form.get('season', '')
        season = None
        if scope == 'season':
            if not re.fullmatch(r'\d{1,4}', raw_season) or int(raw_season) > 1000:
                abort(400)
            season = int(raw_season)
        with db() as con:
            con.execute('BEGIN IMMEDIATE')
            if not con.execute("SELECT 1 FROM skip_records WHERE source_key=? AND media_type='episode' LIMIT 1", (source_key,)).fetchone():
                abort(404)
            counts = approve_pending_scope(con, source_key, season)
        notice = f"{counts['approved']} Zeitmarken freigegeben"
        for key, label in (('duplicates', 'doppelte Vorschläge zusammengeführt'),
                           ('conflicts', 'abweichende Varianten automatisch ausgewählt'),
                           ('protected', 'alte Vorschläge erledigt; bestehende Entscheidungen beibehalten'),
                           ('invalid', 'ungültige Vorschläge bleiben zur Einzelprüfung')):
            if counts[key]:
                notice += f" · {counts[key]} {label}"
        return redirect(url_for('v082_skip_dashboard', state='approved' if counts['approved'] else 'pending', series=source_key, season=season,
                                page=page_number(request.form.get('return_page', '1')),
                                episode_page=page_number(request.form.get('return_episode_page', '1')),
                                _anchor='review-result',
                                notice=notice))

    @app.post("/admin/skip/<int:record_id>/identity")
    def v082_skip_identity(record_id):
        guard = web_auth()
        if guard:
            return guard
        csrf()
        imdb = request.form.get("imdb_id", "").strip()
        tmdb = request.form.get("tmdb_id", "0").strip()
        if (imdb and not re.fullmatch(r"tt\d{7,10}", imdb)) or not re.fullmatch(r"\d{1,9}", tmdb) or int(tmdb) > 100_000_000 or (not imdb and int(tmdb) == 0):
            abort(400)
        with db() as con:
            row = con.execute("SELECT * FROM skip_records WHERE id=?", (record_id,)).fetchone()
            if row is None:
                abort(404)
            con.execute("INSERT INTO skip_identities VALUES(?,?,?,?,?,?) ON CONFLICT(source_key) DO UPDATE SET imdb_id=excluded.imdb_id,tmdb_id=excluded.tmdb_id,title=excluded.title,year=excluded.year,updated_at=excluded.updated_at", (row["source_key"], imdb, int(tmdb), row["title"], row["year"], now()))
            con.execute("DELETE FROM skip_auto_online WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE source_key=?)", (row["source_key"],))
            con.execute("UPDATE skip_jobs SET status='queued',attempts=0,updated_at=? WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE source_key=?) AND status IN ('no_reference','no_match','review','failed')", (now(), row["source_key"]))
        return return_to_marker(row, "Titelzuordnung gespeichert")

    @app.post("/admin/skip/analysis/<int:playlist_id>")
    def v082_skip_analysis_source(playlist_id):
        guard = web_auth()
        if guard:
            return guard
        csrf()
        enabled = request.form.get("enabled") == "1"
        with db() as con:
            row = con.execute("SELECT * FROM customer_playlists WHERE id=?", (playlist_id,)).fetchone()
            if row is None:
                abort(404)
            from skip_analysis import configured_source
            if enabled:
                try:
                    configured_source(row)
                except ValueError:
                    return redirect(url_for("v082_skip_dashboard", notice="Diese Playlist eignet sich nicht für eine sichere Hintergrundanalyse"))
            con.execute("INSERT INTO skip_analysis_sources VALUES(?,?,?) ON CONFLICT(playlist_id) DO UPDATE SET enabled=excluded.enabled,updated_at=excluded.updated_at", (playlist_id, int(enabled), now()))
            if enabled:
                con.execute("UPDATE skip_jobs SET status='queued',attempts=0,updated_at=? WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE playlist_id=?) AND status IN ('disabled','failed','unmatched','no_match','no_reference')", (now(), playlist_id))
        return redirect(url_for("v082_skip_dashboard", notice="Audioanalyse aktiviert" if enabled else "Audioanalyse ausgeschaltet"))

    @app.post("/admin/skip/automatic/<int:playlist_id>")
    def v082_skip_automatic_source(playlist_id):
        guard = web_auth()
        if guard:
            return guard
        csrf()
        automatic = request.form.get("enabled") == "1"
        online = request.form.get("online") == "1"
        auto_accept = request.form.get('auto_accept') == '1'
        with db() as con:
            playlist = con.execute("SELECT p.* FROM customer_playlists p JOIN customers c ON c.id=p.customer_id AND c.enabled=1 WHERE p.id=?", (playlist_id,)).fetchone()
            source = con.execute("SELECT enabled FROM skip_analysis_sources WHERE playlist_id=?", (playlist_id,)).fetchone()
            if playlist is None:
                abort(404)
            if automatic and (not source or not source[0]):
                return redirect(url_for("v082_skip_dashboard", notice="Zuerst die erlaubte Audioanalyse für diese Playlist aktivieren"))
            previous = con.execute('SELECT enabled FROM skip_auto_settings WHERE playlist_id=?', (playlist_id,)).fetchone()
            con.execute("INSERT OR REPLACE INTO skip_auto_settings VALUES(?,?,?,?)", (playlist_id, int(automatic), int(online), now()))
            con.execute('INSERT OR REPLACE INTO skip_release_settings VALUES(?,?,?)', (playlist_id, int(auto_accept), now()))
            if auto_accept:
                from skip_release import accept_pending
                accept_pending(con, playlist_id=playlist_id)
            if automatic and (not previous or not previous[0]):
                con.execute("UPDATE skip_jobs SET status='queued',attempts=0,updated_at=? WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE playlist_id=?) AND status IN ('disabled','failed','unmatched','no_match','no_reference','review','done')", (now(), playlist_id))
                con.execute("DELETE FROM skip_auto_series WHERE playlist_id=?", (playlist_id,))
        return redirect(url_for("v082_skip_dashboard", notice=('Automatik gespeichert · Erkannte Zeitmarken werden automatisch freigegeben' if auto_accept else 'Automatik gespeichert · Neue Vorschläge werden manuell geprüft')))

    @app.post("/admin/skip/catalogue")
    def v082_skip_catalogue():
        guard = web_auth()
        if guard:
            return guard
        csrf()
        from skip_catalogue import start, DEFAULT_DAILY_LIMIT
        raw_limit = request.form.get("daily_limit", str(DEFAULT_DAILY_LIMIT))
        if not re.fullmatch(r"\d{1,3}", raw_limit) or not 1 <= int(raw_limit) <= 500:
            abort(400)
        count = 0
        with db() as con:
            playlists = con.execute("SELECT playlist_id FROM skip_auto_settings WHERE enabled=1").fetchall()
            for playlist in playlists:
                count += int(start(con, playlist[0]))
            if count:
                con.execute("INSERT OR REPLACE INTO skip_catalogue_config VALUES('daily_limit',?,?)", (int(raw_limit), now()))
        notice = ("Gesamtkatalog eingeplant; danach täglich ab 03:00 Uhr neue und geänderte Folgen prüfen"
                  if count else "Zuerst Audioanalyse und Staffelautomatik für eine Playlist aktivieren")
        return redirect(url_for("v082_skip_dashboard", notice=notice))

    @app.post("/admin/skip/catalogue/<int:playlist_id>")
    def v082_skip_catalogue_source(playlist_id):
        guard = web_auth()
        if guard:
            return guard
        csrf()
        from skip_catalogue import start
        with db() as con:
            if not con.execute("SELECT 1 FROM customer_playlists WHERE id=?", (playlist_id,)).fetchone():
                abort(404)
            if request.form.get("enabled") == "1":
                if not start(con, playlist_id):
                    return redirect(url_for("v082_skip_dashboard", notice="Zuerst Audioanalyse und Staffelautomatik aktivieren"))
            else:
                con.execute("UPDATE skip_catalogue_settings SET enabled=0,updated_at=? WHERE playlist_id=?", (now(), playlist_id))
        return redirect(url_for("v082_skip_dashboard", notice="Katalogprüfung aktiviert" if request.form.get("enabled") == "1" else "Weitere Katalogprüfungen ausgeschaltet; eingeplante Folgen bleiben in der Analysewarteschlange"))

    @app.post("/admin/skip/tmdb")
    def v082_skip_tmdb_config():
        guard = web_auth()
        if guard:
            return guard
        csrf()
        token = request.form.get("api_key", "").strip()
        remove = request.form.get("remove") == "1"
        if not remove and not re.fullmatch(r"[a-fA-F0-9]{32}", token):
            return redirect(url_for("v082_skip_dashboard", notice="Bitte einen gültigen TMDB-API-Schlüssel (v3) eintragen"))
        with db() as con:
            con.execute("DELETE FROM skip_auto_online_cooldown WHERE service='tmdb'")
            if remove:
                con.execute("DELETE FROM skip_auto_metadata_config WHERE name='tmdb_api_key'")
            else:
                con.execute("INSERT OR REPLACE INTO skip_auto_metadata_config VALUES('tmdb_api_key',?,?)", (token, now()))
                con.execute("DELETE FROM skip_auto_online")
                con.execute("DELETE FROM skip_auto_online_retry")
                con.execute("UPDATE skip_jobs SET status='queued',attempts=0,updated_at=? WHERE status IN ('no_reference','no_match','review','failed') AND asset_key IN (SELECT a.asset_key FROM skip_assets a JOIN skip_auto_settings s ON s.playlist_id=a.playlist_id AND s.enabled=1 AND s.online_enabled=1)", (now(),))
        return redirect(url_for("v082_skip_dashboard", notice="Schlüssel entfernt" if remove else "Schlüssel für die Seriennamenssuche gespeichert"))

    previous_health = app.view_functions["health"]
    def health():
        response = previous_health()
        data = response.get_json()
        data["api_version"] = "0.8.2"
        data["features"] = {"reviewed_skip_markers": True, "skip_analysis_queue": True, "skip_season_automation": True, "skip_online_candidates": True, "skip_full_catalogue": True, "skip_nightly_catalogue": True, "skip_high_audio_approval": True, "skip_proposal_dedup": True, "skip_online_error_details": True, "skip_language_priority": True, "skip_bulk_review": True, "skip_network_address_fallback": True, "skip_automatic_acceptance": True, "skip_series_progress": True, "skip_database_concurrency": True}
        return jsonify(data)
    app.view_functions["health"] = health
