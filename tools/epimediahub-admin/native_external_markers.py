"""Authenticated EpiScene external marker read model (no writes, no provider calls).

Reuse the same exact-ID, episode and cut matching as the read-only Hetzner
marker report. Missing trusted bridge code or source databases fail closed.
"""
from __future__ import annotations

from collections import Counter
import importlib
import sqlite3
import sys
import time
from pathlib import Path

TRUSTED_BRIDGE = Path("/opt/episcene-learning/unified")
CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
MAX_ROWS = 5000
PAGE_SIZE = 50
PLAYLISTS = {"8": "4K ANALYSE", "10": "THE BEST"}
SOURCES = {"introdb": "IntroDB", "theintrodb": "TheIntroDB"}
KINDS = {"intro", "recap", "outro"}
CACHE_STATES = {"active", "expired"}


class ExternalMarkerUnavailable(RuntimeError):
    pass


def _report_module():
    if TRUSTED_BRIDGE.is_symlink() or not TRUSTED_BRIDGE.is_dir():
        raise ExternalMarkerUnavailable("trusted_bridge_missing")
    name = TRUSTED_BRIDGE / "report_trusted_marker_series.py"
    if name.is_symlink() or not name.is_file():
        raise ExternalMarkerUnavailable("trusted_report_missing")
    # The root-reviewed EpiScene installation is the only accepted source for
    # the report code; never evaluate modules supplied by the device.
    if str(TRUSTED_BRIDGE) not in sys.path:
        sys.path.insert(0, str(TRUSTED_BRIDGE))
    return importlib.import_module("report_trusted_marker_series")


def validate_filter(playlist="", source="", state="", q="", page="1"):
    if playlist not in ("", "8", "10"):
        raise ValueError("invalid_playlist")
    if source not in ("", *SOURCES.keys()):
        raise ValueError("invalid_source")
    if state not in ("", *CACHE_STATES):
        raise ValueError("invalid_state")
    if not isinstance(q, str) or len(q) > 80 or "\x00" in q:
        raise ValueError("invalid_query")
    if not isinstance(page, str) or not page.isascii() or not page.isdecimal():
        raise ValueError("invalid_page")
    value = int(page)
    if not 1 <= value <= 100:
        raise ValueError("invalid_page")
    return playlist, source, state, q.strip().casefold(), value


def list_external_markers(production: Path, *, cache: Path = CACHE,
                          playlist="", source="", state="", q="", page="1"):
    playlist, source, state, q, page = validate_filter(playlist, source, state, q, page)
    report = _report_module()
    try:
        with report.ro(cache) as db:
            # Bound memory/CPU even if the hourly prefetch grows for years.
            size = int(db.execute("SELECT COUNT(*) FROM trusted_external_cache").fetchone()[0])
            if size > MAX_ROWS:
                raise ExternalMarkerUnavailable("cache_too_large_for_live_view")
            _, entries = report.accepted_entries(db)
        if entries:
            with report.ro(production) as prod:
                linked = report.series_matches(prod, entries)
        else:
            linked = {}
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise ExternalMarkerUnavailable("readonly_marker_source_unavailable") from exc

    now = int(time.time())
    rows = []
    for index, item in enumerate(entries):
        active = item["expires"] > now
        cache_state = "active" if active else "expired"
        if state and state != cache_state:
            continue
        # The shared external cache has no playlist ID. Only an exact
        # independently authenticated source ID + matching cut can link it.
        mappings = linked.get(index, set())
        if not mappings:
            continue
        for playlist_label, title in mappings:
            pid = "8" if playlist_label == PLAYLISTS["8"] else (
                "10" if playlist_label == PLAYLISTS["10"] else "")
            if not pid or (playlist and playlist != pid):
                continue
            if q and q not in title.casefold():
                continue
            for marker in item["segments"]:
                origin = marker["source"]
                kind = marker["segment_type"]
                if origin not in SOURCES or kind not in KINDS:
                    continue
                if source and source != origin:
                    continue
                rows.append({
                    "playlist_id": pid,
                    "playlist": playlist_label,
                    "title": title[:180],
                    "season": item["season"],
                    "episode": item["episode"],
                    "source": origin,
                    "kind": kind,
                    "start_ms": marker["start_ms"],
                    "end_ms": marker["end_ms"],
                    "cache_status": cache_state,
                })
    rows.sort(key=lambda row: (
        row["playlist_id"], row["title"].casefold(), row["season"], row["episode"],
        row["kind"], row["source"], row["start_ms"]
    ))
    total = len(rows)
    selected = rows[(page - 1)*PAGE_SIZE:page*PAGE_SIZE]
    totals = Counter(r["source"] for r in rows)
    return {
        "scope": "analysis_playlists_only",
        "read_only": True,
        "markers": selected,
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "has_more": page*PAGE_SIZE < total,
        "source_counts": {k: int(totals[k]) for k in SOURCES},
        "cached_episode_count": len(entries),
        "cache_entry_count": size,
        "generated_at_epoch": now,
        "notice": "Cache-Marker; keine Garantie fuer Anzeige am Endgeraet",
    }
