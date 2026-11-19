#!/usr/bin/env python3
"""Complete local series IDs and run the official IntroDB catalogue through EpiScene."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import stat
import time
import unicodedata
from collections import Counter, defaultdict
from contextlib import closing, contextmanager, nullcontext
from datetime import datetime, timezone
from itertools import zip_longest
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from analysis_identity import _asset_identity, _clean_id, _columns, _source_list
from bridge import Episode, KINDS, parse_introdb
from runtime_integration import _cache_path
from trusted_external import SCHEMA, _key, _promote
from trusted_external_sync import CACHE, PRODUCTION

PLAYLISTS = {8: "4K ANALYSE", 10: "THE BEST"}
SNAPSHOT = Path("/var/lib/episcene-learning/introdb-open-catalogue.sqlite3")
RUNTIME_REPORT_FORMAT = "episcene_introdb_missing_runtimes_v1"
MEASUREMENT_SECONDS = 480
IDS = ("imdb_id", "tmdb_id", "tvdb_id")
PUBLIC_QUERY = "SELECT DISTINCT ?tmdb ?imdb WHERE { ?s wdt:P4983 ?tmdb; wdt:P345 ?imdb . }"
WIKIDATA = "https://query.wikidata.org/sparql?" + urlencode({"query": PUBLIC_QUERY})
TVMAZE = "https://api.tvmaze.com/shows?page="
RAW_ROOT = "https://raw.githubusercontent.com/epimediahub/EpiMediaHub/"
HELPERS = (
    ("stage_introdb_catalogue", "1c37221a9f1c80c93d9552eddbe9e2b47a9d07c2",
     "3c4d5cd8c6e49308b258b0d2f4ae83222820754f21d1e78e215d87abc4415626"),
    ("check_introdb_catalogue_release", "38c7bed41d88d9677f5f949fbb85e196430ed5e6",
     "16a4f3bde35d2072bb7d65cd923cc2b817fd6d7e5aa3a3d57fa9e52ed8bcede8"),
)


def fetch(url, accept):
    limit = 16 * 1024 * 1024
    headers = {"Accept": accept, "Accept-Encoding": "gzip",
               "User-Agent": "EpiMediaHub-Catalogue/1.0 (https://github.com/epimediahub/EpiMediaHub)"}
    for attempt in range(3):
        try:
            with urlopen(Request(url, headers=headers), timeout=20) as response:
                stream = gzip.GzipFile(fileobj=response) if response.headers.get("Content-Encoding") == "gzip" else response
                result = stream.read(limit + 1)
                if len(result) > limit:
                    raise ValueError("Antwort überschreitet das Größenlimit")
                return result
        except HTTPError as error:
            if error.code not in (408, 429, 502, 503, 504) or attempt == 2:
                raise
            retry_after = error.headers.get("Retry-After", "5")
            if not retry_after.isdecimal() or int(retry_after) > 30:
                raise
            time.sleep(max(1, int(retry_after)))


def load_helpers(directory):
    modules = []
    for name, commit, digest in HELPERS:
        url = RAW_ROOT + commit + "/tools/episcene-learning-v1/unified-marker-bridge/" + name + ".py"
        data = fetch(url, "text/plain")
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("Prüfsumme für ein EpiScene-Modul stimmt nicht")
        path = directory / (name + ".py")
        path.write_bytes(data)
        spec = importlib.util.spec_from_file_location(name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        modules.append(module)
    return modules


def title_year(title, year):
    if not isinstance(title, str):
        return None
    title = unicodedata.normalize("NFKC", title).casefold()
    year = str(year or "").strip()
    suffix = re.search(r"\s*(?:\(((?:19|20)\d{2})\)|\[((?:19|20)\d{2})\])\s*$", title)
    if suffix:
        embedded = suffix.group(1) or suffix.group(2)
        if year and year != embedded:
            return None
        year = embedded
        title = title[:suffix.start()]
    title = " ".join(re.findall(r"[^\W_]+", title))
    return (title, int(year)) if title and re.fullmatch(r"(?:19|20)\d{2}", year) else None


def wikidata_ids():
    by_tmdb, by_imdb = defaultdict(set), defaultdict(set)
    rows = csv.DictReader(io.StringIO(fetch(WIKIDATA, "text/csv").decode("utf-8-sig")))
    if not {"tmdb", "imdb"} <= set(rows.fieldnames or ()):
        raise ValueError("Wikidata-Zuordnung hat ein anderes Format")
    for row in rows:
        tmdb, imdb = _clean_id("tmdb_id", row["tmdb"]), _clean_id("imdb_id", row["imdb"])
        if imdb and tmdb:
            by_tmdb[tmdb].add(imdb)
            by_imdb[imdb].add(tmdb)
    if not by_tmdb:
        raise ValueError("Wikidata-Zuordnung ist leer")
    print(f"Wikidata | {len(by_tmdb)} öffentliche TMDB-Serien-IDs", flush=True)
    return by_tmdb, by_imdb


def tvmaze_index():
    by_title, by_tvdb = defaultdict(set), defaultdict(set)
    page = 0
    while True:
        try:
            rows = json.loads(fetch(TVMAZE + str(page), "application/json"))
        except HTTPError as error:
            if error.code == 404 and page:
                break
            raise
        if not isinstance(rows, list) or len(rows) > 250:
            raise ValueError("TVmaze-Index hat ein anderes Format")
        for row in rows:
            show_id = row["id"]
            if type(show_id) is not int or show_id // 250 != page:
                raise ValueError("TVmaze-Index hat eine unerwartete Seitennummer")
            external = row["externals"]
            imdb = _clean_id("imdb_id", external.get("imdb"))
            tvdb = _clean_id("tvdb_id", external.get("thetvdb"))
            premiere = title_year(row.get("name"), str(row.get("premiered") or "")[:4])
            if premiere:
                by_title[premiere].add((show_id, imdb, tvdb))
            if tvdb and imdb:
                by_tvdb[tvdb].add(imdb)
        page += 1
        if page % 50 == 0:
            print(f"TVmaze-Serienindex | {page} Seiten geladen", flush=True)
        time.sleep(.6)
    print("Seriendaten: TVmaze, CC BY-SA, https://www.tvmaze.com/api", flush=True)
    return by_title, by_tvdb


def connect(path, mode):
    db = sqlite3.connect(path.resolve().as_uri() + "?mode=" + mode, uri=True, timeout=12)
    db.row_factory = sqlite3.Row
    if mode == "ro":
        db.execute("PRAGMA query_only=ON")
    return db


def catalogue_groups(path):
    groups = {}
    with closing(connect(path, "ro")) as db:
        columns = _columns(db, "skip_assets")
        if not {"source_key", "asset_key", "playlist_id", "media_type", "title",
                "year", "season", "episode", "duration_ms"} <= columns:
            raise ValueError("Die EpiScene-Serienmetadaten haben ein anderes Schema")
        sources = _source_list(db, columns)
        shared = {row[0] for row in db.execute("""
            SELECT DISTINCT source_key FROM skip_assets
            WHERE playlist_id NOT IN (8,10) OR media_type <> 'episode'
        """)}
        for asset in db.execute("""
            SELECT * FROM skip_assets WHERE media_type='episode' AND playlist_id IN (8,10)
        """):
            source_key = asset["source_key"]
            group = groups.setdefault(source_key, {
                "ids": {field: set() for field in IDS}, "titles": set(), "missing": Counter(),
                "ambiguous": not source_key or source_key in shared,
            })
            group.setdefault("asset", dict(asset))
            title = title_year(asset["title"], asset["year"])
            if title:
                group["titles"].add(title)
            identity, status = _asset_identity(db, asset, sources)
            group["ambiguous"] |= status == "conflicting_ids"
            if not identity or not identity["imdb_id"]:
                group["missing"][asset["playlist_id"]] += 1
            if identity:
                for field in IDS:
                    if identity[field]:
                        group["ids"][field].add(identity[field])
    return groups


def local_index(groups):
    references = defaultdict(set)
    for group in groups.values():
        ids = group["ids"]
        if group["ambiguous"] or any(len(ids[field]) > 1 for field in IDS):
            continue
        for field in ("tmdb_id", "tvdb_id"):
            for reference in ids[field]:
                references[field, reference].update(ids["imdb_id"])
    return references


def match_group(group, local, wd_tmdb, wd_imdb, maze_title, maze_tvdb):
    ids = group["ids"]
    if group["ambiguous"] or any(len(ids[field]) > 1 for field in IDS):
        return None
    tmdb = next(iter(ids["tmdb_id"]), 0)
    tvdb = next(iter(ids["tvdb_id"]), 0)
    choices = (ids["imdb_id"] | local.get(("tmdb_id", tmdb), set())
               | local.get(("tvdb_id", tvdb), set()) | wd_tmdb.get(tmdb, set())
               | maze_tvdb.get(tvdb, set()))
    method = "catalogue_external_id"
    if not choices and len(group["titles"]) == 1:
        titles = maze_title.get(next(iter(group["titles"])), set())
        if len(titles) == 1:
            _, imdb, external_tvdb = next(iter(titles))
            tmdb_options = wd_imdb.get(imdb, set())
            if (imdb and (not tvdb or external_tvdb == tvdb)
                    and (not tmdb or not tmdb_options or tmdb in tmdb_options)):
                choices = {imdb}
                method = "catalogue_exact_title_year"
    if len(choices) != 1:
        return None
    imdb = next(iter(choices))
    tmdb_options = wd_imdb.get(imdb, set())
    if not tmdb and len(tmdb_options) == 1:
        tmdb = next(iter(tmdb_options))
    return imdb, tmdb, method


def save_ids(path, groups, mapping):
    added = Counter()
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(connect(path, "rw")) as db:
        required = {"source_key", "imdb_id", "tmdb_id", "method", "updated_at"}
        if not required <= _columns(db, "skip_auto_identities"):
            raise ValueError("Die EpiScene-Tabelle für automatische IDs hat ein anderes Schema")
        sources = _source_list(db, _columns(db, "skip_assets"))
        shared = {row[0] for row in db.execute("""
            SELECT DISTINCT source_key FROM skip_assets
            WHERE playlist_id NOT IN (8,10) OR media_type <> 'episode'
        """)}
        for source_key, (imdb, tmdb, method) in mapping.items():
            group = groups[source_key]
            asset = group["asset"]
            if source_key in shared:
                continue
            with db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                                     (asset["asset_key"],)).fetchone()
                if not current or any(current[field] != asset[field] for field in
                                      ("source_key", "playlist_id", "media_type", "title", "year")):
                    continue
                identity, status = _asset_identity(db, current, sources)
                if status == "conflicting_ids" or identity and (
                    identity["imdb_id"] not in ("", imdb)
                    or tmdb and identity["tmdb_id"] not in (0, tmdb)
                ):
                    continue
                changed = db.execute("""
                    INSERT INTO skip_auto_identities(source_key,imdb_id,tmdb_id,method,updated_at)
                    VALUES (?,?,?,?,?)
                    ON CONFLICT(source_key) DO UPDATE SET imdb_id=excluded.imdb_id,
                      tmdb_id=CASE WHEN skip_auto_identities.tmdb_id IS NULL
                                  OR skip_auto_identities.tmdb_id=0 THEN excluded.tmdb_id
                                  ELSE skip_auto_identities.tmdb_id END,
                      updated_at=excluded.updated_at
                    WHERE COALESCE(TRIM(skip_auto_identities.imdb_id),'')=''
                      AND (excluded.tmdb_id=0 OR COALESCE(skip_auto_identities.tmdb_id,0)
                           IN (0,excluded.tmdb_id))
                """, (source_key, imdb, tmdb, method, now)).rowcount
                if changed:
                    check, state = _asset_identity(db, current, sources)
                    if state != "ok" or check["imdb_id"] != imdb:
                        db.rollback()
                        continue
                    added.update(group["missing"])
    return added


def seed_open_cache(path, snapshot, entries, valid_range):
    now = int(time.time())
    rows = []
    for identity, markers in entries.items():
        duration = json.loads(identity)[6]
        valid = [marker for marker in markers
                 if valid_range(marker["segment_type"], marker["start_ms"], marker["end_ms"], duration)]
        if valid:
            rows.append((identity, now + 7 * 86400, now,
                         json.dumps({"trusted_segments": valid, "conflicts": [],
                                     "sources": {"introdb": "ok"}, "introdb_export": snapshot})))
    with closing(sqlite3.connect(_cache_path(path), timeout=12)) as db:
        db.executescript(SCHEMA)
        with db:
            updated = db.executemany("""
                INSERT INTO trusted_external_cache(identity,expires_at,created_at,response)
                VALUES (?,?,?,?)
                ON CONFLICT(identity) DO UPDATE SET expires_at=excluded.expires_at,
                    created_at=excluded.created_at,response=excluded.response
                WHERE trusted_external_cache.expires_at<=excluded.created_at
                  AND CASE WHEN json_valid(trusted_external_cache.response)
                    THEN COALESCE(json_array_length(trusted_external_cache.response,'$.conflicts'),0)=0
                    ELSE 0 END
            """, rows).rowcount
    return updated


@contextmanager
def release_cache(cache, entries, export_date, automation, runtime):
    previous_cache = runtime.CACHE
    with TemporaryDirectory(prefix="episcene-open-markers-") as temporary:
        work_cache = Path(temporary) / "trusted-sources.sqlite3"
        try:
            if cache.is_file():
                with closing(connect(cache, "ro")) as original, closing(
                    sqlite3.connect(_cache_path(work_cache))
                ) as copied:
                    original.backup(copied)
            refreshed = seed_open_cache(work_cache, export_date, entries, automation.valid_range)
            runtime.CACHE = work_cache
            print(f"IntroDB | {len(entries)} Folgenfassungen mit Kandidaten | "
                  f"{refreshed} Cache-Einträge für die Freigabe ergänzt", flush=True)
        except (OSError, sqlite3.Error, ValueError) as error:
            print(f"Cache-Ergänzung vorübergehend fehlgeschlagen ({type(error).__name__}). "
                  "Die Freigabe prüft den vorhandenen Live-Cache.", flush=True)
        try:
            yield
        finally:
            runtime.CACHE = previous_cache


def release_staged(catalogue, snapshot, cache, entries, export_date, gate, automation, release, runtime):
    with release_cache(cache, entries, export_date, automation, runtime):
        _, staged = gate.staged_markers(snapshot)
        confirmed = []
        report, _ = gate.inspect_catalogue(
            catalogue, staged, online_enabled=automation.enabled, release_enabled=release.enabled,
            trusted_online_markers=automation.trusted_online_markers, confirmed=confirmed,
        )
        releases = gate.apply_release(catalogue, confirmed, automation, release)
    return report, releases


def report_rows(path):
    raw = path.read_bytes()
    report = json.loads(raw)
    if (not isinstance(report, dict) or report.get("format") != RUNTIME_REPORT_FORMAT
            or not isinstance(report.get("episodes"), list)):
        raise ValueError("Datei ist keine Kandidatenliste aus dem IntroDB-Laufzeitprüflauf")
    rows = {}
    for row in report["episodes"]:
        key = row["asset_key"]
        if (not isinstance(key, str) or not 0 < len(key) <= 240 or row["playlist_id"] not in PLAYLISTS
                or not _clean_id("imdb_id", row["imdb_id"]) or key in rows
                or any(type(row[field]) is not int or row[field] < 0 for field in ("season", "episode"))):
            raise ValueError("Kandidatenliste enthält eine ungültige oder doppelte Folgenzuordnung")
        rows[key] = row
    return rows.values(), hashlib.sha256(raw).hexdigest()


def report_asset(db, row, sources):
    assets = db.execute("SELECT * FROM skip_assets WHERE asset_key=? LIMIT 2", (row["asset_key"],)).fetchall()
    if len(assets) != 1:
        return None, None
    asset = assets[0]
    if asset["playlist_id"] != row["playlist_id"] or asset["media_type"] != "episode":
        return None, None
    identity, state = _asset_identity(db, asset, sources)
    if state != "ok" or any(str(identity[key]) != str(row[key]) for key in ("imdb_id", "season", "episode")):
        return None, None
    return asset, identity


def collect_runtimes(catalogue, rows, export):
    stats = {lane: Counter() for lane in PLAYLISTS}
    pending = {lane: [] for lane in PLAYLISTS}
    ready = []
    with closing(connect(catalogue, "ro")) as db:
        db.execute("BEGIN")
        sources = _source_list(db, _columns(db, "skip_assets"))
        for row in rows:
            lane = row["playlist_id"]
            asset, identity = report_asset(db, row, sources)
            if asset is None:
                stats[lane]["Zuordnung geändert"] += 1
                continue
            payload = export.get((identity["imdb_id"], int(identity["season"]), int(identity["episode"])), {})
            kinds = [kind for kind in KINDS if kind in payload and not payload.get("no_" + kind)
                     and 0 <= payload[kind]["start_ms"] < payload[kind]["end_ms"] <= 86_400_000]
            if not kinds:
                stats[lane]["Treffer im Export entfallen"] += 1
                continue
            try:
                episode = Episode.from_dict(identity)
            except (TypeError, ValueError, OverflowError):
                stats[lane]["ohne Laufzeit"] += 1
                status = ready_to_measure(db, asset)
                if status:
                    pending[lane].append((status != "queued", -len(kinds), row["asset_key"], row, payload))
                continue
            stats[lane]["inzwischen mit Laufzeit"] += 1
            ready.append((episode, payload))
    return ready, pending, stats


def ready_to_measure(db, asset):
    if asset["duration_ms"] != 0:
        return None
    key = asset["asset_key"]
    jobs = db.execute("SELECT status FROM skip_jobs WHERE asset_key=? LIMIT 2", (key,)).fetchall()
    if len(jobs) == 1 and jobs[0]["status"] in ("queued", "failed") and db.execute(
        "SELECT 1 FROM skip_auto_assets WHERE asset_key=?", (key,)
    ).fetchone():
        return jobs[0]["status"]
    return None


@contextmanager
def analysis_slot(lock_path, deadline, *, on_timeout=None):
    import fcntl

    with lock_path.open("rb") as handle:
        next_message = time.monotonic()
        while time.monotonic() < deadline:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                now = time.monotonic()
                if now >= next_message:
                    print("Reguläre Analyse läuft | warte auf den freien Analyseslot ...", flush=True)
                    next_message = now + 60
                time.sleep(min(1, max(0, deadline - time.monotonic())))
                continue
            break
        else:
            if on_timeout is None:
                yield False
                return
            on_timeout()
            print("Analyseslot weiter belegt | Nachlauf bleibt aktiv und setzt beim nächsten freien Slot fort.",
                  flush=True)
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield True
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def catalogue_file_state(read_catalogue, playlist, asset, automation, busy):
    with read_catalogue() as db:
        identifiers = db.execute("""SELECT DISTINCT series_id FROM skip_catalogue_episodes
            WHERE playlist_id=? AND asset_key=? LIMIT 2""", (playlist["id"], asset["asset_key"])).fetchall()
        if not identifiers:
            identifiers = db.execute("""SELECT series_id FROM skip_auto_series
                WHERE playlist_id=? AND source_key=? AND season=? AND series_id<>'' LIMIT 2""",
                (playlist["id"], asset["source_key"], asset["season"])).fetchall()
    if len(identifiers) != 1 or automation.number(identifiers[0][0]) is None:
        return "keine eindeutige Anbieter-Serienzuordnung"
    series_id = identifiers[0][0]
    if automation.series_key(playlist, asset, series_id) != asset["source_key"]:
        return "gespeicherte Serienzuordnung passt nicht zum aktiven Anbieterpfad"
    try:
        body = automation.provider_api(playlist, "get_series_info", busy, series_id=series_id)
    except ValueError as error:
        match = re.fullmatch(r"provider_http_([45]\d{2})", str(error))
        return f"Katalog-API HTTP {match[1]}" if match else "Katalog-API nicht auswertbar"
    except OSError:
        return "Katalog-API nicht erreichbar"
    seasons = body.get("episodes") if isinstance(body, dict) else None
    if not isinstance(seasons, dict):
        return "Katalog-API liefert keine Episodenliste"
    if str(asset["season"]) not in seasons or seasons[str(asset["season"])] == []:
        return "Staffel fehlt in der aktuellen Anbieterantwort"
    episodes = automation.season_entries(body, asset["season"])
    if not episodes:
        return "Staffel in der Anbieterantwort nicht eindeutig"
    for episode in episodes:
        if episode["episode"] != asset["episode"]:
            continue
        if episode["stream_id"] == str(asset["stream_id"]) and episode["extension"] == asset["extension"]:
            return "Datei im aktuellen Anbieterkatalog unverändert"
        return "Anbieterkatalog nennt eine andere Stream-ID oder Dateiendung"
    return "Folge fehlt in der aktuellen Anbieterantwort"


def measure_episode(catalogue, row, automation, release, deadline, *, compare_context=False,
                    inspect_catalogue=False):
    from skip_analysis import probe, provider_asset_key, provider_proxy, source_url
    from skip_analysis_accounts import unavailable, using
    from skip_analysis_worker import busy_check

    lane, key = row["playlist_id"], row["asset_key"]

    def read_catalogue():
        return closing(connect(catalogue, "ro"))

    with read_catalogue() as db:
        sources = _source_list(db, _columns(db, "skip_assets"))
        asset, identity = report_asset(db, row, sources)
        if asset is None:
            return None, "Folge inzwischen geändert"
        try:
            return Episode.from_dict(identity), "Durch Worker nachgemessen"
        except (TypeError, ValueError, OverflowError):
            pass
        if not ready_to_measure(db, asset):
            return None, "Folge inzwischen geändert"
        if (not automation.enabled(db, lane, online=True) or not release.enabled(db, lane)
                or lane in unavailable(db)):
            return None, "Analysezugang oder Online-Freigabe pausiert"
        playlist = db.execute("SELECT * FROM skip_analysis_playlists WHERE id=?", (lane,)).fetchone()

    previous_url = None
    if compare_context:
        try:
            previous_url = source_url(playlist, asset)
        except (OSError, ValueError, KeyError):
            pass
    with using(read_catalogue):
        source_busy = busy_check(read_catalogue, [playlist])

        def busy():
            return time.monotonic() >= deadline or source_busy()

        def describe_catalogue():
            if inspect_catalogue and not busy():
                try:
                    state = catalogue_file_state(read_catalogue, playlist, asset, automation, busy)
                except (sqlite3.Error, OSError, ValueError, KeyError, TypeError):
                    state = "Anbieterabgleich nicht auswertbar"
                print(f"{PLAYLISTS[lane]} | Anbieterabgleich S{row['season']:02}E{row['episode']:02} | {state}",
                      flush=True)

        try:
            if busy():
                return None, "Laufzeitmessung zurückgestellt"
            url = source_url(playlist, asset)
            if compare_context:
                comparison = "gleicher Dateiaufruf" if url == previous_url else "anderer Dateiaufruf"
                if previous_url is None:
                    comparison = "bisheriger Dateiaufruf nicht ermittelbar"
                print(f"{PLAYLISTS[lane]} | regulärer Analysezugang | {comparison}", flush=True)
            if provider_asset_key(url, "episode") != key:
                describe_catalogue()
                return None, "Anbieterdatei nicht mehr eindeutig"
            with provider_proxy(url, busy) as source:
                duration, _ = probe(source, busy)
            if type(duration) is not int:
                raise ValueError("duration_unknown")
            episode = Episode.from_dict(dict(identity, duration_ms=duration))
            if busy_check(read_catalogue, [playlist])():
                return None, "Analysezugang oder Online-Freigabe pausiert"
        except ValueError as error:
            code = str(error)
            if code == "analysis_deferred":
                return None, "Laufzeitmessung zurückgestellt"
            match = re.fullmatch(r"provider_http_([45]\d{2})", code)
            if match and match[1] in ("404", "405"):
                describe_catalogue()
            return None, f"HTTP {match[1]}" if match else "Laufzeit nicht ermittelt"
        except OSError:
            return None, "Dateizugriff fehlgeschlagen"

    with closing(connect(catalogue, "rw")) as db, db:
        db.execute("BEGIN IMMEDIATE")
        current, current_identity = report_asset(db, row, sources)
        if current != asset or current_identity != identity or not ready_to_measure(db, current):
            return None, "Folge inzwischen geändert"
        if not automation.enabled(db, lane, online=True) or not release.enabled(db, lane):
            return None, "Analysezugang oder Online-Freigabe pausiert"
        db.execute("UPDATE skip_assets SET duration_ms=? WHERE asset_key=? AND duration_ms=0", (duration, key))
    return episode, "Laufzeit gemessen"


@contextmanager
def probe_history(path):
    # The checkpoint beside the report stores only playlist IDs and opaque asset keys.
    descriptor = os.open(path, os.O_CREAT | os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode) or mode & 0o077:
            raise ValueError("Prüfverlauf ist keine private reguläre Datei")
    finally:
        os.close(descriptor)
    with closing(connect(path, "rw")) as db:
        with db:
            db.execute("""CREATE TABLE IF NOT EXISTS checked (
                playlist_id INTEGER NOT NULL, asset_key TEXT NOT NULL, PRIMARY KEY(playlist_id, asset_key))""")
        yield db


def measurement_batches(pending, limit, history, offset):
    if not limit:
        return

    queues = {}
    for lane, candidates in pending.items():
        ordered = sorted(candidates)
        if history is None:
            queues[lane] = ordered[:limit]
            continue
        checked = {row[0] for row in history.execute("SELECT asset_key FROM checked WHERE playlist_id=?", (lane,))}
        if ordered:
            start = offset % len(ordered)
            ordered = ordered[start:] + ordered[:start]
        queues[lane] = [item for item in ordered if item[2] not in checked]
        print(f"{PLAYLISTS[lane]} | {len(queues[lane])} messbare Folgen stehen in diesem Durchlauf noch aus",
              flush=True)
    longest = max((len(items) for items in queues.values()), default=0)
    for start in range(0, longest, limit):
        yield {lane: items[start:start + limit] for lane, items in queues.items() if start < len(items)}


def sample_runtimes(catalogue, pending, automation, release, ready, stats, history=None, *, release_on_wait=None):
    from skip_remote_client import RemoteDeferred, configured, health

    lock = catalogue.with_name("skip-analysis.lock")
    if lock.is_symlink() or not lock.is_file() or not configured():
        print("Messung zurückgestellt | Worker-Konfiguration oder Analysesperre fehlt.", flush=True)
        return set(pending)

    def worker_ready():
        try:
            health()
        except RemoteDeferred:
            print("Messung zurückgestellt | Hetzner-Worker nicht erreichbar oder Versionen unterschiedlich.", flush=True)
            return False
        return True

    if not worker_ready():
        return set(pending)
    deadline = time.monotonic() + MEASUREMENT_SECONDS
    paused = set()
    unavailable_states = ("HTTP 404", "HTTP 405", "Anbieterdatei nicht mehr eindeutig")
    for batch in zip_longest(*pending.values()):
        for item in batch:
            if item is None:
                continue
            _, _, _, row, payload = item
            lane = row["playlist_id"]
            if lane in paused:
                continue
            slot_deadline = time.monotonic() + MEASUREMENT_SECONDS if history is not None else deadline
            with analysis_slot(lock, slot_deadline, on_timeout=release_on_wait) as acquired:
                if not acquired:
                    print("Zeitbudget der Messung erreicht | vorhandene Ergebnisse gehen in die Freigabeprüfung.", flush=True)
                    return set(pending)
                if history is not None and history.execute(
                    "SELECT 1 FROM checked WHERE playlist_id=? AND asset_key=?", (lane, row["asset_key"])
                ).fetchone():
                    continue
                if history is not None and time.monotonic() >= slot_deadline and not worker_ready():
                    return set(pending)
                started = time.monotonic()
                probe_deadline = started + MEASUREMENT_SECONDS if history is not None else deadline
                try:
                    inspect_catalogue = sum(stats[lane][state] for state in unavailable_states) < 2
                    episode, state = measure_episode(
                        catalogue, row, automation, release, probe_deadline,
                        compare_context=stats[lane]["Messversuche"] == 0, inspect_catalogue=inspect_catalogue,
                    )
                except sqlite3.OperationalError as error:
                    error_code = getattr(error, "sqlite_errorcode", sqlite3.SQLITE_ERROR) & 0xff
                    if error_code not in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED):
                        raise
                    episode, state = None, "Datenbank beschäftigt"
                stats[lane]["Messzeit"] += time.monotonic() - started
                stats[lane]["Messversuche"] += 1
                if history is not None and (episode is not None or state in unavailable_states):
                    with history:
                        history.execute("INSERT OR IGNORE INTO checked(playlist_id,asset_key) VALUES(?,?)",
                                        (lane, row["asset_key"]))
            stats[lane][state] += 1
            if episode:
                ready.append((episode, payload))
            else:
                if history is None or stats[lane][state] <= 2:
                    print(f"{PLAYLISTS[lane]} | Messung S{row['season']:02}E{row['episode']:02} | {state}", flush=True)
                if state in ("Analysezugang oder Online-Freigabe pausiert", "Laufzeitmessung zurückgestellt",
                             "HTTP 401", "HTTP 403", "HTTP 429"):
                    paused.add(lane)
                if not stats[lane]["Laufzeit gemessen"] and (
                    stats[lane]["HTTP 404"] + stats[lane]["Anbieterdatei nicht mehr eindeutig"] >= 4
                ):
                    paused.add(lane)
                    print(f"{PLAYLISTS[lane]} | Nachmessung nach vier HTTP-404- oder Zuordnungsfehlern pausiert",
                          flush=True)
            if state == "Laufzeit gemessen":
                if stats[lane][state] == 1:
                    print(f"{PLAYLISTS[lane]} | Laufzeit für S{row['season']:02}E{row['episode']:02} gemessen",
                          flush=True)
                elif stats[lane][state] % 10 == 0:
                    print(f"{PLAYLISTS[lane]} | {stats[lane][state]} Laufzeiten gemessen", flush=True)
    return paused


def release_runtime_markers(catalogue, ready, cache, exported_at, gate, automation, release, runtime):
    entries, confirmed = {}, []
    for episode, payload in ready:
        markers, _ = _promote(parse_introdb(payload, episode), {kind for kind in KINDS if payload.get("no_" + kind)})
        candidates = {gate.stamp(marker) for marker in markers if automation.valid_range(
            marker["segment_type"], marker["start_ms"], marker["end_ms"], episode.duration_ms
        )}
        if candidates:
            key = _key(episode)
            entries[key] = markers
            confirmed.append((episode.playlist_id, episode.asset_key, key, candidates))
    if not confirmed:
        return {}
    with release_cache(cache, entries, exported_at, automation, runtime):
        return gate.apply_release(catalogue, confirmed, automation, release)


def recover_runtime_report(catalogue, report, cache, stage, gate, automation, release, runtime, limit, *,
                           playlist=None, sweep=False, offset=0):
    rows, report_hash = report_rows(report)
    selected = [playlist] if isinstance(playlist, int) else playlist
    playlists = {lane: PLAYLISTS[lane] for lane in (selected or PLAYLISTS)}
    selected_rows = (row for row in rows if row["playlist_id"] in playlists)
    print("Lade den IntroDB-Export und prüfe die gespeicherte Kandidatenliste ...", flush=True)
    manifest, export = stage.load_snapshot()
    print(stage.INTRODB_ATTRIBUTION, flush=True)
    ready, pending, stats = collect_runtimes(catalogue, selected_rows, export)
    pending = {lane: pending[lane] for lane in playlists}
    approvals = Counter()

    def release_ready():
        if ready:
            results = release_runtime_markers(catalogue, ready, cache, manifest["generated_at"],
                                              gate, automation, release, runtime)
            for lane in playlists:
                approvals[lane] += results.get(lane, {}).get("neu freigegeben", 0)
            ready.clear()

    history_path = report.with_name(f"{report.stem}.{report_hash[:24]}.progress.sqlite3")
    history_context = probe_history(history_path) if sweep else nullcontext(None)
    paused = set()
    with history_context as history:
        if sweep:
            release_ready()
        for batch in measurement_batches(pending, limit, history, offset):
            batch = {lane: items for lane, items in batch.items() if lane not in paused}
            if not batch:
                break
            print("Laufzeitmessung im regulären Analyse-Slot | " +
                  " | ".join(f"{PLAYLISTS[lane]} bis zu {len(items)} Folgen" for lane, items in batch.items()),
                  flush=True)
            block_stats = {lane: Counter() for lane in batch}
            interrupted = sample_runtimes(catalogue, batch, automation, release, ready, block_stats, history,
                                          release_on_wait=release_ready if sweep else None)
            paused.update(interrupted)
            for lane, counts in block_stats.items():
                stats[lane].update(counts)
            release_ready()
            if sweep:
                for lane in batch:
                    print(f"{PLAYLISTS[lane]} | bisher {stats[lane]['Messversuche']} Messversuche | "
                          f"HTTP 404 bei {stats[lane]['HTTP 404']} | HTTP 405 bei {stats[lane]['HTTP 405']} | "
                          f"{approvals[lane]} Marker neu freigegeben", flush=True)
                    if lane in interrupted:
                        print(f"{PLAYLISTS[lane]} | Nachlauf pausiert | Prüfstand gespeichert.", flush=True)
    release_ready()
    for lane, name in playlists.items():
        counts = stats[lane]
        measured = counts["Laufzeit gemessen"]
        concurrent = counts["Durch Worker nachgemessen"]
        open_episodes = counts["ohne Laufzeit"] - measured - concurrent
        approved = approvals[lane]
        print(f"{name} | nachgemessen {measured} | seit Prüflauf bereits mit Laufzeit "
              f"{counts['inzwischen mit Laufzeit'] + concurrent} | Marker neu freigegeben {approved} "
              f"| weiterhin ohne Laufzeit {open_episodes} | Messzeit {counts['Messzeit']:.1f} s",
              flush=True)


def update_catalogue(catalogue, snapshot, cache, stage, gate, automation, release, runtime):
    wd_tmdb, wd_imdb, maze_title, maze_tvdb = {}, {}, {}, {}
    try:
        print("Lade öffentliche Wikidata-Zuordnung von TMDB zu IMDb ...", flush=True)
        wd_tmdb, wd_imdb = wikidata_ids()
    except (OSError, EOFError, ValueError) as error:
        print(f"Wikidata-Index vorübergehend nicht verfügbar ({type(error).__name__})", flush=True)
    try:
        print("Lade öffentlichen TVmaze-Serienindex für den lokalen Abgleich ...", flush=True)
        maze_title, maze_tvdb = tvmaze_index()
    except (OSError, EOFError, ValueError, KeyError, TypeError) as error:
        print(f"TVmaze-Index vorübergehend nicht vollständig ({type(error).__name__})", flush=True)
    print("Lese die aktuellen Serienmetadaten beider Analyse-Playlists ...", flush=True)
    groups = catalogue_groups(catalogue)
    local = local_index(groups)
    missing = {key: group for key, group in groups.items() if group["missing"]}
    mapping = {}
    for key, group in missing.items():
        if match := match_group(group, local, wd_tmdb, wd_imdb, maze_title, maze_tvdb):
            mapping[key] = match
    added = save_ids(catalogue, groups, mapping) if mapping else Counter()
    print(f"Serienzuordnungen gefunden | {len(mapping)}/{len(missing)}", flush=True)

    print("Gleiche den vollständigen IntroDB-Export mit dem aktuellen Katalog ab ...", flush=True)
    manifest, index = stage.load_snapshot()
    staged_report, entries = stage.match_catalogue(catalogue, index)
    stage.save_snapshot(snapshot, manifest, entries)
    print(stage.INTRODB_ATTRIBUTION, flush=True)
    report, releases = release_staged(catalogue, snapshot, cache, entries, manifest["generated_at"],
                                      gate, automation, release, runtime)
    for lane, name in PLAYLISTS.items():
        still_missing = staged_report[name].get("IMDb-ID fehlt", 0)
        checked = report[lane]["Marker geprüft"]
        approved = releases[lane]["neu freigegeben"]
        open_markers = checked - (report[lane]["bereits freigegeben"] + approved)
        print(f"{name} | IMDb für {added[lane]} Folgen ergänzt | IMDb weiterhin offen {still_missing} | "
              f"Marker geprüft {checked} | neu freigegeben {approved} | "
              f"offene oder bestehende Prüfentscheidungen {open_markers}", flush=True)


def main():
    import episcene_knowledge_first_runtime
    import skip_automation
    import skip_release

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=PRODUCTION)
    parser.add_argument("--snapshot", type=Path, default=SNAPSHOT)
    parser.add_argument("--cache", type=Path, default=CACHE)
    parser.add_argument("--runtime-report", type=Path, help="Kandidatenliste aus --missing-runtimes nachprüfen")
    parser.add_argument("--measure", type=int, default=0, metavar="FOLGEN_PRO_PLAYLIST",
                        help="Maximale Folgenzahl je Playlist, im Nachlauf je Block (Standard dort 64)")
    parser.add_argument("--playlist", type=int, nargs="+", choices=tuple(PLAYLISTS),
                        help="Ausgewählte Analyse-Playlists bearbeiten (8 = 4K ANALYSE, 10 = THE BEST)")
    parser.add_argument("--sweep", action="store_true",
                        help="Alle messbaren Kandidaten der gewählten Playlists abwechselnd mit Prüfverlauf bearbeiten")
    parser.add_argument("--offset", type=int, default=0,
                        help="Die sortierte Kandidatenliste für den Nachlauf um diese Anzahl drehen")
    args = parser.parse_args()
    if args.measure and (not args.runtime_report or not 1 <= args.measure <= 64):
        parser.error("--measure braucht --runtime-report sowie einen Wert zwischen 1 und 64")
    if args.playlist is not None and not args.runtime_report:
        parser.error("--playlist braucht --runtime-report")
    if args.sweep and args.playlist is None:
        parser.error("--sweep braucht --playlist")
    if args.offset < 0 or (args.offset and not args.sweep):
        parser.error("--offset braucht --sweep und einen nichtnegativen Wert")
    with TemporaryDirectory(prefix="episcene-catalogue-") as temporary:
        stage, gate = load_helpers(Path(temporary))
        if args.runtime_report:
            recover_runtime_report(args.catalog, args.runtime_report, args.cache, stage, gate,
                                   skip_automation, skip_release, episcene_knowledge_first_runtime,
                                   (args.measure or 64) if args.sweep else args.measure,
                                   playlist=args.playlist, sweep=args.sweep, offset=args.offset)
        else:
            update_catalogue(args.catalog, args.snapshot, args.cache, stage, gate,
                             skip_automation, skip_release, episcene_knowledge_first_runtime)


if __name__ == "__main__":
    try:
        main()
    except (OSError, EOFError, ValueError, sqlite3.Error, ImportError, AttributeError,
            KeyError, TypeError, RuntimeError) as error:
        raise SystemExit(f"EpiScene-Kataloglauf abgebrochen ({type(error).__name__}): {error}") from None
