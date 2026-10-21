#!/usr/bin/env python3
"""EpiScene unified marker bridge: read-only source, independently reviewed evidence.

This module does not install Jellyfin/Silo, edit provisioning.db, contact IPTV
servers or publish unverified third-party timestamps. Python stdlib only.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

KINDS = ("recap", "intro", "outro")
ANALYSIS_PLAYLISTS = (8, 10)
IMDB_RE = re.compile(r"^tt\d{7,9}$")
FINGERPRINT_RE = re.compile(r"^[0-9a-f]{64}$")
SOURCES = ("introdb", "theintrodb")
DDL = """
CREATE TABLE IF NOT EXISTS verified_markers (
 marker_id INTEGER PRIMARY KEY, asset_key TEXT NOT NULL, playlist_id INTEGER NOT NULL,
 title TEXT NOT NULL, season INTEGER NOT NULL, episode INTEGER NOT NULL,
 kind TEXT NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
 duration_ms INTEGER NOT NULL, fingerprint TEXT NOT NULL DEFAULT '',
 provenance TEXT NOT NULL, reviewed_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS verified_by_asset ON verified_markers(playlist_id,asset_key);
CREATE INDEX IF NOT EXISTS verified_by_fingerprint ON verified_markers(fingerprint,season,episode,kind);
"""

@dataclass(frozen=True)
class Episode:
    playlist_id: int
    asset_key: str
    season: int
    episode: int
    duration_ms: int
    imdb_id: str = ""
    tvdb_id: int = 0
    fingerprint: str = ""
    title: str = ""
    mapping: str = "default"

    @classmethod
    def from_dict(cls, data):
        ep = cls(
            playlist_id=int(data["playlist_id"]), asset_key=str(data["asset_key"]),
            season=int(data["season"]), episode=int(data["episode"]),
            duration_ms=int(data["duration_ms"]),
            imdb_id=str(data.get("imdb_id") or ""),
            tvdb_id=int(data.get("tvdb_id") or 0),
            fingerprint=str(data.get("fingerprint") or "").lower(),
            title=str(data.get("title") or "").strip(),
            mapping=str(data.get("mapping") or "default").lower())
        if not ep.asset_key or len(ep.asset_key) > 240 or ep.season < 0 or ep.episode < 0:
            raise ValueError("Invalid episode identity")
        if ep.duration_ms < 30000 or ep.duration_ms > 86400000:
            raise ValueError("Invalid episode duration")
        if ep.imdb_id and not IMDB_RE.fullmatch(ep.imdb_id):
            raise ValueError("Invalid IMDb id")
        if ep.mapping not in {"default", "official", "dvd", "alternate", "absolute", "regional"}:
            raise ValueError("Invalid TVDB episode ordering")
        if ep.tvdb_id < 0:
            raise ValueError("Invalid TVDB id")
        if ep.fingerprint and not FINGERPRINT_RE.fullmatch(ep.fingerprint):
            raise ValueError("Expected a SHA-256 cut fingerprint")
        return ep

def windows(duration_ms):
    """Suggested search windows, NEVER hard rejection bounds."""
    return {
        "recap": [0, min(duration_ms, 180000)],
        "intro": [0, min(duration_ms, 600000)],
        "outro": [max(0, duration_ms - 300000), duration_ms],
    }

def _milliseconds(value):
    if type(value) not in (int, float) or value != value:
        return None
    if not 0 <= value <= 86400000:
        return None
    return round(value)

def segment(kind, start, end, ep, source, confidence=None):
    a, b = _milliseconds(start), _milliseconds(end)
    if a is None or b is None or not 0 <= a < b <= ep.duration_ms + 1500 or a >= ep.duration_ms:
        return None
    if confidence is not None and (
        type(confidence) not in (int, float) or not 0 <= confidence <= 1
    ):
        confidence = None
    return {"kind": kind, "start_ms": a, "end_ms": min(b, ep.duration_ms),
            "source": source, "confidence": confidence}

def parse_introdb(payload, ep):
    if not isinstance(payload, dict):
        return []
    out = []
    for kind in KINDS:
        if payload.get("no_" + kind) is True:
            continue
        item = payload.get(kind)
        if not isinstance(item, dict):
            continue
        candidate = segment(kind, item.get("start_ms"), item.get("end_ms"),
                            ep, "introdb", item.get("confidence"))
        if candidate:
            out.append(candidate)
    return out

def parse_theintrodb(payload, ep):
    if not isinstance(payload, dict) or payload.get("kind") in ("versions", "episodes"):
        return []
    out = []
    for external, internal in (("recap", "recap"), ("intro", "intro"), ("credits", "outro")):
        entries = payload.get(external, [])
        if not isinstance(entries, list):
            continue
        for item in entries[:12]:
            if not isinstance(item, dict):
                continue
            start = item.get("start_ms")
            end = item.get("end_ms")
            # Documented null semantics: starts at zero / ends at media end.
            a = 0 if start is None else start
            b = ep.duration_ms if end is None else end
            candidate = segment(internal, a, b, ep, "theintrodb",
                                item.get("confidence"))
            if candidate:
                out.append(candidate)
    return out

def _get_json(url):
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "EpiSceneMarkerBridge/1.0"})
    try:
        with urlopen(req, timeout=5) as response:
            if response.status != 200:
                return {"status": "error", "data": None}
            raw = response.read(262145)
            if len(raw) > 262144:
                return {"status": "oversize", "data": None}
            return {"status": "ok", "data": json.loads(raw)}
    except HTTPError as exc:
        return {"status": "rate_limited" if exc.code == 429 else
                "not_found" if exc.code == 404 else "http_error", "data": None}
    except (URLError, TimeoutError, ValueError, OSError):
        return {"status": "network_error", "data": None}

def remote_candidates(ep, fetch=_get_json):
    """Public read-only lookups. Never request/consume IPTV streams."""
    results, source_status = [], {}
    if ep.imdb_id:
        url = "https://api.introdb.app/segments?" + urlencode({
            "imdb_id": ep.imdb_id, "season": ep.season, "episode": ep.episode})
        reply = fetch(url)
        source_status["introdb"] = reply["status"]
        if reply["status"] == "ok":
            results += parse_introdb(reply["data"], ep)
    else:
        source_status["introdb"] = "no_imdb_identity"
    key = ("tvdb_id", ep.tvdb_id) if ep.tvdb_id else ("imdb_id", ep.imdb_id)
    if key[1]:
        params = {key[0]: key[1], "season": ep.season, "episode": ep.episode,
                  "duration_ms": ep.duration_ms, "details": "true",
                  "mapping": ep.mapping}
        url = "https://api.theintrodb.org/v4/media?" + urlencode(params)
        reply = fetch(url)
        source_status["theintrodb"] = reply["status"]
        if reply["status"] == "ok":
            results += parse_theintrodb(reply["data"], ep)
    else:
        source_status["theintrodb"] = "no_external_identity"
    return results, source_status

def _open_ro(file):
    p = Path(file)
    if p.is_symlink() or not p.is_file():
        raise ValueError("Missing or symbolic-link source database")
    db = sqlite3.connect(p.resolve().as_uri() + "?mode=ro", uri=True, timeout=5)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA query_only=ON")
    return db

def import_authenticated_feedback(feedback_db, production_db, store_db):
    """Only the existing authenticated feedback learning output counts as truth.

    Rebuilds the local verified snapshot atomically. Never writes production or
    feedback database. Fingerprint stays blank without actual cut evidence.
    """
    target = Path(store_db)
    if target.is_symlink():
        raise ValueError("Symlink store not allowed")
    with _open_ro(feedback_db) as fb, _open_ro(production_db) as prod:
        fb_columns = {r["name"] for r in fb.execute("PRAGMA table_info(feedback_versions)")}
        required = {"marker_id", "asset_key", "playlist_id", "season", "episode",
                    "kind", "decision", "active", "start_ms", "end_ms",
                    "provenance", "reviewed_at"}
        if not required <= fb_columns:
            raise ValueError("Authenticated feedback schema missing fields")
        asset_cols = {r["name"] for r in prod.execute("PRAGMA table_info(skip_assets)")}
        if not {"asset_key", "playlist_id", "title", "duration_ms", "season", "episode"} <= asset_cols:
            raise ValueError("Asset schema missing fields")
        fp_col = next((col for col in ("content_fingerprint", "media_fingerprint")
                       if col in asset_cols), None)
        chosen = []
        rows = fb.execute("""SELECT marker_id,asset_key,playlist_id,season,episode,
                            kind,decision,active,start_ms,end_ms,provenance,reviewed_at
                            FROM feedback_versions WHERE active=1 AND decision='positive'""")
        for r in rows:
            if r["playlist_id"] not in ANALYSIS_PLAYLISTS or r["kind"] not in KINDS:
                continue
            if r["provenance"] not in ("device_authenticated_direct", "admin_reviewed_machine"):
                continue
            asset = prod.execute("SELECT * FROM skip_assets WHERE asset_key=?",
                                 (r["asset_key"],)).fetchone()
            if asset is None or (asset["playlist_id"], asset["season"], asset["episode"]) != (
                    r["playlist_id"], r["season"], r["episode"]):
                continue
            dur = asset["duration_ms"]
            if type(dur) is not int or type(r["start_ms"]) is not int or type(r["end_ms"]) is not int:
                continue
            if not 0 <= r["start_ms"] < r["end_ms"] <= dur:
                continue
            fingerprint = str(asset[fp_col] or "").lower() if fp_col else ""
            if fingerprint and not FINGERPRINT_RE.fullmatch(fingerprint):
                fingerprint = ""
            chosen.append((r["marker_id"], r["asset_key"], r["playlist_id"],
                           str(asset["title"] or "").casefold().strip(),
                           r["season"], r["episode"], r["kind"], r["start_ms"],
                           r["end_ms"], dur, fingerprint, r["provenance"], r["reviewed_at"]))
    with sqlite3.connect(target, timeout=10) as db:
        with db:
            db.executescript(DDL)
            db.execute("DELETE FROM verified_markers")
            db.executemany("INSERT INTO verified_markers VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", chosen)
    return {"imported_authenticated_markers": len(chosen),
            "from_playlists": list(ANALYSIS_PLAYLISTS),
            "production_database_written": False,
            "external_markers_auto_published": False}

def find_verified(db_path, ep):
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    if db_path.is_symlink():
        raise ValueError("Symlink knowledge store not allowed")
    with _open_ro(db_path) as db:
        matches = db.execute("""SELECT * FROM verified_markers
                                WHERE season=? AND episode=? AND kind IN ('intro','recap','outro')""",
                             (ep.season, ep.episode)).fetchall()
    ready = []
    for r in matches:
        same_asset = r["playlist_id"] == ep.playlist_id and r["asset_key"] == ep.asset_key
        same_cut = bool(ep.fingerprint and r["fingerprint"] and
                        ep.fingerprint == r["fingerprint"] and
                        abs(ep.duration_ms - r["duration_ms"]) <= 1500)
        if not (same_asset or same_cut):
            continue
        if r["end_ms"] > ep.duration_ms:
            continue
        ready.append({"kind": r["kind"], "start_ms": r["start_ms"],
                      "end_ms": r["end_ms"], "source": "authenticated_feedback",
                      "marker_id": r["marker_id"], "match": "same_asset" if same_asset else "same_cut",
                      "confidence": 1.0})
    return ready

def evaluate(ep, store_path=None, external=True, fetch=_get_json):
    verified = find_verified(store_path, ep) if store_path else []
    external_rows, status = remote_candidates(ep, fetch) if external else ([], {})
    ready, conflicting = [], []
    for kind in KINDS:
        rows = [r for r in verified if r["kind"] == kind]
        distinct = {(r["start_ms"], r["end_ms"]) for r in rows}
        if len(distinct) == 1:
            ready.append(rows[0])
        elif len(distinct) > 1:
            conflicting.append(kind)
    # No remote data is blindly released: external episode IDs alone do not
    # prove an identical cut or prove the accuracy of third-party timestamps.
    suggestions = [dict(c, status="needs_cut_verification") for c in external_rows
                   if c["kind"] not in conflicting and
                   not any(r["kind"] == c["kind"] for r in ready)]
    return {"playlist_id": ep.playlist_id, "asset_key": ep.asset_key,
            "search_windows_ms": windows(ep.duration_ms),
            "ready_verified": ready, "review_candidates": suggestions,
            "conflicts": conflicting, "source_status": status,
            "automatic_release_only_from_authenticated_evidence": True,
            "external_sources_are_advisory": True}

def main():
    p = argparse.ArgumentParser(description="EpiScene unified marker bridge")
    sub = p.add_subparsers(dest="command", required=True)
    imp = sub.add_parser("sync-verified", help="Refresh from authenticated feedback")
    imp.add_argument("--feedback", required=True)
    imp.add_argument("--production", required=True)
    imp.add_argument("--store", required=True)
    ask = sub.add_parser("evaluate", help="Read one episode JSON from stdin")
    ask.add_argument("--store")
    ask.add_argument("--offline", action="store_true")
    args = p.parse_args()
    if args.command == "sync-verified":
        result = import_authenticated_feedback(args.feedback, args.production, args.store)
    else:
        result = evaluate(Episode.from_dict(json.load(sys.stdin)), args.store,
                          external=not args.offline)
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
