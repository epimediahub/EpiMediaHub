"""Read-only canonical ID joining for dedicated EpiScene analysis playlists.

Uses existing skip_records / skip_identities / skip_auto_identities columns.
Only joins on exact asset_key or source_key; never title/name similarity.
Conflicting valid IDs are withheld instead of guessing an identity.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from runtime_integration import _cache_path

IMDB = re.compile(r"^tt[0-9]{7,9}$")
SOURCE_TABLES = ("skip_assets", "skip_identities", "skip_auto_identities", "skip_records")
ID_NAMES = ("imdb_id", "tmdb_id", "tvdb_id")
BASE_REQUIRED = {"asset_key", "playlist_id", "season", "episode", "duration_ms"}
STATE = """
CREATE TABLE IF NOT EXISTS trusted_source_sync_cursor(
 singleton INTEGER PRIMARY KEY CHECK(singleton=1),
 playlist_id INTEGER NOT NULL, asset_key TEXT NOT NULL);
"""


def _columns(db, table):
    return {row["name"] for row in db.execute("PRAGMA table_info("+table+")")}


def _source_list(db, asset_columns):
    found = []
    for table in SOURCE_TABLES:
        cols = _columns(db, table)
        ids = tuple(k for k in ID_NAMES if k in cols)
        if not ids:
            continue
        if table == "skip_assets":
            found.append((table, None, ids, cols))
        elif "asset_key" in cols:
            found.append((table, "asset_key", ids, cols))
        elif "source_key" in cols and "source_key" in asset_columns:
            found.append((table, "source_key", ids, cols))
    return found


def _id_not_null(prefix, fields):
    return "(" + " OR ".join(
        "("+prefix+"."+k+" IS NOT NULL AND CAST("+prefix+"."+k+
        " AS TEXT) NOT IN ('','0'))" for k in fields) + ")"


def _selection_sql(sources):
    clauses = []
    for table, key, fields, cols in sources:
        if table == "skip_assets":
            clauses.append("SELECT a.playlist_id,a.asset_key FROM skip_assets a "
                           "WHERE a.playlist_id IN (8,10) AND "+_id_not_null("a", fields))
            continue
        criteria = ""
        if table == "skip_records" and "status" in cols:
            criteria = " AND (s.status IS NULL OR s.status NOT IN " \
                       "('rejected','superseded','disabled'))"
        if "playlist_id" in cols:
            criteria += " AND s.playlist_id=a.playlist_id"
        clauses.append(
            "SELECT a.playlist_id,a.asset_key FROM skip_assets a JOIN "+table+
            " s ON s."+key+"=a."+key+" WHERE a.playlist_id IN (8,10)"
            " AND "+_id_not_null("s", fields)+criteria
        )
    return " UNION ".join(clauses)


def _clean_id(name, value):
    if value is None or value == "":
        return None
    if name == "imdb_id":
        text = str(value).strip()
        return text if IMDB.fullmatch(text) else None
    try:
        number = int(value)
        return number if 1 <= number <= 1000000000 else None
    except (TypeError, ValueError, OverflowError):
        return None


def _asset_identity(db, asset, sources):
    values = {name: set() for name in ID_NAMES}
    for table, key, fields, cols in sources:
        if table == "skip_assets":
            records = [asset]
        else:
            constraint = " AND playlist_id=?" if "playlist_id" in cols else ""
            status = (
                " AND (status IS NULL OR status NOT IN "
                "('rejected','superseded','disabled'))"
                if table == "skip_records" and "status" in cols else ""
            )
            selector = ", ".join(fields)
            args = (asset[key], asset["playlist_id"]) if constraint else (asset[key],)
            records = db.execute(
                "SELECT "+selector+" FROM "+table+" WHERE "+key+"=?"+
                constraint+status+" LIMIT 60", args).fetchall()
        for rec in records:
            for field in fields:
                clean = _clean_id(field, rec[field])
                if clean is not None:
                    values[field].add(clean)
    if any(len(ids) > 1 for ids in values.values()):
        return None, "conflicting_ids"
    ids = {field: next(iter(matches)) if matches else ("" if field=="imdb_id" else 0)
           for field, matches in values.items()}
    if not any(ids.values()):
        return None, "no_valid_id"
    result = {
        "asset_key": asset["asset_key"], "playlist_id": asset["playlist_id"],
        "season": asset["season"], "episode": asset["episode"],
        "duration_ms": asset["duration_ms"], **ids,
    }
    return result, "ok"


def catalog_batch(prod, cache, limit=40):
    """Resolve at most limit indexed analysis episodes per invocation.

    Maintains an independent cursor in a private cache; the source database is
    always opened in SQLite mode=ro.
    """
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("limit must be 1 to 100")
    p = Path(prod)
    if not p.is_file() or p.is_symlink():
        return [], "production_db_unavailable", {"candidates":0,"conflicts":0}
    with sqlite3.connect(p.resolve().as_uri()+"?mode=ro", uri=True, timeout=6) as db:
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA query_only=ON")
        cols = _columns(db, "skip_assets")
        if not BASE_REQUIRED <= cols:
            return [], "missing_episode_columns", {"candidates":0,"conflicts":0}
        sources = _source_list(db, cols)
        if not sources:
            return [], "missing_canonical_external_ids", {"candidates":0,"conflicts":0}
        where = _selection_sql(sources)
        with sqlite3.connect(_cache_path(cache), timeout=6) as cache_db:
            cache_db.executescript(STATE)
            last = cache_db.execute(
                "SELECT playlist_id,asset_key FROM trusted_source_sync_cursor "
                "WHERE singleton=1").fetchone()
            tail = ("WHERE (playlist_id > ? OR (playlist_id=? AND asset_key>?)) "
                    if last else "")
            params = (last[0],last[0],last[1],limit) if last else (limit,)
            query = ("SELECT playlist_id,asset_key FROM ("+where+") "+tail+
                     "ORDER BY playlist_id,asset_key LIMIT ?")
            keys = db.execute(query, params).fetchall()
            if not keys and last:
                with cache_db:
                    cache_db.execute("DELETE FROM trusted_source_sync_cursor")
                keys = db.execute(
                    "SELECT playlist_id,asset_key FROM ("+where+") "
                    "ORDER BY playlist_id,asset_key LIMIT ?", (limit,)).fetchall()
        output, conflicts = [], 0
        for key in keys:
            candidates = db.execute(
                "SELECT * FROM skip_assets WHERE playlist_id=? AND asset_key=? LIMIT 2",
                (key["playlist_id"],key["asset_key"])).fetchall()
            if len(candidates) != 1:
                conflicts += 1
                continue
            resolved, reason = _asset_identity(db, candidates[0], sources)
            if resolved is None:
                conflicts += 1
                continue
            output.append(resolved)
        status = "ok" if keys else "no_episodes_with_identifiers"
        return output, status, {"candidates":len(keys),
                                "conflicts":conflicts,
                                "last":dict(keys[-1]) if keys else None}
