"""Reviewed skip markers bound to one provider file and its measured runtime.

Device proposals are private pending records. Only an authenticated administrator
can publish them to other devices. No provider URL or password is accepted here.
"""
from __future__ import annotations

import hashlib
import json
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
            saved = add_record(con, data, kind, start, end, off, row)
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
            rows = con.execute("SELECT * FROM skip_records WHERE status=? ORDER BY created_at DESC,id DESC LIMIT 100", (state,)).fetchall()
            sources = con.execute("SELECT p.id,p.name,c.name customer_name,COALESCE(s.enabled,0) enabled FROM customer_playlists p JOIN customers c ON c.id=p.customer_id LEFT JOIN skip_analysis_sources s ON s.playlist_id=p.id ORDER BY c.name,p.name LIMIT 200").fetchall()
            jobs = con.execute("SELECT j.*,a.title,a.season,a.episode FROM skip_jobs j JOIN skip_assets a ON a.asset_key=j.asset_key ORDER BY j.id DESC LIMIT 20").fetchall()
        return render_template("skip_markers.html", rows=rows, sources=sources, jobs=jobs, state=state, csrf=session["skip_csrf"], timecode=timecode, notice=request.args.get("notice", ""))

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
            if decision == "approve":
                con.execute("UPDATE skip_records SET status='superseded',reviewed_at=? WHERE id<>? AND asset_key=? AND segment_type=? AND ABS(duration_ms-?)<=2000 AND status='approved'", (now(), record_id, row["asset_key"], row["segment_type"], row["duration_ms"]))
                con.execute("UPDATE skip_jobs SET status='queued',attempts=0,updated_at=? WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE source_key=?) AND status IN ('no_reference','no_match','done','review')", (now(), row["source_key"]))
            con.execute("UPDATE skip_records SET status=?,start_ms=?,end_ms=?,disabled=?,reviewed_at=? WHERE id=?", ("approved" if decision == "approve" else "rejected", start, end, int(off), now(), record_id))
        return redirect(url_for("v082_skip_dashboard", notice="Zeitmarke freigegeben" if decision == "approve" else "Vorschlag abgelehnt"))

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
        return redirect(url_for("v082_skip_dashboard", notice="Titelzuordnung gespeichert"))

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

    previous_health = app.view_functions["health"]
    def health():
        response = previous_health()
        data = response.get_json()
        data["api_version"] = "0.8.2"
        data["features"] = {"reviewed_skip_markers": True, "skip_analysis_queue": True}
        return jsonify(data)
    app.view_functions["health"] = health
