"""Durable full catalogue inventory, then bounded nightly incremental scans.

Catalogue metadata never approves a marker. Only new or changed provider files
enter the existing audio queue; identities, human decisions and credentials stay
under the same rules as player-registered episodes.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import re
import time
from zoneinfo import ZoneInfo

from skip_analysis import provider_asset_key, source_url
from skip_markers import now

ZONE = ZoneInfo("Europe/Berlin")
MAX_SERIES = 20_000
MAX_EPISODES = 10_000
DEFAULT_DAILY_LIMIT = 96
LANGUAGE_POLICY = "language_de_it_v1"
LANGUAGE_FIELDS = ("audio_language", "audio_languages", "language", "languages")
LANGUAGE_ALIASES = {
    "de": "de", "deu": "de", "ger": "de", "german": "de", "deutsch": "de",
    "deutsche": "de", "deutschen": "de",
    "it": "it", "ita": "it", "italian": "it", "italiano": "it", "italiana": "it",
    "italiane": "it", "italiani": "it", "italienisch": "it", "italienische": "it",
    "en": "en", "eng": "en", "english": "en", "englisch": "en",
    "fr": "fr", "fra": "fr", "fre": "fr", "french": "fr", "francais": "fr",
    "es": "es", "spa": "es", "spanish": "es", "espanol": "es",
    "tr": "tr", "tur": "tr", "turkish": "tr", "türkisch": "tr",
    "pt": "pt", "por": "pt", "ru": "ru", "rus": "ru", "ar": "ar", "ara": "ar",
    "us": "en", "uk": "en",
}
PREFERRED_LANGUAGES = {"de", "it"}
QUALITY_LABELS = {"hd", "fhd", "uhd", "4k", "sd"}


def language_codes(value, depth=0):
    """Read bounded, declared stream languages, never TMDB original_language."""
    if depth > 2:
        return set()
    if isinstance(value, str) and len(value) <= 128:
        codes = set()
        for part in re.split(r"[,;/+|]", value):
            token = part.strip().casefold()
            if re.fullmatch(r"[a-z]{2,3}[-_][a-z]{2}", token):
                token = re.split(r"[-_]", token)[0]
            if token in LANGUAGE_ALIASES:
                codes.add(LANGUAGE_ALIASES[token])
        return codes
    if isinstance(value, list) and len(value) <= 32:
        return set().union(*(language_codes(item, depth + 1) for item in value))
    if isinstance(value, dict):
        return set().union(*(language_codes(value.get(key), depth + 1)
                             for key in ("iso_639_1", "code", "language", "name")))
    return set()


def label_languages(value, category=False):
    """Only structured title tags; broader language labels in provider categories."""
    if not isinstance(value, str) or len(value) > 512:
        return set()
    codes, text = set(), value.strip()
    for _ in range(5):
        match = re.match(r"^(?:\[([^\]]+)\]|\(([^)]+)\)|([\w/+ ]{1,32})\s*[|:–-])\s*", text)
        if not match:
            break
        tag = next(part for part in match.groups() if part is not None).strip()
        found = language_codes(tag)
        if not found and tag.casefold() not in QUALITY_LABELS:
            break
        codes |= found
        text = text[match.end():]
    for _ in range(5):
        match = re.search(r"\s*[\[(]([^\])]+)[\])]\s*$", text)
        if not match:
            break
        tag = match[1].strip()
        found = language_codes(tag)
        if not found and tag.casefold() not in QUALITY_LABELS:
            break
        codes |= found
        text = text[:match.start()]
    if category:
        prefix = re.match(r"^(de|deu|ger|it|ita|en|eng|fr|fra|es|spa|tr|tur)(?=\s)", value.strip(), re.I)
        if prefix:
            codes |= language_codes(prefix[1])
        for token in re.findall(r"\w+(?:[-_]\w+)?", value):
            # Lowercase 'de' occurs in ordinary Spanish/French category phrases.
            if len(token) > 3 or token.isupper():
                codes |= language_codes(token)
        for token, code in {"deutschland": "de", "germany": "de", "italia": "it",
                            "italy": "it", "italien": "it"}.items():
            if re.search(rf"(?<!\w){token}(?!\w)", value, re.I):
                codes.add(code)
    return codes


def category_ids(row):
    from skip_automation import number
    values = row.get("category_ids", [])
    values = values if isinstance(values, list) and len(values) <= 32 else []
    return {str(n) for value in [row.get("category_id"), *values]
            if (n := number(value)) is not None}


def language_priority(row, categories=None, fallback=1):
    if not isinstance(row, dict):
        return fallback
    declared = set().union(*(language_codes(row.get(field)) for field in LANGUAGE_FIELDS))
    tagged = label_languages(row.get("name", ""))
    codes = declared or tagged
    if codes:
        return 0 if codes & PREFERRED_LANGUAGES else 1
    codes = label_languages(row.get("category_name", ""), category=True)
    if codes:
        return 0 if codes & PREFERRED_LANGUAGES else 1
    ranks = [(categories or {})[key] for key in category_ids(row) if key in (categories or {})]
    return min(ranks) if ranks else fallback


def category_priorities(body):
    from skip_automation import number
    if not isinstance(body, list) or len(body) > MAX_SERIES:
        raise ValueError("metadata_limit")
    result, ambiguous = {}, set()
    for row in body:
        if not isinstance(row, dict) or (identifier := number(row.get("category_id"))) is None:
            continue
        rank = language_priority({"category_name": row.get("category_name", "")})
        key = str(identifier)
        if key in result and result[key] != rank:
            ambiguous.add(key)
        result[key] = rank
    return {key: rank for key, rank in result.items() if key not in ambiguous}


def set_asset_language(con, asset_key, priority):
    con.execute("""INSERT INTO skip_language_priority VALUES(?,?)
      ON CONFLICT(asset_key) DO UPDATE SET priority=excluded.priority""", (asset_key, priority))


def set_series_language(con, playlist_id, series_id, priority):
    con.execute("""INSERT INTO skip_catalogue_languages VALUES(?,?,?)
      ON CONFLICT(playlist_id,series_id) DO UPDATE SET priority=excluded.priority""",
      (playlist_id, series_id, priority))
    con.execute("""INSERT INTO skip_language_priority SELECT asset_key,? FROM skip_catalogue_episodes
      WHERE playlist_id=? AND series_id=?
      ON CONFLICT(asset_key) DO UPDATE SET priority=excluded.priority""", (priority, playlist_id, series_id))


def preferred_inventory_pending(con, playlist_id=None):
    """Do not consume an older other-language job while known preferred files are being inventoried."""
    return bool(con.execute("""SELECT 1 FROM skip_catalogue_series z
      JOIN skip_catalogue_languages l ON l.playlist_id=z.playlist_id AND l.series_id=z.series_id AND l.priority=0
      JOIN skip_catalogue_runs r ON r.playlist_id=z.playlist_id AND r.generation=z.pending_generation
      JOIN skip_catalogue_settings x ON x.playlist_id=z.playlist_id AND x.enabled=1
      JOIN skip_auto_settings a ON a.playlist_id=z.playlist_id AND a.enabled=1
      JOIN skip_analysis_sources s ON s.playlist_id=z.playlist_id AND s.enabled=1
      JOIN customer_playlists p ON p.id=z.playlist_id
      JOIN customers c ON c.id=p.customer_id AND c.enabled=1
      WHERE z.pending_generation>0 AND r.phase<>'idle' AND r.retry_at<=?
        AND (? IS NULL OR z.playlist_id=?) LIMIT 1""",
      (int(time.time()), playlist_id, playlist_id)).fetchone())


def provider_listing(playlist, busy):
    from skip_automation import provider_api
    body = provider_api(playlist, "get_series", busy, _limit=24_000_000)
    entries = listing(body)  # Validate before the optional category request.
    if any(category_ids(row) for row in body if isinstance(row, dict)):
        categories = {}
        try:
            categories = category_priorities(provider_api(playlist, "get_series_categories", busy))
        except ValueError as error:
            if str(error) == "analysis_deferred":
                raise
        except (OSError, TypeError, KeyError, json.JSONDecodeError):
            pass  # Missing categories must not prevent normal inventory.
        entries = listing(body, categories)
    return entries


def language_refreshed(con, playlist_id, timestamp):
    con.execute("""INSERT INTO skip_catalogue_language_refresh VALUES(?,?,0)
      ON CONFLICT(playlist_id) DO UPDATE SET checked_at=excluded.checked_at,retry_at=0""",
      (playlist_id, timestamp))


def migrate(con):
    con.executescript("""
      CREATE TABLE IF NOT EXISTS skip_catalogue_settings(
        playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
        enabled INTEGER NOT NULL DEFAULT 0,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_catalogue_config(
        name TEXT PRIMARY KEY,value INTEGER NOT NULL,updated_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_catalogue_runs(
        playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
        full_done INTEGER NOT NULL DEFAULT 0,phase TEXT NOT NULL DEFAULT 'idle',
        generation INTEGER NOT NULL DEFAULT 0,started_at INTEGER NOT NULL DEFAULT 0,
        finished_at INTEGER NOT NULL DEFAULT 0,next_due INTEGER NOT NULL DEFAULT 0,
        retry_at INTEGER NOT NULL DEFAULT 0,last_touch REAL NOT NULL DEFAULT 0,
        total INTEGER NOT NULL DEFAULT 0,checked INTEGER NOT NULL DEFAULT 0,
        queued INTEGER NOT NULL DEFAULT 0,detail TEXT NOT NULL DEFAULT '');
      CREATE TABLE IF NOT EXISTS skip_catalogue_series(
        playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
        series_id TEXT NOT NULL,payload_json TEXT NOT NULL,signature TEXT NOT NULL,
        modified INTEGER NOT NULL DEFAULT 0,seen_generation INTEGER NOT NULL,
        pending_generation INTEGER NOT NULL DEFAULT 0,checked_at INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT '',detail TEXT NOT NULL DEFAULT '',
        PRIMARY KEY(playlist_id,series_id));
      CREATE TABLE IF NOT EXISTS skip_catalogue_episodes(
        playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
        series_id TEXT NOT NULL,asset_key TEXT NOT NULL REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        signature TEXT NOT NULL,seen_generation INTEGER NOT NULL,
        PRIMARY KEY(playlist_id,series_id,asset_key));
      CREATE INDEX IF NOT EXISTS idx_skip_catalogue_episode_asset
        ON skip_catalogue_episodes(asset_key,playlist_id,series_id);
      CREATE TABLE IF NOT EXISTS skip_catalogue_priority(
        asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        priority INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS skip_catalogue_languages(
        playlist_id INTEGER NOT NULL REFERENCES customer_playlists(id) ON DELETE CASCADE,
        series_id TEXT NOT NULL,priority INTEGER NOT NULL CHECK(priority IN (0,1)),
        PRIMARY KEY(playlist_id,series_id));
      CREATE TABLE IF NOT EXISTS skip_language_priority(
        asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        priority INTEGER NOT NULL CHECK(priority IN (0,1)));
      CREATE TABLE IF NOT EXISTS skip_catalogue_language_refresh(
        playlist_id INTEGER PRIMARY KEY REFERENCES customer_playlists(id) ON DELETE CASCADE,
        checked_at INTEGER NOT NULL DEFAULT 0,retry_at INTEGER NOT NULL DEFAULT 0);
    """)
    if not con.execute("SELECT 1 FROM skip_auto_maintenance WHERE name=?", (LANGUAGE_POLICY,)).fetchone():
        con.execute("""INSERT OR IGNORE INTO skip_catalogue_language_refresh
          SELECT DISTINCT playlist_id,0,0 FROM skip_catalogue_series""")
        # Reorder the existing backlog from retained provider names; never requeue
        # finished audio, reset quota, change file identity or touch reviewed markers.
        for row in con.execute("SELECT playlist_id,series_id,payload_json FROM skip_catalogue_series").fetchall():
            try:
                metadata = json.loads(row["payload_json"])
                rank = metadata.get("language_priority")
                rank = rank if type(rank) is int and rank in (0, 1) else language_priority(metadata)
            except (ValueError, TypeError, AttributeError):
                rank = 1
            set_series_language(con, row["playlist_id"], row["series_id"], rank)
        for row in con.execute("""SELECT a.asset_key,a.title FROM skip_assets a
          LEFT JOIN skip_language_priority l ON l.asset_key=a.asset_key
          WHERE a.media_type='episode' AND l.asset_key IS NULL""").fetchall():
            if label_languages(row["title"]) & PREFERRED_LANGUAGES:
                set_asset_language(con, row["asset_key"], 0)
        con.execute("INSERT INTO skip_auto_maintenance VALUES(?,?)", (LANGUAGE_POLICY, now()))
    from skip_schedule import migrate as schedule_migrate
    schedule_migrate(con)


def active(con, playlist_id):
    from skip_automation import enabled
    setting = con.execute("SELECT enabled FROM skip_catalogue_settings WHERE playlist_id=?", (playlist_id,)).fetchone()
    return bool(setting and setting[0] and enabled(con, playlist_id))


def daily_limit(con):
    # Existing installations retain their old budget until bulk mode is enabled.
    if not con.execute("SELECT 1 FROM skip_catalogue_settings WHERE enabled=1").fetchone():
        return 24
    row = con.execute("SELECT value FROM skip_catalogue_config WHERE name='daily_limit'").fetchone()
    return max(1, min(500, int(row[0]))) if row else DEFAULT_DAILY_LIMIT


def start(con, playlist_id, stamp=None):
    from skip_automation import enabled
    if not enabled(con, playlist_id):
        return False
    stamp = stamp or now()
    con.execute("INSERT INTO skip_catalogue_settings VALUES(?,1,?) ON CONFLICT(playlist_id) DO UPDATE SET enabled=1,updated_at=excluded.updated_at", (playlist_id, stamp))
    con.execute("INSERT OR IGNORE INTO skip_catalogue_runs(playlist_id) VALUES(?)", (playlist_id,))
    # Repeated clicks never reset a partially completed scan or completed jobs.
    con.execute("UPDATE skip_catalogue_runs SET next_due=0,retry_at=0 WHERE playlist_id=? AND phase='idle'", (playlist_id,))
    return True


def next_night(timestamp):
    current = datetime.fromtimestamp(timestamp, ZONE)
    target = current.replace(hour=3, minute=0, second=0, microsecond=0)
    if target <= current:
        target += timedelta(days=1)
    return int(target.timestamp())


def stamp_display(value):
    return datetime.fromtimestamp(value, ZONE).strftime("%d.%m. %H:%M") if value else "noch nicht"


def player_title(value):
    """Mirror V116Names.clean, preserving case and punctuation for series keys."""
    value = value.strip()
    languages = r"DE|GER|GERMAN|IT|ITA|EN|ENG|FR|TR|ES|US|UK"
    for _ in range(5):
        value = re.sub(rf"^\s*(?:[\[(](?:{languages}|HD|FHD|UHD|4K)[\])]|(?:{languages})\s*[|:–-])\s*", "", value, flags=re.I).strip()
        value = re.sub(r"\s*(?:[|:–-]\s*)?(?:[\[(])?(?:4K|UHD|FHD|FULL HD|HD|SD|HEVC|H265|H264|1080P|720P)(?:[\])])?\s*$", "", value, flags=re.I).strip()
    return re.sub(r"\s*[\[(](?:19|20)[0-9]{2}[\])]\s*$", "", value).strip()


def first(*values):
    return next((str(v).strip() for v in values if isinstance(v, (str, int)) and not isinstance(v, bool) and str(v).strip() not in ("", "null")), "")


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def listing(body, categories=None):
    from skip_automation import number
    if not isinstance(body, list) or len(body) > MAX_SERIES:
        raise ValueError("metadata_limit")
    result, ambiguous = {}, set()
    for row in body:
        if not isinstance(row, dict) or (identifier := number(row.get("series_id"))) is None:
            continue
        identifier = str(identifier)
        name = first(row.get("name"))
        if not name or len(name) > 512:
            continue
        # Whitelist scalar metadata; provider URLs/accounts/other fields are not stored.
        data = dict(series_id=identifier, name=name, year=first(row.get("year")),
                    release=first(row.get("releaseDate"), row.get("releasedate")),
                    language_priority=language_priority(row, categories))
        modified = number(row.get("last_modified"), high=9_999_999_999) or 0
        entry = (data, digest(data), modified)
        if identifier in result and result[identifier] != entry:
            ambiguous.add(identifier)
        result[identifier] = entry
    return [result[k] for k in sorted(result, key=lambda k: (-result[k][2], int(k))) if k not in ambiguous]


def episodes(body):
    from skip_automation import number, season_entries
    if not isinstance(body, dict) or not isinstance(body.get("episodes"), dict) or len(body["episodes"]) > 200:
        raise ValueError("catalogue_invalid")
    output, identifiers, seasons = [], set(), set()
    for raw_season in body["episodes"]:
        season = number(raw_season, low=0, high=1000)
        if season is None or season in seasons:
            raise ValueError("catalogue_invalid")
        seasons.add(season)
        rows = body["episodes"][raw_season]
        if rows == []:
            continue
        # Use canonical season keys, rejecting duplicate episode/file numbering.
        accepted = season_entries({"episodes": {str(season): rows}}, season)
        if not accepted:
            raise ValueError("catalogue_invalid")
        for item, raw in zip(accepted, rows):
            if item["stream_id"] in identifiers:
                raise ValueError("catalogue_invalid")
            identifiers.add(item["stream_id"])
            info = raw.get("info") if isinstance(raw.get("info"), dict) else {}
            identity = dict(item, season=season)
            # Only file/numbering/declared duration/version changes can requeue audio.
            version = dict(identity, added=first(raw.get("added")), modified=first(raw.get("last_modified")),
                           duration=first(info.get("duration_secs"), info.get("duration")),
                           video=first(info.get("video_codec")), audio=first(info.get("audio_codec")))
            output.append((identity, digest(version)))
            if len(output) > MAX_EPISODES:
                raise ValueError("metadata_limit")
    return sorted(output, key=lambda x: (x[0]["season"], x[0]["episode"]))


def remember_listing(con, playlist, run, entries, timestamp):
    if not active(con, playlist["id"]):
        return False
    generation = run["generation"] + 1
    phase = "nightly" if run["full_done"] else "full"
    pending = 0
    for data, signature, modified in entries:
        set_series_language(con, playlist["id"], data["series_id"], data["language_priority"])
        previous = con.execute("SELECT * FROM skip_catalogue_series WHERE playlist_id=? AND series_id=?", (playlist["id"], data["series_id"])).fetchone()
        # Reliable provider modification times make nightly checks inexpensive.
        # Missing timestamps are inspected every night; unchanged timestamps also
        # get a weekly control so a broken provider clock cannot hide updates forever.
        changed = (not previous or not run["full_done"] or previous["signature"] != signature
                   or previous["modified"] != modified or not modified
                   or previous["status"] != "ok" or previous["checked_at"] < timestamp - 7 * 86400)
        pending += int(changed)
        con.execute("""INSERT INTO skip_catalogue_series VALUES(?,?,?,?,?,?,?,?,?,?)
          ON CONFLICT(playlist_id,series_id) DO UPDATE SET payload_json=excluded.payload_json,
          signature=excluded.signature,modified=excluded.modified,seen_generation=excluded.seen_generation,
          pending_generation=excluded.pending_generation""",
          (playlist["id"], data["series_id"], json.dumps(data, ensure_ascii=False), signature, modified,
           generation, generation if changed else 0, previous["checked_at"] if previous else 0,
           previous["status"] if previous else "", previous["detail"] if previous else ""))
    # A removed series stops future scans; its reviewed markers remain intact.
    con.execute("UPDATE skip_catalogue_series SET pending_generation=0 WHERE playlist_id=? AND seen_generation<>?", (playlist["id"], generation))
    con.execute("""UPDATE skip_catalogue_runs SET phase=?,generation=?,started_at=?,retry_at=0,
      last_touch=?,total=?,checked=0,queued=0,detail=? WHERE playlist_id=?""",
      (phase, generation, timestamp, time.time(), pending,
       "Serienbestand wird aufgenommen" if phase == "full" else "Neue und geänderte Serien werden geprüft", playlist["id"]))
    return True


def register_episodes(con, playlist, series, body, entries, run):
    from skip_automation import series_key
    if not active(con, playlist["id"]):
        return 0
    metadata = json.loads(series["payload_json"])
    info = body.get("info") if isinstance(body.get("info"), dict) else {}
    rank = language_priority(info, fallback=metadata.get("language_priority", 1))
    set_series_language(con, playlist["id"], series["series_id"], rank)
    title = player_title(first(info.get("name"), metadata["name"]))
    release = first(info.get("releaseDate"), info.get("releasedate"), metadata["release"])
    raw_year = first(info.get("year"), release[:4], metadata["year"])
    year = raw_year[:4] if re.fullmatch(r"(?:19|20)\d{2}", raw_year[:4]) else ""
    if not title or len(title) > 180:
        raise ValueError("catalogue_invalid")
    base = dict(title=title, year=year, media_type="episode", duration_ms=0, playlist_id=playlist["id"])
    key = series_key(playlist, base, series["series_id"])
    queued = 0
    for item, signature in entries:
        data = base | item
        asset_key = provider_asset_key(source_url(playlist, data), "episode")
        previous = con.execute("SELECT * FROM skip_catalogue_episodes WHERE playlist_id=? AND series_id=? AND asset_key=?", (playlist["id"], series["series_id"], asset_key)).fetchone()
        asset = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (asset_key,)).fetchone()
        new = asset is None
        changed = bool(previous and previous["signature"] != signature)
        if new:
            con.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", (asset_key, key, playlist["id"], item["stream_id"], item["extension"], "episode", 0, item["season"], item["episode"], title, year, now()))
            con.execute("INSERT INTO skip_auto_assets VALUES(?,?)", (asset_key, now()))
        else:
            # Never relabel a file already identified by a player/another series.
            if (asset["media_type"] != "episode" or asset["season"] != item["season"] or asset["episode"] != item["episode"]
                    or asset["stream_id"] != item["stream_id"] or asset["extension"] != item["extension"]):
                continue
        con.execute("INSERT OR REPLACE INTO skip_catalogue_episodes VALUES(?,?,?,?,?)", (playlist["id"], series["series_id"], asset_key, signature, run["generation"]))
        set_asset_language(con, asset_key, rank)
        if new or changed:
            if changed:
                # Fresh provider probing may adopt a new runtime only for files
                # still carrying catalogue proof. Player-reported runtimes stay authoritative.
                con.execute("UPDATE skip_assets SET duration_ms=0 WHERE asset_key=? AND asset_key IN (SELECT asset_key FROM skip_auto_assets)", (asset_key,))
                con.execute("DELETE FROM skip_auto_windows WHERE asset_key=?", (asset_key,))
                con.execute("DELETE FROM skip_auto_online WHERE asset_key=?", (asset_key,))
            con.execute("""INSERT INTO skip_jobs(asset_key,status,created_at,updated_at) VALUES(?,'queued',?,?)
              ON CONFLICT(asset_key) DO UPDATE SET status='queued',attempts=0,detail='',updated_at=excluded.updated_at
              WHERE skip_jobs.status<>'running'""", (asset_key, now(), now()))
            priority = 0 if run["phase"] == "nightly" else 2
            con.execute("INSERT INTO skip_catalogue_priority VALUES(?,?) ON CONFLICT(asset_key) DO UPDATE SET priority=MIN(priority,excluded.priority)", (asset_key, priority))
            queued += 1
    return queued


def finish(con, playlist_id, timestamp):
    con.execute("""UPDATE skip_catalogue_runs SET full_done=1,phase='idle',finished_at=?,
      next_due=?,retry_at=0,last_touch=?,detail='Katalogabgleich abgeschlossen; Folgen werden in der Warteschlange geprüft'
      WHERE playlist_id=?""", (timestamp, next_night(timestamp), time.time(), playlist_id))


def step(db, busy_factory, timestamp, playlist_id=None):
    from skip_automation import provider_api
    with db() as con:
        con.execute("""INSERT OR IGNORE INTO skip_catalogue_runs(playlist_id)
          SELECT playlist_id FROM skip_catalogue_settings WHERE enabled=1""")
        runs = con.execute("""SELECT r.*,COALESCE(f.checked_at,1) language_checked,
          COALESCE(f.retry_at,0) language_retry FROM skip_catalogue_runs r
          JOIN skip_catalogue_settings x ON x.playlist_id=r.playlist_id AND x.enabled=1
          JOIN skip_auto_settings a ON a.playlist_id=r.playlist_id AND a.enabled=1
          JOIN skip_analysis_sources s ON s.playlist_id=r.playlist_id AND s.enabled=1
          JOIN customer_playlists p ON p.id=r.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          LEFT JOIN skip_catalogue_language_refresh f ON f.playlist_id=r.playlist_id
          WHERE (? IS NULL OR r.playlist_id=?) AND r.retry_at<=?
          AND (r.phase<>'idle' OR r.next_due<=? OR (f.checked_at=0 AND f.retry_at<=?))
          ORDER BY CASE WHEN r.phase='idle' OR (f.checked_at=0 AND f.retry_at<=?) THEN -1 ELSE COALESCE((
            SELECT MIN(COALESCE(l.priority,1)) FROM skip_catalogue_series z
            LEFT JOIN skip_catalogue_languages l ON l.playlist_id=z.playlist_id AND l.series_id=z.series_id
            WHERE z.playlist_id=r.playlist_id AND z.pending_generation=r.generation),1) END,
          r.last_touch,r.playlist_id""", (playlist_id, playlist_id, timestamp, timestamp, timestamp, timestamp)).fetchall()
    if not runs:
        return "idle"
    for run in runs:
        with db() as con:
            playlist = con.execute("SELECT * FROM customer_playlists WHERE id=?", (run["playlist_id"],)).fetchone()
        busy = busy_factory(db, [playlist])
        refreshing = (run['language_checked'] == 0 and run['language_retry'] <= timestamp
                      and (run['phase'] != 'idle' or run['next_due'] > timestamp))
        if busy():
            with db() as con:
                con.execute("UPDATE skip_catalogue_runs SET detail='Wartet, bis die Wiedergabe beendet ist',last_touch=? WHERE playlist_id=?", (time.time(), playlist["id"]))
            continue
        try:
            if refreshing:
                entries = provider_listing(playlist, busy)
                with db() as con:
                    if not active(con, playlist['id']):
                        return 'disabled'
                    for metadata, _, _ in entries:
                        saved = con.execute('SELECT payload_json FROM skip_catalogue_series WHERE playlist_id=? AND series_id=?',
                                            (playlist['id'], metadata['series_id'])).fetchone()
                        if not saved:
                            continue
                        payload = json.loads(saved[0])
                        payload['language_priority'] = metadata['language_priority']
                        con.execute('UPDATE skip_catalogue_series SET payload_json=? WHERE playlist_id=? AND series_id=?',
                                    (json.dumps(payload, ensure_ascii=False), playlist['id'], metadata['series_id']))
                        set_series_language(con, playlist['id'], metadata['series_id'], metadata['language_priority'])
                    language_refreshed(con, playlist['id'], timestamp)
                return 'language_refreshed'
            if run["phase"] == "idle":
                entries = provider_listing(playlist, busy)
                with db() as con:
                    if not remember_listing(con, playlist, run, entries, timestamp):
                        return "disabled"
                    language_refreshed(con, playlist['id'], timestamp)
                    if not con.execute("SELECT 1 FROM skip_catalogue_series WHERE playlist_id=? AND pending_generation=?", (playlist["id"], run["generation"] + 1)).fetchone():
                        finish(con, playlist["id"], timestamp)
                return "listed"
            with db() as con:
                series = con.execute("""SELECT s.* FROM skip_catalogue_series s
                  LEFT JOIN skip_catalogue_languages l ON l.playlist_id=s.playlist_id AND l.series_id=s.series_id
                  WHERE s.playlist_id=? AND s.pending_generation=?
                  ORDER BY COALESCE(l.priority,1),s.modified DESC,CAST(s.series_id AS INTEGER) LIMIT 1""",
                  (playlist["id"], run["generation"])).fetchone()
            if series is None:
                with db() as con:
                    if active(con, playlist["id"]):
                        finish(con, playlist["id"], timestamp)
                return "finished"
            body = provider_api(playlist, "get_series_info", busy, series_id=series["series_id"])
            entries = episodes(body)
            with db() as con:
                if not active(con, playlist["id"]):
                    return "disabled"
                # A user can restart/disable while metadata is fetched. Do not
                # attach work to a changed generation.
                current = con.execute("SELECT * FROM skip_catalogue_runs WHERE playlist_id=?", (playlist["id"],)).fetchone()
                if current["generation"] != run["generation"]:
                    return "queued"
                queued = register_episodes(con, playlist, series, body, entries, run)
                con.execute("UPDATE skip_catalogue_series SET pending_generation=0,checked_at=?,status='ok',detail='' WHERE playlist_id=? AND series_id=?", (timestamp, playlist["id"], series["series_id"]))
                con.execute("UPDATE skip_catalogue_runs SET checked=checked+1,queued=queued+?,last_touch=?,detail='Serien erfasst; neue oder geänderte Folgen eingeplant' WHERE playlist_id=?", (queued, time.time(), playlist["id"]))
            return "discovered"
        except ValueError as error:
            if str(error) == "analysis_deferred":
                return "queued"
        except (OSError, TypeError, KeyError, json.JSONDecodeError):
            pass
        # Do not log exception strings: upstream messages may contain account URLs.
        with db() as con:
            if not active(con, playlist["id"]):
                return "disabled"
            detail = "Anbieterkatalog derzeit nicht auswertbar; gespeicherte Zeitmarken bleiben nutzbar"
            if refreshing:
                con.execute('UPDATE skip_catalogue_language_refresh SET retry_at=? WHERE playlist_id=?',
                            (timestamp + 3600, playlist['id']))
            elif run["phase"] == "idle":
                con.execute("UPDATE skip_catalogue_runs SET retry_at=?,last_touch=?,detail=? WHERE playlist_id=?", (timestamp + 3600, time.time(), detail, playlist["id"]))
            else:
                con.execute("UPDATE skip_catalogue_series SET pending_generation=0,checked_at=?,status='failed',detail=? WHERE playlist_id=? AND series_id=?", (timestamp, detail, playlist["id"], series["series_id"]))
                con.execute("UPDATE skip_catalogue_runs SET checked=checked+1,last_touch=?,detail=? WHERE playlist_id=?", (time.time(), detail, playlist["id"]))
        return "failed"
    return "queued"


def advance(db, busy_factory, timestamp=None, max_steps=8, playlist_id=None, stop_when_ready=False):
    """Small serial metadata batch, never dependent on the daily audio budget."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    deadline = time.monotonic() + 30
    outcome = "idle"
    for _ in range(max_steps):
        if time.monotonic() >= deadline:
            break
        result = step(db, busy_factory, timestamp, playlist_id)
        if result in ("idle", "queued", "disabled", "failed"):
            return result if outcome == "idle" else outcome
        outcome = result
        if stop_when_ready and playlist_id is not None:
            from skip_schedule import ready
            with db() as con:
                if ready(con, playlist_id):
                    break
    return outcome


def dashboard(con):
    rows = con.execute("""SELECT p.id,p.name,c.name customer_name,x.enabled,
      COALESCE(r.phase,'idle') phase,COALESCE(r.full_done,0) full_done,
      COALESCE(r.checked,0) checked,COALESCE(r.total,0) total,COALESCE(r.queued,0) queued,
      COALESCE(r.next_due,0) next_due,COALESCE(r.started_at,0) started_at,COALESCE(r.detail,'') detail
      FROM skip_catalogue_settings x JOIN customer_playlists p ON p.id=x.playlist_id
      JOIN customers c ON c.id=p.customer_id LEFT JOIN skip_catalogue_runs r ON r.playlist_id=p.id
      ORDER BY c.name,p.name""").fetchall()
    result = []
    for row in rows:
        failed = con.execute("SELECT COUNT(*) FROM skip_catalogue_series WHERE playlist_id=? AND status='failed' AND seen_generation=(SELECT generation FROM skip_catalogue_runs WHERE playlist_id=?)", (row["id"], row["id"])).fetchone()[0]
        counts = con.execute("""SELECT COUNT(DISTINCT e.asset_key) total,
          COUNT(DISTINCT CASE WHEN j.status IN ('queued','running') THEN e.asset_key END) waiting,
          COUNT(DISTINCT CASE WHEN j.status NOT IN ('queued','running','disabled') THEN e.asset_key END) checked
          FROM skip_catalogue_episodes e LEFT JOIN skip_jobs j ON j.asset_key=e.asset_key WHERE e.playlist_id=?""", (row["id"],)).fetchone()
        result.append(dict(row) | dict(episodes=counts["total"], waiting=counts["waiting"], analyzed=counts["checked"], failed_series=failed,
                                      next_text=stamp_display(row["next_due"]), last_text=stamp_display(row["started_at"]),
                                      active=active(con, row["id"])))
    return result
