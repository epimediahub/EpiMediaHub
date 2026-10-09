"""Bounded season discovery and evidence-based publishing for the existing player.

External databases provide suggestions, never file identity. Human corrections
take precedence, and machine approvals cannot become independent human evidence.
"""
from __future__ import annotations

from math import ceil
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import re
import time
import unicodedata
import urllib.parse
import urllib.request
import urllib.error

from skip_analysis import (configured_source, source_url, provider_asset_key,
                           provider_proxy, probe, fingerprint, matching_offset,
                           chapter_candidates, provider_failure)
from skip_markers import add_record, now, valid_range
import numpy as np
from skip_detector_v2 import Config as LegacyDetectorConfig, IntroOutroDetectorV2, MarkerType as LegacyMarkerType
from skip_detector_v3 import (AUTO as DETECTOR_AUTO, Config as DetectorConfig,
                              FpWindow, PairCache, detect as detector_detect)

LEGACY_DETECTOR_POLICY = "chromaprint_v2_1"
DETECTOR_POLICY = "chromaprint_fft_v3_1"
DETECTOR_POLICIES = (LEGACY_DETECTOR_POLICY, DETECTOR_POLICY)

WINDOW_MS = 720_000
AUTO_CONFIDENCE = .92
BOUNDARY_TOLERANCE = 500
MAX_SEASON_EPISODES = 200
PROPOSAL_SOURCES = ('audio', 'chapter', 'theintrodb', 'audio_repetition', 'episcene')
PROPOSAL_RANK = {'audio': 4, 'chapter': 3, 'theintrodb': 2, 'audio_repetition': 1, 'episcene': 6}
POLICY_VERSION = 'high_audio_v2'
LEGACY_ONLINE_ERROR = 'Online-Datenbank derzeit nicht erreichbar; Audioanalyse bleibt nutzbar'
ONLINE_RECHECK_LIMIT = 96


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
      CREATE TABLE IF NOT EXISTS skip_auto_online_retry(
        asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        service TEXT NOT NULL,error_code TEXT NOT NULL,retry_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_online_cooldown(
        service TEXT PRIMARY KEY,error_code TEXT NOT NULL,retry_at INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_online_budget(day TEXT PRIMARY KEY,count INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS skip_auto_online_retry_due ON skip_auto_online_retry(retry_at,asset_key);
      CREATE TABLE IF NOT EXISTS skip_analysis_budget(day TEXT PRIMARY KEY,count INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_metadata_config(
        name TEXT PRIMARY KEY,value TEXT NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_auto_maintenance(
        name TEXT PRIMARY KEY,completed_at TEXT NOT NULL);
    """)
    from skip_catalogue import migrate as catalogue_migrate
    catalogue_migrate(con)
    from skip_scene import migrate as scene_migrate
    scene_migrate(con)
    maintain_proposals(con)
    from skip_release import migrate as release_migrate
    release_migrate(con)
    migrate_detector(con)
    # The old message discarded the actual cause. Recheck those entries using
    # metadata only; keep every marker, audio job and daily audio budget intact.
    con.execute("""INSERT OR IGNORE INTO skip_auto_online_retry
      SELECT asset_key,'','legacy_error',0 FROM skip_auto_online WHERE detail=?""", (LEGACY_ONLINE_ERROR,))
    con.execute("UPDATE skip_auto_online SET detail=? WHERE detail=?",
                ('Online-Abfrage wird erneut geprüft; Audioanalyse bleibt nutzbar', LEGACY_ONLINE_ERROR))


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
    """Fetch metadata on the catalogue host with the validated provider transport."""
    from skip_remote_client import local_execution
    if busy():
        raise ValueError("analysis_deferred")
    # Metadata stays on the Pi even when media decoding is remote. Scope this
    # override to the fetch so the following audio operation remains offloaded.
    with local_execution(), provider_proxy(url, busy) as local:
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


class OnlineFailure(ValueError):
    def __init__(self, service, code, retry_at=0):
        super().__init__(code)
        self.service, self.code, self.retry_at = service, code, retry_at


def online_failure_code(error):
    text = str(error)
    if re.fullmatch(r'provider_http_[1-5][0-9]{2}', text):
        return text
    if text in ('provider_dns', 'provider_tls', 'provider_timeout', 'provider_connection',
                'unsafe_source', 'redirect_limit', 'redirect_downgrade', 'metadata_limit'):
        return text
    if isinstance(error, urllib.error.HTTPError):
        return 'provider_http_' + str(error.code) if 100 <= error.code <= 599 else 'request_failed'
    if isinstance(error, (TimeoutError, urllib.error.URLError, OSError)):
        return provider_failure(error)
    return 'invalid_response'


def external_json(db, url, busy, service):
    """Apply service-wide pauses without exposing URLs, keys or response bodies."""
    if busy():
        raise ValueError('analysis_deferred')
    with db() as con:
        cooldown = con.execute('SELECT * FROM skip_auto_online_cooldown WHERE service=?', (service,)).fetchone()
    if cooldown and cooldown['retry_at'] > time.time():
        raise OnlineFailure(service, cooldown['error_code'], cooldown['retry_at'])
    try:
        body = fetch_json(url, busy)
        if not isinstance(body, dict):
            raise ValueError('invalid_response')
        return body
    except (ValueError, OSError) as error:
        if str(error) == 'analysis_deferred' or busy():
            raise ValueError('analysis_deferred') from None
        code = online_failure_code(error)
        status = int(code.removeprefix('provider_http_')) if code.startswith('provider_http_') else 0
        # A missing record or an invalid mapping is not a service outage.
        if status == 404 or 400 <= status < 500 and status not in (401, 403, 408, 429):
            raise OnlineFailure(service, code) from None
        delay = (getattr(error, 'retry_after', 0) or 3600) if status == 429 else (86400 if status in (401, 403) else 300)
        retry_at = int(time.time()) + max(30, min(int(delay), 86400))
        with db() as con:
            con.execute('INSERT OR REPLACE INTO skip_auto_online_cooldown VALUES(?,?,?)',
                        (service, code, retry_at))
        raise OnlineFailure(service, code, retry_at) from None


def online_failure_detail(error):
    service = 'TMDB' if error.service == 'tmdb' else 'Online-Zeitdatenbank'
    code = error.code
    if code == 'provider_http_404':
        detail = ('TMDB kennt diese Serien-/Folgenzuordnung nicht; Titel und Folgennummer prüfen'
                  if error.service == 'tmdb' else 'Keine Online-Zeitmarken für diese Folge vorhanden')
    elif code == 'provider_http_429':
        detail = service + ': Abfragelimit erreicht; erneuter Versuch nach der Wartezeit'
    elif code in ('provider_http_401', 'provider_http_403'):
        detail = ('TMDB-Schlüssel wird nicht akzeptiert (HTTP 401); Schlüssel prüfen'
                  if error.service == 'tmdb' and code == 'provider_http_401'
                  else f'{service} verweigert den Zugriff (HTTP {code[-3:]})')
    elif code in ('provider_http_400', 'provider_http_422'):
        detail = f'{service}: Abfrage abgewiesen (HTTP {code[-3:]}); Serien-/Folgenzuordnung prüfen'
    elif code.startswith('provider_http_'):
        detail = f'{service}: Server antwortet mit HTTP {code[-3:]}; erneuter Versuch folgt'
    else:
        reason = {'provider_dns': 'DNS-Fehler', 'provider_tls': 'TLS-Fehler',
                  'provider_timeout': 'Zeitüberschreitung', 'provider_connection': 'Verbindungsfehler',
                  'invalid_response': 'ungültige Antwort', 'metadata_limit': 'Antwort zu groß oder zu langsam',
                  'unsafe_source': 'Zieladresse nicht zulässig', 'redirect_limit': 'zu viele Weiterleitungen',
                  'redirect_downgrade': 'unsichere Weiterleitung'}.get(code, 'Abruf fehlgeschlagen')
        detail = f'{service}: {reason}; erneuter Versuch folgt'
    return detail + '; Audioanalyse bleibt nutzbar'


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


def discover_one(db, busy_factory, playlist_id=None):
    """Enumerate one previously watched season per idle tick, at most daily."""
    with db() as con:
        anchor = con.execute("""SELECT a.* FROM skip_assets a
          JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          LEFT JOIN skip_auto_assets d ON d.asset_key=a.asset_key
          LEFT JOIN skip_language_priority l ON l.asset_key=a.asset_key
          LEFT JOIN skip_auto_series z ON z.source_key=a.source_key AND z.playlist_id=a.playlist_id AND z.season=a.season
          WHERE a.media_type='episode' AND d.asset_key IS NULL
          AND (? IS NULL OR a.playlist_id=?)
          AND NOT EXISTS(SELECT 1 FROM skip_catalogue_settings cs WHERE cs.playlist_id=a.playlist_id AND cs.enabled=1)
          AND COALESCE(z.checked_at,0)<? ORDER BY COALESCE(l.priority,1),COALESCE(z.checked_at,0),a.updated_at DESC LIMIT 1""",
          (playlist_id, playlist_id, int(time.time()) - 86400)).fetchone()
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
        from skip_catalogue import language_priority, set_asset_language
        if entries:
            prior = con.execute('SELECT priority FROM skip_language_priority WHERE asset_key=?', (anchor['asset_key'],)).fetchone()
            metadata = info.get('info') if isinstance(info.get('info'), dict) else {}
            rank = language_priority(metadata, fallback=prior[0] if prior else language_priority({'name': anchor['title']}))
            set_asset_language(con, anchor['asset_key'], rank)
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
            set_asset_language(con, key, rank)
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
        return external_json(db, "https://api.themoviedb.org/3/" + path + "?" + urllib.parse.urlencode(dict(api_key=token, language="de-DE", **params)), busy, 'tmdb')
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
        retry = con.execute('SELECT retry_at FROM skip_auto_online_retry WHERE asset_key=?', (asset['asset_key'],)).fetchone()
        if cache and cache["duration_ms"] == asset["duration_ms"] and cache['detail'] != LEGACY_ONLINE_ERROR:
            fresh = retry['retry_at'] > time.time() if retry else cache['checked_at'] > time.time() - 86400
            if fresh:
                return json.loads(cache["segments_json"])
    segments, detail = [], "Keine eindeutige Titelkennung für die Online-Abfrage"
    failure = None
    try:
        ids = resolve_identity(db, asset, busy)
        if ids:
            query = {"tmdb_id": ids["tmdb_id"]} if ids.get("tmdb_id") else {"imdb_id": ids["imdb_id"]}
            query.update(season=asset["season"], episode=asset["episode"], duration_ms=asset["duration_ms"])
            body = external_json(db, "https://api.theintrodb.org/v3/media?" + urllib.parse.urlencode(query), busy, 'theintrodb')
            # Reject a conflicting canonical series ID instead of accepting a provider fallback.
            if not ids.get("tmdb_id") or body.get("tmdb_id") == ids["tmdb_id"]:
                segments = [x | {"identity_verified": ids["verified"]} for x in parse_online(body, asset["duration_ms"])]
            detail = "Online-Zeiten verfügbar" if segments else "Keine passenden Online-Zeiten vorhanden"
    except OnlineFailure as error:
        failure, detail = error, online_failure_detail(error)
    except ValueError as error:
        if str(error) == "analysis_deferred":
            raise
        failure = OnlineFailure('tmdb', online_failure_code(error), int(time.time()) + 3600)
        detail = online_failure_detail(failure)
    except (OSError, TypeError, AttributeError, KeyError, json.JSONDecodeError):
        failure = OnlineFailure('tmdb', 'invalid_response', int(time.time()) + 3600)
        detail = online_failure_detail(failure)
    with db() as con:
        if not enabled(con, asset['playlist_id'], online=True):
            return []
        con.execute("INSERT OR REPLACE INTO skip_auto_online VALUES(?,?,?,?,?)",
                    (asset["asset_key"], asset["duration_ms"], json.dumps(segments), detail, int(time.time())))
        con.execute('DELETE FROM skip_auto_online_retry WHERE asset_key=?', (asset['asset_key'],))
        if failure and failure.retry_at:
            con.execute('INSERT INTO skip_auto_online_retry VALUES(?,?,?,?)',
                        (asset['asset_key'], failure.service, failure.code, failure.retry_at))
    return segments


def refresh_online_one(db, busy_factory, playlist_id=None):
    """Retry one due metadata request per idle tick, without fetching any video."""
    stamp, day = int(time.time()), now()[:10]
    with db() as con:
        budget = con.execute('SELECT count FROM skip_auto_online_budget WHERE day=?', (day,)).fetchone()
        if budget and budget[0] >= ONLINE_RECHECK_LIMIT:
            return 'daily_limit'
        asset = con.execute("""SELECT a.* FROM skip_auto_online_retry r
          JOIN skip_assets a ON a.asset_key=r.asset_key
          JOIN skip_auto_settings s ON s.playlist_id=a.playlist_id AND s.enabled=1 AND s.online_enabled=1
          JOIN skip_analysis_sources x ON x.playlist_id=a.playlist_id AND x.enabled=1
          JOIN customer_playlists p ON p.id=a.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          JOIN skip_jobs j ON j.asset_key=a.asset_key AND j.status NOT IN ('queued','running','disabled')
          LEFT JOIN skip_auto_online_cooldown l ON l.service=r.service
          LEFT JOIN skip_language_priority lang ON lang.asset_key=a.asset_key
          WHERE r.retry_at<=? AND COALESCE(l.retry_at,0)<=? AND a.duration_ms>=5000
            AND (? IS NULL OR a.playlist_id=?)
          ORDER BY CASE WHEN a.media_type='episode' THEN COALESCE(lang.priority,1) ELSE 1 END,
          r.retry_at,a.asset_key LIMIT 1""", (stamp, stamp, playlist_id, playlist_id)).fetchone()
        if not asset:
            return 'idle'
        playlist = con.execute('SELECT * FROM customer_playlists WHERE id=?', (asset['playlist_id'],)).fetchone()
    busy = busy_factory(db, [playlist])
    if busy():
        return 'queued'
    try:
        candidates = online_segments(db, asset, busy)
    except ValueError as error:
        if str(error) == 'analysis_deferred':
            return 'queued'
        raise
    with db() as con:
        current = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (asset['asset_key'],)).fetchone()
        if current and dict(current) == dict(asset) and enabled(con, asset['playlist_id'], online=True):
            for candidate in candidates:
                store_proposal(con, asset, candidate['kind'], candidate['start'], candidate['end'],
                               'theintrodb', evidence={'method': 'online_suggestion'})
            from skip_release import accept_pending
            accept_pending(con, asset_key=asset['asset_key'])
        con.execute('INSERT INTO skip_auto_online_budget VALUES(?,1) ON CONFLICT(day) DO UPDATE SET count=count+1', (day,))
        con.execute('DELETE FROM skip_auto_online_budget WHERE day<?',
                    (time.strftime('%Y-%m-%d', time.gmtime(time.time() - 31 * 86400)),))
    return 'online_checked'


def protected(con, asset, kind, section=None):
    # Old coarse-grained manual exclusions stay authoritative. A separate,
    # approved intro is not grounds to suppress a nonoverlapping new intro.
    if con.execute(
        "SELECT 1 FROM skip_auto_blocks WHERE asset_key=? AND kind=? "
        "AND ABS(duration_ms-?)<=2000 LIMIT 1",
        (asset["asset_key"], kind, asset["duration_ms"])).fetchone():
        return True
    rows = con.execute("""SELECT * FROM skip_records WHERE asset_key=? AND segment_type=?
      AND ABS(duration_ms-?)<=2000 AND (status IN ('approved','rejected') OR
        (status='pending' AND (source='device' OR EXISTS(
          SELECT 1 FROM skip_auto_evidence e
          WHERE e.record_id=skip_records.id AND e.human_review=1))))""",
      (asset["asset_key"], kind, asset["duration_ms"])).fetchall()
    if section is None:
        return bool(rows)
    from skip_intro_sections import overlaps
    return any(r['disabled'] or overlaps(r, section) for r in rows)


def pending_proposals(con, asset, kind):
    return con.execute("""SELECT r.*,e.evidence_json FROM skip_records r
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.asset_key=? AND r.source_key=? AND r.media_type=? AND r.season=? AND r.episode=?
      AND r.duration_ms=? AND r.segment_type=? AND r.status='pending' AND r.disabled=0
      AND r.source IN ('audio','chapter','theintrodb','audio_repetition','episcene')
      AND COALESCE(e.human_review,0)=0""",
      (*(asset[key] for key in ('asset_key','source_key','media_type','season','episode','duration_ms')), kind)).fetchall()


def proposal_rank(row):
    rank = PROPOSAL_RANK.get(row['source'], 5 if row['source'] == 'auto_audio' else 0)
    try:
        evidence = json.loads(row['evidence_json'] or '{}')
        if isinstance(evidence, dict) and evidence.get('policy') in DETECTOR_POLICIES:
            rank = 5
    except (KeyError, IndexError, ValueError, TypeError):
        pass
    return (rank, row['confidence'], -row['id'])


def same_boundaries(first, second):
    return (abs(first['start_ms'] - second['start_ms']) <= BOUNDARY_TOLERANCE
            and abs(first['end_ms'] - second['end_ms']) <= BOUNDARY_TOLERANCE)


def retire_proposals(con, asset, kind, keep=None, section=None):
    """Retire only overlapping machine alternatives after a local decision."""
    sql = """UPDATE skip_records SET status='superseded' WHERE asset_key=? AND source_key=?
      AND media_type=? AND season=? AND episode=? AND ABS(duration_ms-?)<=2000 AND segment_type=?
      AND status='pending' AND source IN ('audio','chapter','theintrodb','audio_repetition','episcene')
      AND id<>? AND NOT EXISTS(SELECT 1 FROM skip_auto_evidence e WHERE e.record_id=skip_records.id AND e.human_review=1)"""
    args = [*(asset[key] for key in ('asset_key','source_key','media_type','season','episode','duration_ms')),
            kind, keep or -1]
    if section is not None:
        sql += ' AND start_ms<? AND end_ms>?'
        args.extend((section['end_ms'], section['start_ms']))
    con.execute(sql, args)


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
    if protected(con, asset, kind, {'start_ms': start, 'end_ms': end}):
        return None
    from skip_scene import enabled as scene_enabled
    if scene_enabled(con):
        evidence = dict(evidence or {}, episcene_required=True)
    candidate = {'start_ms': start, 'end_ms': end}
    matches = [row for row in pending_proposals(con, asset, kind) if same_boundaries(row, candidate)]
    update_evidence = True
    if matches:
        saved = max(matches, key=proposal_rank)
        update_evidence = proposal_rank(dict(source=source, confidence=confidence, id=0,
                                             evidence_json=json.dumps(evidence)))[:2] >= proposal_rank(saved)[:2]
        if source == 'episcene' and saved['source'] == 'episcene':
            update_evidence = True  # A fresh consensus can have more independent support.
        if update_evidence:
            con.execute("UPDATE skip_records SET start_ms=?,end_ms=?,source=?,confidence=? WHERE id=? AND status='pending'",
                        (start, end, source, confidence, saved['id']))
    else:
        saved = add_record(con, dict(asset, imdb_id=asset.get('imdb_id',''), tmdb_id=asset.get('tmdb_id',0)),
                           kind, start, end, False, source=source, confidence=confidence)
        # A prior machine alternative may have been archived before a fresh retry.
        con.execute("""UPDATE skip_records SET status='pending',confidence=? WHERE id=? AND status IN ('pending','superseded')
          AND source IN ('audio','chapter','theintrodb','audio_repetition','episcene')
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
        # An earlier accepted intro must not erase a different intro.
        decided = con.execute("""SELECT start_ms,end_ms FROM skip_records WHERE
          asset_key=? AND segment_type=? AND ABS(duration_ms-?)<=2000
          AND status IN ('approved','rejected')""",
          (row['asset_key'], row['segment_type'], row['duration_ms'])).fetchall()
        for decision in decided:
            retire_proposals(con, row, row['segment_type'], section=decision)
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
    from skip_release import enabled as release_enabled
    return con.execute("""SELECT r.*,a.playlist_id FROM skip_records r JOIN skip_assets a ON a.asset_key=r.asset_key
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.source_key=? AND r.season=? AND r.segment_type=? AND r.status='approved' AND r.disabled=0
      AND ((e.record_id IS NULL AND r.source<>'auto_audio') OR e.human_review=1
           OR (?=1 AND r.source IN ('chapter','theintrodb','audio_repetition')
               AND json_valid(e.evidence_json) AND json_extract(e.evidence_json,'$.automatic_acceptance')=1))
      AND r.asset_key<>?
      AND a.source_key=r.source_key AND a.season=r.season AND a.episode=r.episode AND a.media_type='episode'
      AND r.end_ms-r.start_ms BETWEEN 19000 AND 300000 AND ABS(a.duration_ms-r.duration_ms)<=2000
      ORDER BY COALESCE(e.human_review,0) DESC,r.reviewed_at DESC,r.id DESC LIMIT 4""",
      (asset["source_key"], asset["season"], kind, int(release_enabled(con, asset['playlist_id'])), asset["asset_key"])).fetchall()


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
    from skip_remote_client import configured, boundaries as remote_boundaries
    if configured():
        return remote_boundaries(reference, target, step, offset)
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
    from skip_scene import enabled as scene_enabled
    if scene_enabled(con):
        return False  # The image stage validates and publishes the combined result.
    if (not evidence or evidence.get('policy') != POLICY_VERSION
            or evidence['confidence'] < AUTO_CONFIDENCE or not evidence['votes']
            or not valid_range(kind, evidence['start'], evidence['end'], asset['duration_ms'])):
        return False
    if not enabled(con, asset["playlist_id"]) or protected(con, asset, kind, evidence):
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
    retire_proposals(con, asset, kind, saved['id'],
                     {'start_ms': evidence['start'], 'end_ms': evidence['end']})
    return True


def common_span(a, b, step):
    """Legacy compatibility helper; production uses the V3.1 FFT consensus."""
    if not 0 < step <= 1000:
        return None
    match = IntroOutroDetectorV2(LegacyDetectorConfig(item_duration_sec=step / 1000)).find_pair_candidate(
        a, b, LegacyMarkerType.INTRO)
    if match:
        return (round(match.segment.start * 1000 / step), round(match.segment.end * 1000 / step),
                -match.offset_frames, match.quality)
    return None


def migrate_detector(con):
    """Revisit missing intro/outro markers once with the V3.1 FFT detector."""
    if con.execute('SELECT 1 FROM skip_auto_maintenance WHERE name=?', (DETECTOR_POLICY,)).fetchone():
        return
    if not con.execute('SELECT 1 FROM skip_auto_settings WHERE enabled=1 LIMIT 1').fetchone():
        con.execute('INSERT INTO skip_auto_maintenance VALUES(?,?)', (DETECTOR_POLICY, now()))
        return
    con.execute("""UPDATE skip_jobs SET status='queued',attempts=0,
      detail='Intro/Outro wird mit dem V3.1-Staffelvergleich erneut geprüft',updated_at=?
      WHERE status IN ('no_reference','no_match','review','done') AND asset_key IN (
        SELECT a.asset_key FROM skip_assets a
        JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
        JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
        JOIN customer_playlists p ON p.id=a.playlist_id
        JOIN customers c ON c.id=p.customer_id AND c.enabled=1
        WHERE a.media_type='episode' AND (
          (NOT EXISTS (
            SELECT 1 FROM skip_records r WHERE r.asset_key=a.asset_key AND r.segment_type='intro'
            AND ABS(r.duration_ms-a.duration_ms)<=2000 AND (r.status IN ('approved','rejected')
            OR (r.status='pending' AND (r.source='device' OR EXISTS (
              SELECT 1 FROM skip_auto_evidence e WHERE e.record_id=r.id AND e.human_review=1)))))
           AND NOT EXISTS (SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=a.asset_key AND b.kind='intro'
             AND ABS(b.duration_ms-a.duration_ms)<=2000))
          OR
          (NOT EXISTS (
            SELECT 1 FROM skip_records r WHERE r.asset_key=a.asset_key AND r.segment_type='outro'
            AND ABS(r.duration_ms-a.duration_ms)<=2000 AND (r.status IN ('approved','rejected')
            OR (r.status='pending' AND (r.source='device' OR EXISTS (
              SELECT 1 FROM skip_auto_evidence e WHERE e.record_id=r.id AND e.human_review=1)))))
           AND NOT EXISTS (SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=a.asset_key AND b.kind='outro'
             AND ABS(b.duration_ms-a.duration_ms)<=2000))
        ))""", (now(),))
    con.execute('INSERT INTO skip_auto_maintenance VALUES(?,?)', (DETECTOR_POLICY, now()))

def detector_windows(con, asset, kind):
    rows = con.execute("""SELECT w.*,a.episode,a.source_key,a.season,a.playlist_id,'server' origin FROM skip_auto_windows w
      JOIN skip_assets a ON a.asset_key=w.asset_key
      JOIN skip_auto_settings x ON x.playlist_id=a.playlist_id AND x.enabled=1
      JOIN skip_analysis_sources s ON s.playlist_id=a.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=a.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE a.source_key=? AND a.season=? AND a.media_type='episode' AND w.kind=?
      AND ABS(w.duration_ms-a.duration_ms)<=2000 AND w.length_ms>=30000
      AND w.offset_ms>=0 AND w.offset_ms+w.length_ms<=a.duration_ms+250
      AND NOT EXISTS (SELECT 1 FROM skip_auto_blocks b WHERE b.asset_key=a.asset_key AND b.kind=w.kind
        AND ABS(b.duration_ms-a.duration_ms)<=2000)
      ORDER BY ABS(a.episode-?),w.created_at DESC,w.asset_key LIMIT 32""",
      (asset['source_key'], asset['season'], kind, asset['episode'])).fetchall()
    from skip_app_capture import windows as app_windows
    # Keep the longest contiguous section of a file. Repeated device uploads
    # and multiple audio tracks of one episode never count as extra partners.
    chosen = {r['asset_key']: r for r in rows}
    for row in app_windows(con, asset, kind):
        previous = chosen.get(row['asset_key'])
        if previous is None or row['length_ms'] > previous['length_ms']:
            chosen[row['asset_key']] = row
    return sorted(chosen.values(), key=lambda r: (abs(r['episode']-asset['episode']),r['asset_key']))[:32]


def _trusted_window(con, row, kind):
    """Only explicit human approval can lower the V3.1 auto-confirm partner count."""
    return bool(con.execute("""SELECT 1 FROM skip_records r
      LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.asset_key=? AND r.segment_type=? AND r.status='approved' AND r.disabled=0
      AND ABS(r.duration_ms-?)<=2000 AND (r.source='device' OR COALESCE(e.human_review,0)=1)
      LIMIT 1""", (row['asset_key'], kind, row['duration_ms'])).fetchone())


def _trusted_markers(con, row, kind):
    return [dict(r) for r in con.execute('''SELECT r.id,r.asset_key,r.start_ms,r.end_ms,r.reviewed_at
      FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id
      WHERE r.asset_key=? AND r.segment_type=? AND r.status='approved' AND r.disabled=0
      AND r.source_key=? AND r.season=? AND r.episode=? AND ABS(r.duration_ms-?)<=2000
      AND (r.source='device' OR COALESCE(e.human_review,0)=1)
      ORDER BY r.reviewed_at DESC,r.id DESC LIMIT 3''',
      (row['asset_key'], kind, row['source_key'], row['season'], row['episode'], row['duration_ms']))]


def bootstrap(con, asset, kind, busy=lambda: False):
    """Run V3.1 episode consensus entirely from the bounded cached windows."""
    if not enabled(con, asset['playlist_id']):
        return False
    current = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (asset['asset_key'],)).fetchone()
    if (not current or any(current[k] != asset[k] for k in ('source_key','season','episode','playlist_id'))
            or abs(current['duration_ms'] - asset['duration_ms']) > 2000):
        return False
    rows = detector_windows(con, asset, kind)
    own = next((r for r in rows if r['asset_key'] == asset['asset_key']), None)
    if not own or not 0 < own['step_ms'] <= 1000:
        return False

    selected, windows, used, trusted_markers = [], [], set(), []
    for row in [own] + [r for r in rows if r['asset_key'] != own['asset_key']]:
        if row['episode'] in used or abs(row['step_ms'] - own['step_ms']) > .001:
            continue
        try:
            words = json.loads(row['words_json'])
        except (ValueError, TypeError):
            continue
        if (not isinstance(words, list) or not 1 <= len(words) <= 10000
                or len(words) * row['step_ms'] > row['length_ms'] + 250
                or any(type(w) is not int or not -(1 << 31) <= w < (1 << 32) for w in words)):
            continue
        markers = _trusted_markers(con, row, kind) if row['asset_key'] != own['asset_key'] else []
        trusted = bool(markers)
        try:
            win = FpWindow(
                np.asarray(words, dtype=np.uint64),
                start_sec=row['offset_ms'] / 1000.0,
                item_sec=row['step_ms'] / 1000.0,
                episode_id=row['asset_key'],
                duration_sec=row['duration_ms'] / 1000.0,
                trusted=trusted,
                trusted_ranges=[(r['start_ms']/1000, r['end_ms']/1000) for r in markers],
            )
        except (ValueError, TypeError, OverflowError):
            continue
        selected.append(row)
        windows.append(win)
        trusted_markers.extend(markers)
        used.add(row['episode'])
        if len(selected) == 5:
            break

    if len(windows) < 3 or selected[0]['asset_key'] != own['asset_key']:
        return False
    if busy():
        raise ValueError('analysis_deferred')

    from skip_remote_client import configured, detect as remote_detect
    if configured():
        decision = remote_detect(windows[0], windows[1:], kind, DetectorConfig(), busy)
    else:
        decision = detector_detect(windows[0], windows[1:], kind, DetectorConfig(), PairCache())
    if not decision.found:
        return False

    start = round(decision.start_sec * 1000)
    end = round(decision.end_sec * 1000)
    duration = asset['duration_ms']
    if (not valid_range(kind, start, end, duration)
            or end > own['offset_ms'] + own['length_ms'] + 250
            or start < max(0, own['offset_ms'] - 250)
            or (kind == 'intro' and start > min(WINDOW_MS, duration * .4))
            or (kind == 'outro' and (start < duration * .65 or end < duration - 15000))):
        return False

    details = decision.details if isinstance(decision.details, dict) else {}
    evidence = dict(
        method='episode_consensus_v3',
        policy=DETECTOR_POLICY,
        status=decision.status,
        support=decision.partners_supporting,
        attempted_partners=decision.partners_used,
        mean_pair_quality=round(float(details.get('mean_quality', 0.0)), 6),
        boundary_spread_sec=round(float(details.get('spread_sec', 999.0)), 6),
        position_plausibility=round(float(details.get('position', 0.0)), 6),
        truncated=bool(details.get('truncated', False)),
        precision_policy='audio_consensus_precision_v1',
        ambiguous=bool(details.get('ambiguous', False)),
        boundaries_consistent=bool(details.get('boundaries_consistent', False)),
        episodes=[r['episode'] for r in selected],
        trusted_episodes=[r['episode'] for r in selected[1:]
                          if r['asset_key'] in details.get('trusted_episode_ids', [])],
        trusted_markers=[r for r in trusted_markers if r['asset_key'] in details.get('trusted_episode_ids', [])],
        windows=[dict(asset_key=r['asset_key'], episode=r['episode'], duration_ms=r['duration_ms'],
                      origin=r['origin'],
                      offset_ms=r['offset_ms'], length_ms=r['length_ms'], step_ms=r['step_ms'],
                      fingerprint_sha256=hashlib.sha256(r['words_json'].encode()).hexdigest())
                 for r in selected],
    )
    saved = store_proposal(con, asset, kind, start, end, 'audio_repetition', decision.confidence, evidence)
    if saved:
        # REVIEW remains pending. Only V3.1 AUTO_CONFIRMED evidence can pass
        # skip_release.detector_release_ready().
        retire_proposals(con, asset, kind, saved['id'], {'start_ms': start, 'end_ms': end})
    return bool(saved)

def refresh_neighbour_consensus(db, asset, kind, busy=lambda: False):
    """Use cached audio to update earlier episodes as independent partners arrive."""
    from skip_release import accept_pending
    with db() as con:
        keys = [r['asset_key'] for r in detector_windows(con, asset, kind)
                if r['asset_key'] != asset['asset_key']][:4]
    for key in keys:
        if busy():
            raise ValueError('analysis_deferred')
        with db() as con:
            neighbour = con.execute('SELECT * FROM skip_assets WHERE asset_key=?', (key,)).fetchone()
            if neighbour and bootstrap(con, neighbour, kind, busy) and accept_pending(con, asset_key=key):
                con.execute("""UPDATE skip_jobs SET status='done',detail=?,updated_at=?
                  WHERE asset_key=? AND status IN ('no_reference','no_match')""",
                  ('Abschnitt aus dem Staffelvergleich automatisch freigegeben; Zeiten später korrigierbar', now(), key))


def save_window(con, asset, kind, words, step, offset, length):
    con.execute("INSERT OR REPLACE INTO skip_auto_windows VALUES(?,?,?,?,?,?,?,?)",
                (asset["asset_key"], kind, json.dumps(words), step, offset, length, asset["duration_ms"], now()))
    # Bounded derived cache, never PCM or provider URLs.
    con.execute("DELETE FROM skip_auto_windows WHERE rowid NOT IN (SELECT rowid FROM skip_auto_windows ORDER BY created_at DESC LIMIT 256)")


def cached_window(con, asset, kind, offset, length):
    """Reuse a recent complete window only after the file runtime is rechecked."""
    from skip_app_capture import complete_window
    captured = complete_window(con, asset, kind, offset, length)
    if captured is not None:
        return captured
    row = con.execute("SELECT * FROM skip_auto_windows WHERE asset_key=? AND kind=?",
                      (asset['asset_key'], kind)).fetchone()
    if (not row or row['duration_ms'] != asset['duration_ms'] or row['offset_ms'] != offset
            or not length - 250 <= row['length_ms'] <= length + 250
            or not 0 < row['step_ms'] <= 1000):
        return None
    try:
        age = (datetime.now(timezone.utc) - datetime.fromisoformat(row['created_at'].replace('Z', '+00:00'))).total_seconds()
        words = json.loads(row['words_json'])
    except (ValueError, TypeError, AttributeError):
        return None
    if (not 0 <= age <= 3600 or not isinstance(words, list) or not 1 <= len(words) <= 10000
            or len(words) * row['step_ms'] > row['length_ms'] + 250
            or len(words) * row['step_ms'] < row['length_ms'] - 8000
            or any(type(w) is not int or not -(1 << 31) <= w < (1 << 32) for w in words)):
        return None
    return words, row['step_ms'], offset, row['length_ms']


@contextmanager
def analysis_phase(name):
    started=time.perf_counter()
    try:
        yield
    finally:
        if os.environ.get('SKIP_ANALYSIS_TIMING')=='1':
            print('skip_phase='+name+' elapsed_seconds='+str(round(time.perf_counter()-started,3)),flush=True)


def _analyze_window(db, asset, kind, window, refs, playlists, online, busy):
    from skip_analysis_worker import store_fingerprint, reusable_fingerprint
    duration = asset['duration_ms']
    target, target_step, window_offset, coverage = window
    proposals, approvals = 0, 0
    votes = []
    for record in refs[kind]:
        with db() as con:
            reference_asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (record["asset_key"],)).fetchone()
        # Reuse only a recently validated, complete fingerprint of this
        # exact reviewed marker. Older/unvalidated caches are read again.
        with db() as con:
            stored = con.execute('SELECT * FROM skip_fingerprints WHERE record_id=?', (record['id'],)).fetchone()
            checked = con.execute('SELECT * FROM skip_auto_reference_checks WHERE record_id=?', (record['id'],)).fetchone()
        reusable = (reference_asset and abs(reference_asset['duration_ms']-record['duration_ms'])<=2000
                    and reusable_fingerprint(stored, record) and checked
                    and checked['fingerprint_created_at']==stored['created_at']
                    and int(time.time())-checked['checked_at']<3600)
        try:
            if reusable:
                words, step = json.loads(stored['words_json']), stored['step_ms']
            else:
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
        if not reusable:
            with db() as con:
                store_fingerprint(con, record, words, step)
                con.execute('''INSERT OR REPLACE INTO skip_auto_reference_checks
                  SELECT record_id,created_at,? FROM skip_fingerprints WHERE record_id=?
                  AND words_json=? AND step_ms=?''', (int(time.time()), record['id'], json.dumps(words), step))
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
        elif bootstrap(con, asset, kind, busy):
            proposals += 1
    from skip_release import accept_pending
    with db() as con:
        approvals += accept_pending(con, asset_key=asset["asset_key"])
    refresh_neighbour_consensus(db, asset, kind, busy)
    from skip_scene import analyze as scene_analyze
    with db() as con:
        from skip_scene import enabled as scene_enabled
        use_scene = scene_enabled(con)
    if use_scene:
        with analysis_phase('episcene_'+kind):
            added, accepted = scene_analyze(db, asset, kind, refs[kind], busy)
        proposals += added
        approvals += accepted
    return proposals, approvals


def analyze(db, job, busy_factory):
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
        with analysis_phase("probe"):
            duration, chapters = probe(source, busy)
        if asset["duration_ms"] == 0 and discovered:
            with db() as con:
                con.execute("UPDATE skip_assets SET duration_ms=? WHERE asset_key=? AND duration_ms=0", (duration, asset["asset_key"]))
            asset["duration_ms"] = duration
        elif abs(duration - asset["duration_ms"]) > 2000:
            with db() as con:
                con.execute('DELETE FROM skip_scene_windows WHERE asset_key=?',(asset['asset_key'],))
            return "unmatched", "Videolaufzeit stimmt nicht mit der gemeldeten Folge überein"
        else:
            from skip_scene import enabled as scene_enabled
            with db() as con:
                if scene_enabled(con):
                    con.execute('UPDATE skip_assets SET duration_ms=? WHERE asset_key=? AND duration_ms=?',
                                (duration,asset['asset_key'],asset['duration_ms']))
        asset["duration_ms"] = duration
        with db() as con:
            for kind, start, end in chapter_candidates(chapters, duration):
                proposals += bool(store_proposal(con, asset, kind, start, end, 'chapter'))
    online = []  # Verified audio can publish before optional external metadata.
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
            with db() as con:
                cached = cached_window(con, asset, kind, offset, length)
            if cached is not None:
                windows[kind] = cached
            else:
                try:
                    with provider_proxy(source_url(playlist, asset), busy) as source:
                        with analysis_phase("fingerprint_"+kind):
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
            if kind in windows:
                with analysis_phase("comparison_"+kind):
                    added, accepted = _analyze_window(db, asset, kind, windows[kind], refs, playlists, online, busy)
                proposals += added
                approvals += accepted
            else:
                from skip_scene import analyze as scene_analyze, enabled as scene_enabled
                with db() as con:
                    use_scene = scene_enabled(con)
                if use_scene:
                    with analysis_phase('episcene_'+kind):
                        added, accepted = scene_analyze(db, asset, kind, refs[kind], busy)
                    proposals += added
                    approvals += accepted
    with analysis_phase("online_metadata"):
        online = online_segments(db, asset, busy)
    with db() as con:
        for candidate in online:
            proposals += bool(store_proposal(con, asset, candidate['kind'], candidate['start'], candidate['end'],
                                             'theintrodb', evidence={'method':'online_suggestion'}))
    with db() as con:
        from skip_release import accept_pending
        approvals += accept_pending(con, asset_key=asset['asset_key'])
    if approvals:
        return "done", f"{approvals} erkannte Abschnitt(e) automatisch freigegeben; Zeiten später korrigierbar"
    if proposals:
        return "review", "Vorschläge vorhanden; Zeitgrenzen im Dashboard prüfen"
    if not windows and last_error:
        from skip_scene import has_completed_visual
        with db() as con:
            if has_completed_visual(con,asset['asset_key']):
                return 'no_match','EpiScene: Bilder gespeichert; weitere unabhängige Folgen oder eine Referenz benötigt'
        raise last_error
    return "no_match", "Noch keine ausreichend eindeutigen Abschnittszeiten erkannt"
