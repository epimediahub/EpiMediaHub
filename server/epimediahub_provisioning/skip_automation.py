"""Bounded season discovery and evidence-based publishing for the existing player.

External databases provide suggestions, never file identity. Human corrections
take precedence, and machine approvals cannot become independent human evidence.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from math import ceil
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request

from skip_analysis import (configured_source, source_url, provider_asset_key,
                           provider_proxy, probe, fingerprint, matching_offset,
                           chapter_candidates)
from skip_markers import add_record, now, valid_range

WINDOW_MS = 600_000
AUTO_CONFIDENCE = .92
BOUNDARY_TOLERANCE = 500
MAX_SEASON_EPISODES = 200
PROPOSAL_SOURCES = ('audio', 'chapter', 'theintrodb', 'audio_repetition')
PROPOSAL_RANK = {'audio': 4, 'chapter': 3, 'theintrodb': 2, 'audio_repetition': 1}
POLICY_VERSION = 'high_audio_v2'


def migrate(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS skip_auto_settings(
        playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
        enabled INTEGER NOT NULL DEFAULT 0,online_enabled INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_series(
        source_key TEXT NOT NULL,playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
        season INTEGER NOT NULL,series_id TEXT NOT NULL DEFAULT '',checked_at INTEGER NOT NULL DEFAULT 0,
        detail TEXT NOT NULL DEFAULT '',PRIMARY KEY(source_key,playlist_id,season));
      CREATE TABLE IF NOT EXISTS skip_auto_catalogue(
        playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
        ids_json TEXT NOT NULL,checked_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_assets(
        asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,created_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_windows(
        asset_key TEXT NOT NULL REFERENCES skip_assets(asset_key) ON DELETE CASCADE,kind TEXT NOT NULL,
        words_json TEXT NOT NULL,step_ms REAL NOT NULL,offset_ms INTEGER NOT NULL,
        length_ms INTEGER NOT NULL,duration_ms INTEGER NOT NULL,created_at TEXT NOT NULL,
        PRIMARY KEY(asset_key,kind));
      CREATE TABLE IF NOT EXISTS skip_auto_evidence(
        record_id INTEGER PRIMARY KEY REFERENCES skip_records(id) ON DELETE CASCADE,
        evidence_json TEXT NOT NULL,human_review INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS skip_auto_blocks(
        asset_key TEXT NOT NULL,kind TEXT NOT NULL,duration_ms INTEGER NOT NULL,updated_at TEXT NOT NULL,
        PRIMARY KEY(asset_key,kind,duration_ms));
      CREATE TABLE IF NOT EXISTS skip_auto_identities(
        source_key TEXT PRIMARY KEY,imdb_id TEXT NOT NULL DEFAULT '',tmdb_id INTEGER NOT NULL DEFAULT 0,
        method TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_online(
        asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        duration_ms INTEGER NOT NULL,segments_json TEXT NOT NULL,detail TEXT NOT NULL,checked_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_analysis_budget(day TEXT PRIMARY KEY,count INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_metadata_config(
        name TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_maintenance(
        name TEXT PRIMARY KEY,completed_at TEXT NOT NULL);
    """)
    from skip_catalogue import migrate as catalogue_migrate
    catalogue_migrate(con)
    maintain_proposals(con)


def enabled(con, playlist_id, online=False):
    if not con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='skip_auto_settings'").fetchone():
        return False  # Read-only diagnostic snapshots from older installations.
    if not con.execute("SELECT 1 FROM skip_auto_settings WHERE playlist_id=? AND enabled=1", (playlist_id,)).fetchone():
        return False
    row = con.execute("""SELECT a.* FROM skip_auto_settings a
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE a.playlist_id=? AND a.enabled=1""", (playlist_id,)).fetchone()
    return bool(row and (not online or row["online_enabled"]))


def fetch_json(url, busy=lambda: False, limit=1_000_000):
    """Use the same validated, pinned, bounded provider transport for every host."""
    if busy():
        raise ValueError("analysis_deferred")
    with provider_proxy(url, busy) as local:
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(local, timeout=35) as response:
            chunks, size, started = [], 0, time.monotonic()
            while True:
                if busy():
                    raise ValueError("analysis_deferred")
                if time.monotonic() - started > 35:
                    raise ValueError("metadata_limit")
                chunk = response.read(min(65_536, limit + 1 - size))
                if not chunk:
                    break
                chunks.append(chunk); size += len(chunk)
                if size > limit:
                    raise ValueError("metadata_limit")
    return json.loads(b"".join(chunks))


def number(value, low=1, high=10**12 - 1):
    if isinstance(value, bool) or not re.fullmatch(r"\d{1,12}", str(value)):
        return None
    result = int(value)
    return result if low <= result <= high else None


def provider_api(playlist, action, busy, *, _limit=8_000_000, **params):
    cfg = configured_source(playlist)
    query = dict(username=cfg["xtream_username"], password=cfg["xtream_password"], action=action, **params)
    return fetch_json(cfg["xtream_server"].rstrip("/") + "/player_api.php?" + urllib.parse.urlencode(query), busy, _limit)


def series_key(playlist, asset, series_id):
    uri = urllib.parse.urlsplit(configured_source(playlist)["xtream_server"])
    origin = f"{uri.hostname}:{uri.port if uri.port is not None else -1}"
    return hashlib.sha256(f"{origin}|true|{series_id}|{asset['title']}|{asset['year']}".encode()).hexdigest()


def season_entries(info, season):
    """Accept unambiguous structured numbering; never infer episodes from names."""
    if not isinstance(info, dict) or not isinstance(info.get("episodes"), dict):
        return []
    items = info["episodes"].get(str(season), [])
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_SEASON_EPISODES:
        return []
    result, ids, numbers = [], set(), set()
    for row in items:
        if not isinstance(row, dict):
            return []
        stream, episode = number(row.get("id")), number(row.get("episode_num"), high=10_000)
        reported_season = number(row.get("season", season), low=0, high=1000)
        extension = row.get("container_extension", "mp4")
        if (stream is None or episode is None or reported_season != season
                or extension not in ("mp4", "mkv", "m4v", "avi", "ts", "mpeg", "mpg")
                or stream in ids or episode in numbers):
            return []
        ids.add(stream); numbers.add(episode)
        result.append(dict(stream_id=str(stream), episode=episode, extension=extension))
    return result


def discover_one(db, busy_factory):
    """Enumerate one previously watched season per idle tick, at most daily."""
    with db() as con:
        anchor = con.execute("""SELECT a.* FROM skip_assets a
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          LEFT JOIN skip_auto_assets d ON d.asset_key=a.asset_key
          LEFT JOIN skip_auto_series z ON z.source_key=a.source_key AND z.playlist_id=a.playlist_id AND z.season=a.season
          WHERE a.media_type='episode' AND d.asset_key IS NULL
          AND NOT EXISTS(SELECT 1 FROM skip_catalogue_settings cs WHERE cs.playlist_id=a.playlist_id AND cs.enabled=1)
          AND COALESCE(z.checked_at,0)<? ORDER BY COALESCE(z.checked_at,0),a.updated_at DESC LIMIT 1""",
          (int(time.time()) - 86400,)).fetchone()
        if not anchor:
            return "idle"
        playlist = con.execute("SELECT * FROM customer_playlists WHERE id=?", (anchor["playlist_id"],)).fetchone()
        cached = con.execute("SELECT * FROM skip_auto_catalogue WHERE playlist_id=?", (playlist["id"],)).fetchone()
        previous = con.execute("SELECT series_id FROM skip_auto_series WHERE source_key=? AND playlist_id=? AND season=?",
                               (anchor["source_key"], playlist["id"], anchor["season"])).fetchone()
    busy = busy_factory(db, [playlist])
    if busy():
        return "queued"
    series_id, detail, entries = "", "Staffel im Anbieterkatalog nicht eindeutig zugeordnet", []
    try:
        if previous and previous[0]:
            candidates = [previous[0]]
        else:
            if not cached or cached["checked_at"] < time.time() - 86400:
                catalogue = provider_api(playlist, "get_series", busy)
                if not isinstance(catalogue, list) or len(catalogue) > 10_000:
                    raise ValueError("metadata_limit")
                ids = sorted({str(n) for row in catalogue if isinstance(row, dict)
                              and (n := number(row.get("series_id"))) is not None})
                with db() as con:
                    con.execute("INSERT OR REPLACE INTO skip_auto_catalogue VALUES(?,?,?)", (playlist["id"], json.dumps(ids), int(time.time())))
            else:
                ids = json.loads(cached["ids_json"])
            candidates = [n for n in ids if series_key(playlist, anchor, n) == anchor["source_key"]]
        if len(candidates) == 1:
            info = provider_api(playlist, "get_series_info", busy, series_id=candidates[0])
            entries = season_entries(info, anchor["season"])
            same = [x for x in entries if x["stream_id"] == anchor["stream_id"]
                    and x["episode"] == anchor["episode"] and x["extension"] == anchor["extension"]]
            if len(same) == 1 and series_key(playlist, anchor, candidates[0]) == anchor["source_key"]:
                series_id, detail = candidates[0], "Staffel zugeordnet; weitere Folgen automatisch eingeplant"
            else:
                entries = []
    except ValueError as error:
        if str(error) == "analysis_deferred":
            return "queued"
        detail = "Anbieterkatalog derzeit nicht auswertbar; vorhandene Analyse bleibt nutzbar"
    except (OSError, TypeError, KeyError, json.JSONDecodeError):
        detail = "Anbieterkatalog derzeit nicht auswertbar; vorhandene Analyse bleibt nutzbar"
    with db() as con:
        if not enabled(con, playlist["id"]):
            return "disabled"
        con.execute("INSERT OR REPLACE INTO skip_auto_series VALUES(?,?,?,?,?,?)",
                    (anchor["source_key"], playlist["id"], anchor["season"], series_id, int(time.time()), detail))
        # Prioritise the next episodes, then the earlier ones, without requeueing completed work.
        for episode in sorted(entries, key=lambda x: (x["episode"] <= anchor["episode"], x["episode"])):
            data = dict(anchor) | episode
            key = provider_asset_key(source_url(playlist, data), "episode")
            existing = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (key,)).fetchone()
            if existing:
                continue  # Do not relabel a file previously identified by a client.
            con.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (key, anchor["source_key"], playlist["id"], episode["stream_id"], episode["extension"],
                         "episode", 0, anchor["season"], episode["episode"], anchor["title"], anchor["year"], now()))
            con.execute("INSERT INTO skip_auto_assets VALUES(?,?)", (key, now()))
            con.execute("INSERT INTO skip_jobs(asset_key,status,created_at,updated_at) VALUES(?,'queued',?,?)", (key, now(), now()))
    return "discovered" if entries else "unmapped"


def clean_title(value):
    value = str(value).strip()
    languages = r"(?:DE|GER|GERMAN|IT|ITA|EN|ENG|FR|TR|ES|US|UK|HD|FHD|UHD|4K)"
    for _ in range(5):
        value = re.sub(rf"^(?:\[{languages}\]|{languages}\s*[|:–-])\s*", "", value, flags=re.I)
    value = re.sub(r"\s*(?:S\d{1,3}\s*E\d{1,4}|\d{1,3}x\d{1,4}).*$", "", value, flags=re.I)
    value = re.sub(r"\s*[(\[]?(?:4K|UHD|FHD|FULL HD|HD|SD|HEVC|H[ .]?26[45]|1080P|720P)[)\]]?\s*$", "", value, flags=re.I)
    value = re.sub(r"\s*[([](?:19|20)\d{2}[)\]]\s*$", "", value)
    text = unicodedata.normalize("NFKD", value.casefold())
    return " ".join(re.findall(r"[a-z0-9]+", "".join(x for x in text if not unicodedata.combining(x))))


def identity(con, asset):
    # An explicit dashboard correction always takes priority over a machine match.
    row = con.execute("SELECT imdb_id,tmdb_id FROM skip_identities WHERE source_key=?", (asset["source_key"],)).fetchone()
    if row:
        return dict(row, verified=True)
    row = con.execute("SELECT imdb_id,tmdb_id,method FROM skip_auto_identities WHERE source_key=?", (asset["source_key"],)).fetchone()
    return dict(row, verified=row["method"] == "tmdb_title_year_episode") if row else None


def resolve_identity(db, asset, busy):
    with db() as con:
        known = identity(con, asset)
    with db() as con:
        configured = con.execute("SELECT value FROM skip_auto_metadata_config WHERE name='tmdb_api_key'").fetchone()
    token = configured[0] if configured else os.environ.get("EPIMEDIAHUB_TMDB_API_KEY", "")
    if known and (known["verified"] or not token):
        return known
    if not token:
        return None
    def api(path, **params):
        return fetch_json("https://api.themoviedb.org/3/" + path + "?" + urllib.parse.urlencode(dict(api_key=token, language="de-DE", **params)), busy)
    search_title = clean_title(asset["title"])
    if not search_title:
        return None
    results = api("search/tv", query=search_title, include_adult="false").get("results", [])
    candidates = [row for row in results[:20] if isinstance(row, dict)
                  and clean_title(asset["title"]) in {clean_title(row.get("name", "")), clean_title(row.get("original_name", ""))}
                  and asset["year"] and str(row.get("first_air_date", ""))[:4] == asset["year"]
                  and number(row.get("id"), high=100_000_000)]
    if len(candidates) != 1:
        return None
    tmdb = int(candidates[0]["id"])
    details = api(f"tv/{tmdb}/season/{asset['season']}/episode/{asset['episode']}")
    if details.get("season_number") != asset["season"] or details.get("episode_number") != asset["episode"]:
        return None
    external = api(f"tv/{tmdb}/external_ids")
    imdb = external.get("imdb_id") or ""
    if imdb and not re.fullmatch(r"tt\d{7,10}", str(imdb)):
        return None
    with db() as con:
        if not enabled(con, asset["playlist_id"], online=True):
            return None
        con.execute("""INSERT INTO skip_auto_identities VALUES(?,?,?,?,?)
          ON CONFLICT(source_key) DO UPDATE SET imdb_id=excluded.imdb_id,tmdb_id=excluded.tmdb_id,
          method=excluded.method,updated_at=excluded.updated_at WHERE skip_auto_identities.method='client_id_hint'""",
                    (asset["source_key"], imdb, tmdb, "tmdb_title_year_episode", now()))
        return identity(con, asset)


def parse_online(body, duration):
    """TheIntroDB v3 uses millisecond arrays and null for a media boundary."""
    if not isinstance(body, dict) or body.get("type") != "tv":
        return []
    result = []
    for field, kind in (("intro", "intro"), ("recap", "recap"), ("credits", "outro")):
        rows = body.get(field, [])
        if not isinstance(rows, list) or len(rows) > 10:
            continue
        for row in rows:
            if not isinstance(row, dict) or "start_ms" not in row or "end_ms" not in row:
                continue
            start = 0 if row["start_ms"] is None else row["start_ms"]
            end = duration if row["end_ms"] is None else row["end_ms"]
            if type(start) is int and type(end) is int and valid_range(kind, start, end, duration):
                result.append(dict(kind=kind, start=start, end=end, source="theintrodb"))
    return result


def online_segments(db, asset, busy):
    with db() as con:
        if not enabled(con, asset["playlist_id"], online=True):
            return []
        cache = con.execute("SELECT * FROM skip_auto_online WHERE asset_key=?", (asset["asset_key"],)).fetchone()
        if cache and cache["duration_ms"] == asset["duration_ms"] and cache["checked_at"] > time.time() - 86400:
            return json.loads(cache["segments_json"])
    segments, detail = [], "Keine eindeutige Titelkennung für die Online-Abfrage"
    try:
        ids = resolve_identity(db, asset, busy)
        if ids:
            query = {"tmdb_id": ids["tmdb_id"]} if ids.get("tmdb_id") else {"imdb_id": ids["imdb_id"]}
            query.update(season=asset["season"], episode=asset["episode"], duration_ms=asset["duration_ms"])
            body = fetch_json("https://api.theintrodb.org/v3/media?" + urllib.parse.urlencode(query), busy)
            # Reject a conflicting canonical series ID instead of accepting a provider fallback.
            if not ids.get("tmdb_id") or body.get("tmdb_id") == ids["tmdb_id"]:
                segments = [x | {"identity_verified": ids["verified"]} for x in parse_online(body, asset["duration_ms"])]
            detail = "Online-Zeiten verfügbar" if segments else "Keine passenden Online-Zeiten vorhanden"
    except ValueError as error:
        if str(error) == "analysis_deferred":
            raise
        detail = "Online-Datenbank derzeit nicht erreichbar; Audioanalyse bleibt nutzbar"
    except (OSError, TypeError, AttributeError, KeyError, json.JSONDecodeError):
        detail = "Online-Datenbank derzeit nicht erreichbar; Audioanalyse bleibt nutzbar"
    with db() as con:
        con.execute("INSERT OR REPLACE INTO skip_auto_online VALUES(?,?,?,?,?)",
                    (asset["asset_key"], asset["duration_ms"], json.dumps(segments), detail, int(time.time())))
    return segments


def protected(con, asset, kind):
    return bool(con.execute("""SELECT 1 FROM skip_records WHERE asset_key=? AND segment_type=?
      AND ABS(duration_ms-?)<=2000 AND (status IN ('approved','rejected') OR (status='pending' AND
        (source='device' OR EXISTS(SELECT 1 FROM skip_auto_evidence e WHERE e.record_id=skip_records.id AND e.human_review=1)))) LIMIT 1""",
      (asset["asset_key"], kind, asset["duration_ms"])).fetchone()
      or con.execute("SELECT 1 FROM skip_auto_blocks WHERE asset_key=? AND kind=? AND ABS(duration_ms-?)<=2000 LIMIT 1",
                     (asset["asset_key"], kind, asset["duration_ms"])).fetchone())


def pending_proposals(con, asset, kind):
    return con.execute("""SELECT r.* FROM skip_records r
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.asset_key=? AND r.source_key=? AND r.media_type=? AND r.season=? AND r.episode=?
      AND r.duration_ms=? AND r.segment_type=? AND r.status='pending' AND r.disabled=0
      AND r.source IN ('audio','chapter','theintrodb','audio_repetition')
      AND COALESCE(e.human_review,0)=0""",
      (*(asset[key] for key in ('asset_key','source_key','media_type','season','episode','duration_ms')), kind)).fetchall()


def proposal_rank(row):
    return (PROPOSAL_RANK[row['source']], row['confidence'], -row['id'])


def same_boundaries(first, second):
    return (abs(first['start_ms'] - second['start_ms']) <= BOUNDARY_TOLERANCE
            and abs(first['end_ms'] - second['end_ms']) <= BOUNDARY_TOLERANCE)


def retire_proposals(con, asset, kind, keep=None):
    """Archive generated alternatives after a decision, preserving human records."""
    con.execute("""UPDATE skip_records SET status='superseded' WHERE asset_key=? AND source_key=?
      AND media_type=? AND season=? AND episode=? AND ABS(duration_ms-?)<=2000 AND segment_type=?
      AND status='pending' AND source IN ('audio','chapter','theintrodb','audio_repetition')
      AND id<>? AND NOT EXISTS(SELECT 1 FROM skip_auto_evidence e WHERE e.record_id=skip_records.id AND e.human_review=1)""",
      (*(asset[key] for key in ('asset_key','source_key','media_type','season','episode','duration_ms')), kind, keep or -1))


def consolidate_proposals(con, asset, kind):
    """Collapse nearby machine proposals; retain materially conflicting boundaries."""
    keepers = []
    for row in sorted(pending_proposals(con, asset, kind), key=proposal_rank, reverse=True):
        if any(same_boundaries(row, kept) for kept in keepers):
            con.execute("UPDATE skip_records SET status='superseded' WHERE id=? AND status='pending'", (row['id'],))
        else:
            keepers.append(row)
    return keepers


def store_proposal(con, asset, kind, start, end, source, confidence=0, evidence=None):
    """Keep the strongest matching proposal, independent of the reference count."""
    asset = dict(asset)
    if protected(con, asset, kind):
        return None
    candidate = {'start_ms': start, 'end_ms': end}
    matches = [row for row in pending_proposals(con, asset, kind) if same_boundaries(row, candidate)]
    update_evidence = True
    if matches:
        saved = max(matches, key=proposal_rank)
        update_evidence = (PROPOSAL_RANK[source], confidence) >= proposal_rank(saved)[:2]
        if update_evidence:
            con.execute("UPDATE skip_records SET start_ms=?,end_ms=?,source=?,confidence=? WHERE id=? AND status='pending'",
                        (start, end, source, confidence, saved['id']))
    else:
        saved = add_record(con, dict(asset, imdb_id=asset.get('imdb_id',''), tmdb_id=asset.get('tmdb_id',0)),
                           kind, start, end, False, source=source, confidence=confidence)
        # A prior machine alternative may have been archived before a fresh retry.
        con.execute("""UPDATE skip_records SET status='pending',confidence=? WHERE id=? AND status IN ('pending','superseded')
          AND source IN ('audio','chapter','theintrodb','audio_repetition')
          AND NOT EXISTS(SELECT 1 FROM skip_auto_evidence e WHERE e.record_id=skip_records.id AND e.human_review=1)""",
          (confidence, saved['id']))
    if evidence and update_evidence:
        con.execute("""INSERT OR REPLACE INTO skip_auto_evidence SELECT ?,?,0 FROM skip_records
          WHERE id=? AND status='pending'""", (saved['id'], json.dumps(evidence), saved['id']))
    keepers = consolidate_proposals(con, asset, kind)
    return next((row for row in keepers if same_boundaries(row, candidate)), None)


def maintain_proposals(con):
    """One-time cleanup and fresh analysis of existing high-score proposals."""
    if con.execute("SELECT 1 FROM skip_auto_maintenance WHERE name=?", (POLICY_VERSION,)).fetchone():
        return
    groups = con.execute("""SELECT DISTINCT asset_key,source_key,media_type,season,episode,duration_ms,segment_type
      FROM skip_records WHERE status='pending' AND source IN ('audio','chapter','theintrodb','audio_repetition')""").fetchall()
    for row in groups:
        if protected(con, row, row['segment_type']):
            retire_proposals(con, row, row['segment_type'])
        else:
            consolidate_proposals(con, row, row['segment_type'])
    # Old scores alone are not enough: the normal worker verifies current files,
    # unique position and both boundaries before publishing. Keep the daily ledger.
    if con.execute('SELECT 1 FROM skip_auto_settings WHERE enabled=1 LIMIT 1').fetchone():
        con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,
          detail='Hohe Audiotreffer werden mit der neuen Freigaberegel erneut geprüft',updated_at=?
          WHERE status IN ('review','no_match','done') AND asset_key IN (
            SELECT a.asset_key FROM skip_assets a
            JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
            JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
            JOIN customer_playlists p ON p.id=a.playlist_id
            JOIN customers c ON c.id=p.customer_id AND c.enabled=1
            JOIN skip_records r ON r.asset_key=a.asset_key AND r.source_key=a.source_key
              AND r.season=a.season AND r.episode=a.episode AND ABS(r.duration_ms-a.duration_ms)<=2000
            WHERE a.media_type='episode' AND r.media_type=a.media_type
              AND r.status='pending' AND r.source='audio' AND r.confidence>=?)""", (now(), AUTO_CONFIDENCE))
    con.execute("INSERT INTO skip_auto_maintenance VALUES(?,?)", (POLICY_VERSION, now()))


def reference_rows(con, asset, kind):
    return con.execute("""SELECT r.*,a.playlist_id FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.source_key=? AND r.season=? AND r.segment_type=? AND r.status='approved' AND r.disabled=0
      AND ((e.record_id IS NULL AND r.source<>'auto_audio') OR e.human_review=1) AND r.asset_key<>?
      AND a.source_key=r.source_key AND a.season=r.season AND a.episode=r.episode AND a.media_type='episode'
      AND r.end_ms-r.start_ms BETWEEN 19000 AND 300000 AND ABS(a.duration_ms-r.duration_ms)<=2000
      ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 4""",
      (asset["source_key"], asset["season"], kind, asset["asset_key"])).fetchall()


def consensus(votes, online, duration, kind):
    """One reviewed reference suffices for a strong, unique full-boundary match."""
    good = [v for v in votes if v["confidence"] >= AUTO_CONFIDENCE and v.get('boundaries_confirmed') is True
            and valid_range(kind, v["start"], v["end"], duration)]
    if not good:
        return None
    # A disagreement between any strong references requires human inspection.
    if max(v["start"] for v in good) - min(v["start"] for v in good) > BOUNDARY_TOLERANCE or max(v["end"] for v in good) - min(v["end"] for v in good) > BOUNDARY_TOLERANCE:
        return None
    external = [x for x in online if x["kind"] == kind and x.get("identity_verified") is True
                and abs(x["start"] - good[0]["start"]) <= BOUNDARY_TOLERANCE
                and abs(x["end"] - good[0]["end"]) <= BOUNDARY_TOLERANCE]
    start = round(sum(v["start"] for v in good) / len(good))
    end = round(sum(v["end"] for v in good) / len(good))
    # Avoid projecting credit music over a possible post-credit scene.
    if kind == "outro" and duration - end > 1000:
        return None
    return dict(start=start, end=end, confidence=min(v["confidence"] for v in good), votes=good,
                online=external, policy=POLICY_VERSION)


def matching_boundaries(reference, target, step, offset):
    """Check both ends around the unique full match, allowing repeated short motifs."""
    cut = max(40, len(reference) // 3)
    radius = ceil(BOUNDARY_TOLERANCE / step)
    anchor = round(offset / step)
    for part, relative in ((reference[:cut], 0), (reference[-cut:], len(reference) - cut)):
        predicted = anchor + relative
        begin = max(0, predicted - radius)
        finish = min(len(target), predicted + radius + len(part))
        match = matching_offset(part, target[begin:finish], step)
        if not match or abs(begin * step + match[0] - offset - relative * step) > BOUNDARY_TOLERANCE:
            return False
    return True


def publish(con, asset, kind, evidence):
    if (not evidence or evidence.get('policy') != POLICY_VERSION
            or evidence['confidence'] < AUTO_CONFIDENCE or not evidence['votes']
            or not valid_range(kind, evidence['start'], evidence['end'], asset['duration_ms'])):
        return False
    if not enabled(con, asset["playlist_id"]) or protected(con, asset, kind):
        return False
    current = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (asset["asset_key"],)).fetchone()
    if (not current or any(current[key] != asset[key] for key in ("source_key", "media_type", "season", "episode", "playlist_id"))
            or abs(current["duration_ms"] - asset["duration_ms"]) > 2000):
        return False
    if evidence["online"]:
        cache = con.execute("SELECT segments_json,duration_ms FROM skip_auto_online WHERE asset_key=?", (asset["asset_key"],)).fetchone()
        if (not enabled(con, asset["playlist_id"], online=True) or not cache
                or cache["duration_ms"] != asset["duration_ms"]
                or any(x not in json.loads(cache["segments_json"]) for x in evidence["online"])):
            # Online corroboration is optional for a strong reviewed audio match.
            evidence = dict(evidence, online=[])
    for vote in evidence["votes"]:
        row = con.execute("""SELECT r.*,a.duration_ms asset_duration,a.source_key asset_source,a.season asset_season,
          a.episode asset_episode,s.enabled,c.enabled customer_enabled FROM skip_records r
          JOIN skip_assets a ON a.asset_key=r.asset_key JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id
          JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id
          LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
          WHERE r.id=? AND ((e.record_id IS NULL AND r.source<>'auto_audio') OR e.human_review=1)""", (vote["record_id"],)).fetchone()
        if (not row or row["status"] != "approved" or row["disabled"] or not row["enabled"] or not row["customer_enabled"]
                or row["source_key"] != asset["source_key"] or row["season"] != asset["season"] or row["segment_type"] != kind
                or row['asset_key'] != vote['asset_key'] or row['asset_key'] == asset['asset_key'] or row['episode'] != vote['episode']
                or vote.get('boundaries_confirmed') is not True or vote['confidence'] < AUTO_CONFIDENCE
                or row["asset_source"] != row["source_key"] or row["asset_season"] != row["season"] or row["asset_episode"] != row["episode"]
                or row["reviewed_at"] != vote["reviewed_at"]
                or row["start_ms"] != vote["ref_start"] or row["end_ms"] != vote["ref_end"]
                or abs(row["asset_duration"] - row["duration_ms"]) > 2000):
            return False
    # Same transaction as the checks: a concurrent correction cannot be overwritten.
    saved = add_record(con, dict(asset, imdb_id="", tmdb_id=0), kind, evidence["start"], evidence["end"], False,
                       source="auto_audio", confidence=evidence["confidence"])
    row = con.execute("SELECT status FROM skip_records WHERE id=?", (saved["id"],)).fetchone()
    if row[0] != "pending":
        return False
    con.execute("INSERT OR REPLACE INTO skip_auto_evidence VALUES(?,?,0)", (saved["id"], json.dumps(evidence)))
    con.execute("UPDATE skip_records SET status='approved',reviewed_at=? WHERE id=? AND status='pending'", (now(), saved["id"]))
    retire_proposals(con, asset, kind, saved['id'])
    return True


def common_span(a, b, step):
    """Find a unique contiguous high-information repetition in two bounded windows."""
    if not 160 <= min(len(a), len(b)) or max(len(a), len(b)) > 5000:
        return None
    index = defaultdict(list)
    for i, word in enumerate(b):
        for band in (0, 1):
            index[(band, (word >> (16 * band)) & 65535)].append(i)
    offsets = Counter()
    for i, word in enumerate(a):
        for band in (0, 1):
            positions = index[(band, (word >> (16 * band)) & 65535)]
            if len(positions) <= 24:
                for j in positions:
                    offsets[j - i] += 1
    spans = []
    chosen = []
    for offset, count in offsets.most_common(24):
        if count < 30 or any(abs(offset - previous) * step < 2000 for previous in chosen):
            continue
        chosen.append(offset)
        begin, finish = max(0, -offset), min(len(a), len(b) - offset)
        distances = [(a[i] ^ b[i + offset]).bit_count() / 32 for i in range(begin, finish)]
        run_start = None
        for k in range(len(distances) + 1):
            good = k < len(distances) and sum(distances[max(0, k - 3):k + 5]) / len(distances[max(0, k - 3):k + 5]) <= .075
            if good and run_start is None:
                run_start = k
            if not good and run_start is not None:
                length = k - run_start
                words = a[begin + run_start:begin + k]
                if 19_000 <= length * step <= 180_000 and len(set(words)) >= max(30, len(words) // 3):
                    score = 1 - sum(distances[run_start:k]) / length
                    spans.append((begin + run_start, begin + k, offset, score))
                run_start = None
    if not spans:
        return None
    spans.sort(key=lambda x: (-(x[1] - x[0]), -x[3]))
    best = spans[0]
    if any(abs(x[0] - best[0]) * step > 2000 and x[1] - x[0] >= (best[1] - best[0]) * .8 for x in spans[1:]):
        return None
    return best


def bootstrap(con, asset, kind):
    rows = con.execute("""SELECT w.*,a.episode FROM skip_auto_windows w JOIN skip_assets a ON a.asset_key=w.asset_key
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      WHERE a.source_key=? AND a.season=? AND w.kind=? AND w.asset_key<>?
      ORDER BY w.created_at DESC LIMIT 6""", (asset["source_key"], asset["season"], kind, asset["asset_key"])).fetchall()
    own = con.execute("SELECT * FROM skip_auto_windows WHERE asset_key=? AND kind=?", (asset["asset_key"], kind)).fetchone()
    if not own or protected(con, asset, kind):
        return False
    target = json.loads(own["words_json"])
    matches, used = [], {asset["episode"]}
    for row in rows:
        if row["episode"] in used or abs(row["step_ms"] - own["step_ms"]) > .001:
            continue
        span = common_span(target, json.loads(row["words_json"]), own["step_ms"])
        if span:
            matches.append((row, span)); used.add(row["episode"])
    if len(matches) < 2:
        return False
    spans = [x[1] for x in matches]
    if (max(x[0] for x in spans) - min(x[0] for x in spans)) * own["step_ms"] > 1000 or (max(x[1] for x in spans) - min(x[1] for x in spans)) * own["step_ms"] > 1000:
        return False
    start = own["offset_ms"] + round(sum(x[0] for x in spans) / len(spans) * own["step_ms"])
    end = own["offset_ms"] + round(sum(x[1] for x in spans) / len(spans) * own["step_ms"])
    duration = asset["duration_ms"]
    if (not valid_range(kind, start, end, duration)
            or (kind == "intro" and start > min(WINDOW_MS, duration * .4))
            or (kind == "outro" and (start < duration * .65 or end < duration - 15_000))):
        return False
    saved = store_proposal(con, asset, kind, start, end, 'audio_repetition', min(x[3] for x in spans),
                           {"method": "three_episode_repetition", "episodes": [asset["episode"]] + [x[0]["episode"] for x in matches]})
    return bool(saved)  # Repeated music alone cannot establish precise semantic boundaries.


def save_window(con, asset, kind, words, step, offset, length):
    con.execute("INSERT OR REPLACE INTO skip_auto_windows VALUES(?,?,?,?,?,?,?,?)",
                (asset["asset_key"], kind, json.dumps(words), step, offset, length, asset["duration_ms"], now()))
    # Bounded derived cache, never PCM or provider URLs.
    con.execute("DELETE FROM skip_auto_windows WHERE rowid NOT IN (SELECT rowid FROM skip_auto_windows ORDER BY created_at DESC LIMIT 256)")


def analyze(db, job, busy_factory):
    from skip_analysis_worker import store_fingerprint
    with db() as con:
        asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (job["asset_key"],)).fetchone()
        if not asset or not enabled(con, asset["playlist_id"]):
            return "disabled", "Automatik für diese Playlist ausgeschaltet"
        playlist = con.execute("SELECT * FROM customer_playlists WHERE id=?", (asset["playlist_id"],)).fetchone()
        discovered = bool(con.execute("SELECT 1 FROM skip_auto_assets WHERE asset_key=?", (asset["asset_key"],)).fetchone())
        refs = {kind: reference_rows(con, asset, kind) for kind in ("intro", "outro")}
        playlists = {r["playlist_id"]: con.execute("SELECT * FROM customer_playlists WHERE id=?", (r["playlist_id"],)).fetchone() for rows in refs.values() for r in rows}
    busy = busy_factory(db, [playlist] + list(playlists.values()))
    if busy():
        return "queued", "Wartet, bis die Wiedergabe beendet ist"
    asset = dict(asset)
    windows, proposals, approvals = {}, 0, 0
    with provider_proxy(source_url(playlist, asset), busy) as source:
        duration, chapters = probe(source, busy)
        if asset["duration_ms"] == 0 and discovered:
            with db() as con:
                con.execute("UPDATE skip_assets SET duration_ms=? WHERE asset_key=? AND duration_ms=0", (duration, asset["asset_key"]))
            asset["duration_ms"] = duration
        elif abs(duration - asset["duration_ms"]) > 2000:
            return "unmatched", "Videolaufzeit stimmt nicht mit der gemeldeten Folge überein"
        asset["duration_ms"] = duration
        with db() as con:
            for kind, start, end in chapter_candidates(chapters, duration):
                proposals += bool(store_proposal(con, asset, kind, start, end, 'chapter'))
    online = online_segments(db, asset, busy)
    with db() as con:
        for candidate in online:
            proposals += bool(store_proposal(con, asset, candidate['kind'], candidate['start'], candidate['end'],
                                             'theintrodb', evidence={'method':'online_suggestion'}))
    last_error = None
    if duration >= 19_000:
        for kind in ("intro", "outro"):
            with db() as con:
                if not enabled(con, asset["playlist_id"]):
                    return "disabled", "Automatik für diese Playlist ausgeschaltet"
                if protected(con, asset, kind):
                    continue
            offset = 0 if kind == "intro" else max(0, duration - WINDOW_MS)
            length = min(WINDOW_MS, duration)
            try:
                with provider_proxy(source_url(playlist, asset), busy) as source:
                    words, step, coverage = fingerprint(source, offset, length, busy, with_coverage=True)
                windows[kind] = (words, step, offset, coverage)
                with db() as con:
                    save_window(con, asset, kind, words, step, offset, round(coverage))
            except ValueError as error:
                if str(error) == "analysis_deferred":
                    raise
                last_error = error
            except OSError:
                last_error = ValueError("analysis_failed")
    for kind, (target, target_step, window_offset, coverage) in windows.items():
        votes = []
        for record in refs[kind]:
            with db() as con:
                reference_asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (record["asset_key"],)).fetchone()
            # Revalidate reference duration and complete audio, including old
            # caches produced before truncation checks were available.
            try:
                with provider_proxy(source_url(playlists[record["playlist_id"]], reference_asset), busy) as source:
                    measured, _ = probe(source, busy)
                    if abs(measured - record["duration_ms"]) > 2000:
                        continue
                    words, step = fingerprint(source, record["start_ms"] + 2000, record["end_ms"] - record["start_ms"] - 4000, busy, require_complete=True)
            except ValueError as error:
                if str(error) == "analysis_deferred":
                    raise
                last_error = error
                continue
            except OSError:
                last_error = ValueError("analysis_failed")
                continue
            with db() as con:
                store_fingerprint(con, record, words, step)
            match = matching_offset(words, target, step) if abs(step - target_step) <= .001 else None
            if not match:
                continue
            offset, confidence = match
            start = window_offset + offset - 2000
            end = start + record["end_ms"] - record["start_ms"]
            if -target_step / 2 <= start < 0:
                start = 0
            if duration < end <= duration + target_step / 2:
                end = duration
            if not valid_range(kind, start, end, duration) or end > window_offset + coverage + 250:
                continue
            # Confirm the first and last musical portions independently so a
            # coincidental central match cannot authorize a complete segment.
            boundaries = matching_boundaries(words, target, step, offset)
            vote = dict(start=start, end=end, confidence=confidence if boundaries else 0,
                        boundaries_confirmed=bool(boundaries),
                        asset_key=record["asset_key"], episode=record["episode"], record_id=record["id"],
                        reviewed_at=record["reviewed_at"], ref_start=record["start_ms"], ref_end=record["end_ms"])
            votes.append(vote)
            with db() as con:
                proposals += bool(store_proposal(con, asset, kind, start, end, 'audio', confidence,
                                                 {'method':'reviewed_audio_match','vote':vote}))
        decision = consensus(votes, online, duration, kind)
        with db() as con:
            if decision and publish(con, asset, kind, decision):
                approvals += 1
            elif not votes and bootstrap(con, asset, kind):
                proposals += 1
    if approvals:
        return "done", f"{approvals} Abschnitt(e) mit hohem, eindeutigem Audiotreffer automatisch freigegeben"
    if proposals:
        return "review", "Vorschläge vorhanden; Zeitgrenzen im Dashboard prüfen"
    if not windows and last_error:
        raise last_error
    return "no_match", "Noch keine ausreichend eindeutigen Abschnittszeiten erkannt"
