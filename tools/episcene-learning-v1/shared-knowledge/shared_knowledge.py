#!/usr/bin/env python3
"""EpiScene provider-independent marker knowledge (no automatic publication).

A conservative reference resolver. Designed for integration with the original
EpiScene release gate: it NEVER inserts into production skip_records or changes
approval thresholds. Input episode IDs and content alignment evidence must be
verified by the caller; title-only matching is expressly unsupported.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
import sqlite3
from typing import Optional

ANALYSIS_PLAYLISTS = frozenset((8, 10))
KINDS = frozenset(("intro", "recap", "outro"))
SOURCES = frozenset(("human_verified", "analyzer_verified", "introdb", "theintrodb"))
IMDB = re.compile(r"^tt[0-9]{5,12}$")
WINDOW_MS = {"recap": 180_000, "intro": 600_000, "outro": 300_000}
MAX_DISAGREEMENT_MS = 1500


@dataclass(frozen=True)
class Episode:
    namespace: str
    media_id: str
    season: int
    episode: int
    duration_ms: int
    cut_digest: str = ""

    def __post_init__(self):
        if self.namespace not in ("imdb", "tvdb"):
            raise ValueError("Verified IMDb or TVDB identity required")
        if (self.namespace == "imdb" and not IMDB.fullmatch(self.media_id)) or (
            self.namespace == "tvdb" and
            (not self.media_id.isdecimal() or int(self.media_id) < 1)
        ):
            raise ValueError("Invalid external identity")
        if (type(self.season) is not int or self.season < 0 or
            type(self.episode) is not int or self.episode < 1 or
            type(self.duration_ms) is not int or not 60_000 <= self.duration_ms <= 43_200_000):
            raise ValueError("Invalid episode coordinates or duration")
        if self.cut_digest and not re.fullmatch(r"[0-9a-f]{64}", self.cut_digest):
            raise ValueError("Content fingerprint must be a SHA-256 digest")


@dataclass(frozen=True)
class Marker:
    kind: str
    start_ms: int
    end_ms: int
    source: str
    playlist_id: int
    cut_digest: str = ""

    def validate(self, duration_ms: int):
        if self.kind not in KINDS or self.source not in SOURCES:
            raise ValueError("Unknown segment or provenance")
        if type(self.playlist_id) is not int or self.playlist_id not in ANALYSIS_PLAYLISTS:
            raise ValueError("Only independent analysis playlists may teach the database")
        if (type(self.start_ms) is not int or type(self.end_ms) is not int or
            not 0 <= self.start_ms < self.end_ms <= duration_ms or
            self.end_ms - self.start_ms < 5000):
            raise ValueError("Invalid media segment boundaries")
        if self.cut_digest and not re.fullmatch(r"[0-9a-f]{64}", self.cut_digest):
            raise ValueError("Bad cut digest")


def search_windows(duration_ms: int) -> dict:
    """Soft scan priorities, never exclusion constraints."""
    if type(duration_ms) is not int or duration_ms <= 0:
        raise ValueError("Invalid duration")
    return {
        "recap": (0, min(duration_ms, WINDOW_MS["recap"])),
        "intro": (0, min(duration_ms, WINDOW_MS["intro"])),
        "outro": (max(0, duration_ms - WINDOW_MS["outro"]), duration_ms),
        "expand_on_miss": True,
    }


def _interval(kind, row, duration_ms):
    if not isinstance(row, dict):
        return None
    start = row.get("start_ms")
    end = row.get("end_ms")
    if start is None and kind in ("recap", "intro"):
        start = 0
    if end is None and kind == "outro":
        end = duration_ms
    if type(start) is not int or type(end) is not int:
        return None
    if 0 <= start < end <= duration_ms and end - start >= 5000:
        return {"kind": kind, "start_ms": start, "end_ms": end}
    return None


def parse_introdb_app(data: dict, duration_ms: int) -> list:
    """https://api.introdb.app/segments (IMDb episode identity checked by caller)."""
    if not isinstance(data, dict):
        raise ValueError("Unexpected IntroDB result")
    found = []
    for kind in ("recap", "intro", "outro"):
        row = data.get(kind)
        if data.get("no_" + kind) is True:
            if row is not None:
                raise ValueError("Conflicting IntroDB absence and marker")
            continue
        segment = _interval(kind, row, duration_ms)
        if segment:
            found.append(segment)
    # post_credits intentionally not mistaken for an outro
    return found


def parse_theintrodb(data: dict, duration_ms: int) -> list:
    """TheIntroDB v4 /media; array segments and nullable clip boundaries."""
    if not isinstance(data, dict):
        raise ValueError("Unexpected TheIntroDB result")
    found = []
    for remote, kind in (("recap", "recap"), ("intro", "intro"), ("credits", "outro")):
        value = data.get(remote) or []
        if not isinstance(value, list):
            raise ValueError("Unexpected TheIntroDB segment type")
        for row in value:
            segment = _interval(kind, row, duration_ms)
            if segment:
                found.append(segment)
    return found


class Knowledge:
    """Independent SQLite store, never the live provisioning DB."""

    def __init__(self, db_path):
        self.db_path = str(db_path)
        if Path(self.db_path).name == "provisioning.db":
            raise ValueError("Do not write into production provisioning.db")

    @staticmethod
    def init(db):
        db.execute("""
        CREATE TABLE IF NOT EXISTS verified_references(
          namespace TEXT NOT NULL, media_id TEXT NOT NULL,
          season INTEGER NOT NULL, episode INTEGER NOT NULL,
          playlist_id INTEGER NOT NULL, kind TEXT NOT NULL,
          start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
          source TEXT NOT NULL, cut_digest TEXT NOT NULL DEFAULT '',
          PRIMARY KEY(namespace,media_id,season,episode,playlist_id,
                      kind,start_ms,end_ms,source,cut_digest)
        )""")
        db.execute("""CREATE INDEX IF NOT EXISTS references_episode_idx
          ON verified_references(namespace,media_id,season,episode,kind)""")

    def add(self, ep: Episode, marker: Marker):
        marker.validate(ep.duration_ms)
        if marker.cut_digest != ep.cut_digest:
            raise ValueError("Reference and episode cut identity disagree")
        with sqlite3.connect(self.db_path, timeout=15) as db:
            self.init(db)
            db.execute("""INSERT OR IGNORE INTO verified_references
              VALUES(?,?,?,?,?,?,?,?,?,?)""",
              (ep.namespace, ep.media_id, ep.season, ep.episode,
               marker.playlist_id, marker.kind, marker.start_ms,
               marker.end_ms, marker.source, marker.cut_digest))

    def resolve(self, target: Episode) -> list:
        """Answer only: is a marker a reference or safe candidate for ORIGINAL gate?

        A matching duration or series name is NEVER proof of an identical cut.
        Multiple disagreeing same-cut references stop automated use.
        """
        with sqlite3.connect(self.db_path, timeout=15) as db:
            self.init(db)
            refs = db.execute("""SELECT playlist_id,kind,start_ms,end_ms,source,cut_digest
              FROM verified_references WHERE namespace=? AND media_id=? AND
                   season=? AND episode=? ORDER BY kind,source,playlist_id""",
              (target.namespace,target.media_id,target.season,target.episode)).fetchall()
        results = []
        for kind in ("recap", "intro", "outro"):
            candidates = []
            for playlist, rk, start, end, source, digest in refs:
                if rk != kind or not (0 <= start < end <= target.duration_ms):
                    continue
                same_cut = bool(target.cut_digest and digest == target.cut_digest)
                candidates.append(dict(
                    kind=kind,start_ms=start,end_ms=end,source=source,
                    from_playlist=playlist,cut_verified=same_cut))
            exact = [m for m in candidates if m["cut_verified"]]
            if exact:
                conflict = any(
                    abs(m["start_ms"] - exact[0]["start_ms"]) > MAX_DISAGREEMENT_MS or
                    abs(m["end_ms"] - exact[0]["end_ms"]) > MAX_DISAGREEMENT_MS
                    for m in exact[1:])
                if conflict:
                    results.append(dict(kind=kind,status="conflict_review",
                                        references=len(exact),
                                        eligible_for_original_release_gate=False))
                else:
                    best = sorted(exact, key=lambda m:
                                  (m["source"] not in ("human_verified","analyzer_verified"),
                                   m["from_playlist"]))[0]
                    results.append(dict(**best,status="cut_verified_reference",
                                        references=len(exact),
                                        eligible_for_original_release_gate=True))
            elif candidates:
                results.append(dict(kind=kind,status="needs_cut_alignment",
                                    references=len(candidates),
                                    eligible_for_original_release_gate=False))
        return results


def admitted_external(ep: Episode, data: dict, *, provider: str, playlist_id: int):
    """Construct source-tagged references; caller validates API identity and cut.

    External timestamps are recorded as trusted knowledge, NOT auto-approved
    customer skip markers. Fingerprint evidence is never fabricated.
    """
    parser = {"introdb": parse_introdb_app, "theintrodb": parse_theintrodb}.get(provider)
    if not parser:
        raise ValueError("Unsupported public reference source")
    if provider == "introdb":
        if (ep.namespace != "imdb" or data.get("imdb_id") != ep.media_id or
            data.get("season") != ep.season or data.get("episode") != ep.episode):
            raise ValueError("IntroDB episode identity mismatch")
    elif provider == "theintrodb":
        if (ep.namespace != "tvdb" or
            str(data.get("tvdb_id")) != ep.media_id):
            raise ValueError("TheIntroDB identity mismatch")
        if data.get("season") not in (None, ep.season) or data.get("episode") not in (None,ep.episode):
            raise ValueError("TheIntroDB episode index mismatch")
    # External timing is never evidence that the specific IPTV cut matches.
    return [Marker(x["kind"],x["start_ms"],x["end_ms"],provider,playlist_id,"")
            for x in parser(data,ep.duration_ms)]


def demo_summary(ep: Episode, db_path):
    """No episode title, provider URL or credentials in returned diagnostics."""
    return {"search_windows":search_windows(ep.duration_ms),
            "decisions":Knowledge(db_path).resolve(ep),
            "production_mutated":False,"customer_markers_approved":False}
