"""Bulk IntroDB export and series-level TheIntroDB coverage for the prefetch job."""

from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
import gzip
import io
import json
import os
import sqlite3
import tempfile
import time
from contextlib import closing
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import Request, urlopen
import zipfile
import zlib

from bridge import KINDS, _get_json
from runtime_integration import _cache_path

INTRODB_DATA = "https://data.introdb.app/snapshots/"
INTRODB_ATTRIBUTION = "Contains data from IntroDB (introdb.app), available under the ODbL."
EXPORT_FILES = ("segments.csv.gz", "segmentless.csv.gz")
EXPORT_LIMIT = 32 * 1024 * 1024
DAY = 86400
COVERAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS trusted_theintrodb_coverage (
    identity TEXT PRIMARY KEY,
    expires_at INTEGER NOT NULL,
    coordinates TEXT NOT NULL
);
"""


def _download(url):
    request = Request(url, headers={"User-Agent": "EpiSceneMarkerBridge/1.0"})
    with urlopen(request, timeout=8) as response:
        body = response.read(EXPORT_LIMIT + 1)
    if len(body) > EXPORT_LIMIT:
        raise ValueError("IntroDB export exceeds the supported size")
    return body


def _export_rows(data, required):
    with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:
        with io.TextIOWrapper(compressed, encoding="utf-8-sig", newline="") as source:
            rows = csv.DictReader(source)
            if not required <= set(rows.fieldnames or ()):
                raise ValueError("Unrecognized IntroDB export columns")
            for row in rows:
                if any(row.get(name) is None for name in required):
                    raise ValueError("Incomplete IntroDB export row")
                yield row


def _export_index(segments, segmentless):
    index = {}
    for data, absent in ((segments, False), (segmentless, True)):
        required = {"imdb_id", "is_movie", "season", "episode", "segment"}
        if not absent:
            required |= {"start_ms", "end_ms"}
        for row in _export_rows(data, required):
            kind = row["segment"]
            if kind not in KINDS or row["is_movie"].lower() not in {"f", "false", "0"}:
                continue
            coordinate = (row["imdb_id"], int(row["season"]), int(row["episode"]))
            markers = index.setdefault(coordinate, {})
            if absent:
                markers["no_" + kind] = True
            else:
                marker = {"start_ms": int(row["start_ms"]), "end_ms": int(row["end_ms"])}
                if kind in markers and markers[kind] != marker:
                    raise ValueError("Conflicting rows in IntroDB export")
                markers[kind] = marker
    return index


def _save_export(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temporary:
        name = temporary.name
        try:
            with zipfile.ZipFile(temporary, "w") as bundle:
                for filename, content in zip(EXPORT_FILES, data):
                    bundle.writestr(filename, content)
            temporary.flush()
            os.replace(name, path)
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass


def load_introdb_export(path, *, download=_download, now=None):
    """Return one consistent dated pair of published and explicitly absent segments."""
    now = time.time() if now is None else now
    errors = (OSError, EOFError, UnicodeError, ValueError, TypeError, KeyError,
              csv.Error, zipfile.BadZipFile, zlib.error)
    try:
        if now - path.stat().st_mtime < DAY:
            with zipfile.ZipFile(path) as bundle:
                return _export_index(*(bundle.read(name) for name in EXPORT_FILES))
    except errors:
        pass
    today = datetime.fromtimestamp(now, timezone.utc).date()
    for day in (today, today - timedelta(days=1)):
        try:
            root = INTRODB_DATA + day.isoformat() + "/"
            data = tuple(download(root + name) for name in EXPORT_FILES)
            index = _export_index(*data)
        except errors:
            continue
        try:
            _save_export(path, data)
        except OSError:
            pass  # This run can use the fresh snapshot even if caching failed.
        return index
    return None


def _theintrodb_coordinates(payload, identity):
    """Only a complete, explicit v4 episode list can answer a coverage miss."""
    if (not isinstance(payload, dict) or payload.get("type") != "tv"
            or type(payload.get("tvdb_id")) is not int or payload["tvdb_id"] <= 0
            or not isinstance(payload.get("episodes"), list)
            or payload.get("next") or payload.get("has_more")):
        return None
    if identity[0] == "tvdb_id" and str(payload["tvdb_id"]) != identity[1]:
        return None
    supported = ("intro_accepted_count", "recap_accepted_count", "credits_accepted_count")
    coordinates = set()
    for row in payload["episodes"]:
        if not isinstance(row, dict):
            return None
        values = [row.get(key) for key in ("season", "episode", *supported)]
        if any(type(value) is not int or value < 0 for value in values):
            return None
        season, episode, *counts = values
        if any(counts):
            coordinates.add((season, episode))
    return coordinates


class CatalogueSources:
    """Adapt the existing episode transport without changing marker validation."""

    def __init__(self, cache, *, fetch=_get_json, introdb_loader=load_introdb_export):
        self.cache = _cache_path(cache)
        self.fetch = fetch
        self.introdb_loader = introdb_loader
        self.introdb = None
        self.introdb_loaded = False
        self.coverage = {}
        self.next_request = 0.0
        self.rate_limited = False
        with closing(sqlite3.connect(self.cache, timeout=6)) as db:
            db.executescript(COVERAGE_SCHEMA)

    def _theintrodb(self, url):
        if self.rate_limited:
            return {"status": "rate_limited", "data": None}
        wait = self.next_request - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self.next_request = time.monotonic() + 0.42
        reply = self.fetch(url)
        self.rate_limited = reply.get("status") == "rate_limited"
        return reply

    def _coverage(self, root, identity):
        if identity in self.coverage:
            return self.coverage[identity]
        key = urlencode([identity])
        now = int(time.time())
        with closing(sqlite3.connect(self.cache, timeout=6)) as db:
            row = db.execute(
                "SELECT coordinates FROM trusted_theintrodb_coverage "
                "WHERE identity=? AND expires_at>?", (key, now)).fetchone()
            if row:
                try:
                    coordinates = {tuple(item) for item in json.loads(row[0])}
                except (TypeError, ValueError):
                    coordinates = None
                else:
                    self.coverage[identity] = coordinates
                    return coordinates
            reply = self._theintrodb(root + "?" + key)
            coordinates = (_theintrodb_coordinates(reply.get("data"), identity)
                           if reply.get("status") == "ok" else None)
            if coordinates is not None:
                with db:
                    db.execute(
                        "INSERT INTO trusted_theintrodb_coverage VALUES(?,?,?) "
                        "ON CONFLICT(identity) DO UPDATE SET expires_at=excluded.expires_at, "
                        "coordinates=excluded.coordinates",
                        (key, now + DAY, json.dumps(sorted(coordinates))))
        self.coverage[identity] = coordinates
        return coordinates

    def __call__(self, url):
        parsed = urlsplit(url)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        if parsed.hostname == "api.introdb.app" and parsed.path == "/segments":
            if not self.introdb_loaded:
                self.introdb = self.introdb_loader(
                    self.cache.with_name(self.cache.name + ".introdb.zip"))
                self.introdb_loaded = True
            if self.introdb is not None:
                key = (query["imdb_id"], int(query["season"]), int(query["episode"]))
                return {"status": "ok", "data": {
                    "imdb_id": key[0], "season": key[1], "episode": key[2],
                    **self.introdb.get(key, {})}}
        if parsed.hostname != "api.theintrodb.org" or parsed.path != "/v4/media":
            return self.fetch(url)
        if query.get("mapping", "default") == "default":
            identity = next(((name, query[name]) for name in ("tvdb_id", "tmdb_id", "imdb_id")
                             if name in query), None)
            if identity is not None:
                root = "https://api.theintrodb.org/v4/media"
                coordinates = self._coverage(root, identity)
                episode = (int(query["season"]), int(query["episode"]))
                if coordinates is not None and episode not in coordinates:
                    return {"status": "not_found", "data": None}
        return self._theintrodb(url)
