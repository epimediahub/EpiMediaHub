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
      CREATE TABLE IF NOT EXISTS skip_catalogue_priority(
        asset_key TEXT PRIMARY KEY REFERENCES skip_assets(asset_key) ON DELETE CASCADE,
        priority INTEGER NOT NULL);
    """)


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


def listing(body):
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
                    release=first(row.get("releaseDate"), row.get("releasedate")))
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


def step(db, busy_factory, timestamp):
    from skip_automation import provider_api
    with db() as con:
        con.execute("""INSERT OR IGNORE INTO skip_catalogue_runs(playlist_id)
          SELECT playlist_id FROM skip_catalogue_settings WHERE enabled=1""")
        runs = con.execute("""SELECT r.* FROM skip_catalogue_runs r
          JOIN skip_catalogue_settings x ON x.playlist_id=r.playlist_id AND x.enabled=1
          JOIN skip_auto_settings a ON a.playlist_id=r.playlist_id AND a.enabled=1
          JOIN skip_analysis_sources s ON s.playlist_id=r.playlist_id AND s.enabled=1
          JOIN customer_playlists p ON p.id=r.playlist_id
          JOIN customers c ON c.id=p.customer_id AND c.enabled=1
          WHERE r.retry_at<=? AND (r.phase<>'idle' OR r.next_due<=?) ORDER BY r.last_touch,r.playlist_id""", (timestamp, timestamp)).fetchall()
    if not runs:
        return "idle"
    for run in runs:
        with db() as con:
            playlist = con.execute("SELECT * FROM customer_playlists WHERE id=?", (run["playlist_id"],)).fetchone()
        busy = busy_factory(db, [playlist])
        if busy():
            with db() as con:
                con.execute("UPDATE skip_catalogue_runs SET detail='Wartet, bis die Wiedergabe beendet ist',last_touch=? WHERE playlist_id=?", (time.time(), playlist["id"]))
            continue
        try:
            if run["phase"] == "idle":
                entries = listing(provider_api(playlist, "get_series", busy, _limit=24_000_000))
                with db() as con:
                    if not remember_listing(con, playlist, run, entries, timestamp):
                        return "disabled"
                    if not con.execute("SELECT 1 FROM skip_catalogue_series WHERE playlist_id=? AND pending_generation=?", (playlist["id"], run["generation"] + 1)).fetchone():
                        finish(con, playlist["id"], timestamp)
                return "listed"
            with db() as con:
                series = con.execute("SELECT * FROM skip_catalogue_series WHERE playlist_id=? AND pending_generation=? ORDER BY modified DESC,CAST(series_id AS INTEGER) LIMIT 1", (playlist["id"], run["generation"])).fetchone()
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
            if run["phase"] == "idle":
                con.execute("UPDATE skip_catalogue_runs SET retry_at=?,last_touch=?,detail=? WHERE playlist_id=?", (timestamp + 3600, time.time(), detail, playlist["id"]))
            else:
                con.execute("UPDATE skip_catalogue_series SET pending_generation=0,checked_at=?,status='failed',detail=? WHERE playlist_id=? AND series_id=?", (timestamp, detail, playlist["id"], series["series_id"]))
                con.execute("UPDATE skip_catalogue_runs SET checked=checked+1,last_touch=?,detail=? WHERE playlist_id=?", (time.time(), detail, playlist["id"]))
        return "failed"
    return "queued"


def advance(db, busy_factory, timestamp=None, max_steps=8):
    """Small serial metadata batch, never dependent on the daily audio budget."""
    timestamp = int(time.time()) if timestamp is None else timestamp
    deadline = time.monotonic() + 30
    outcome = "idle"
    for _ in range(max_steps):
        if time.monotonic() >= deadline:
            break
        result = step(db, busy_factory, timestamp)
        if result in ("idle", "queued", "disabled", "failed"):
            return result if outcome == "idle" else outcome
        outcome = result
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
