#!/usr/bin/env python3
"""EpiScene Learning Engine: segment-specific profiles from VERIFIED user labels.

IMPORTANT:
- Read-only access to the separate Learning Engine SQLite database.
- A marker with source='device', status='approved', or reviewed_at is NOT
  necessarily authenticated human feedback and is NOT included here.
- Never changes any marker, threshold or customer release. No autotraining.
- All profiles are per series + playlist + season + segment type.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sqlite3
from statistics import median
import sys

DB_PATH = Path("/var/lib/episcene-learning/knowledge.sqlite3")
TYPES = ("intro", "recap", "outro")
MIN_EXAMPLES_FOR_REFERENCE = {"intro": 3, "recap": 4, "outro": 3}


def _normalized(text):
    return " ".join(str(text or "").casefold().split())


def _positive_duration(row):
    try:
        start, end = int(row["start_ms"]), int(row["end_ms"])
    except (KeyError, TypeError, ValueError):
        return None
    if 0 <= start < end <= 86_400_000:
        return (end - start) / 1000.0
    return None


def verified_profiles(rows):
    """Make advisory duration profiles; conflicting reviewer labels are excluded."""
    observations = defaultdict(list)
    for row in rows:
        try:
            if int(row.get("verified", 0)) != 1 or int(row.get("active", 0)) != 1:
                continue
            kind = str(row["segment_type"]).strip().lower()
            if kind not in TYPES:
                continue
            duration = _positive_duration(row)
            title = _normalized(row.get("series_normalized") or row.get("series_title"))
            asset = str(row.get("asset_key") or "")
            if duration is None or not title or not asset:
                continue
            key = (title, row.get("playlist_id"), int(row.get("season", 0)), kind)
            observations[(key, asset)].append(duration)
        except (KeyError, ValueError, TypeError):
            continue

    groups = defaultdict(list)
    ambiguous = defaultdict(int)
    for (group_key, asset), durations in observations.items():
        if len(durations) > 1:
            # Different reviewers can agree within 0.25s. Conflicting annotations
            # must be adjudicated rather than silently averaged.
            if max(durations) - min(durations) > 0.25:
                ambiguous[group_key] += 1
                continue
        groups[group_key].append(median(durations))

    results = []
    for key in sorted(set(groups) | set(ambiguous), key=lambda x: tuple(map(str,x))):
        durations = groups[key]
        title, playlist, season, kind = key
        min_examples = MIN_EXAMPLES_FOR_REFERENCE[kind]
        item = {
            "series": title,
            "playlist_id": playlist,
            "season": season,
            "segment_type": kind,
            "verified_episodes": len(durations),
            "conflicted_episodes_excluded": ambiguous[key],
            "reference_ready": len(durations) >= min_examples,
            "median_duration_sec": round(median(durations), 3) if durations else None,
            "min_duration_sec": round(min(durations), 3) if durations else None,
            "max_duration_sec": round(max(durations), 3) if durations else None,
            "median_absolute_deviation_sec": (
                round(median([abs(x-median(durations)) for x in durations]), 3)
                if durations else None
            ),
            "release_automatically": False
        }
        results.append(item)
    return results


def load_verified_rows(db_path=DB_PATH):
    path = Path(db_path)
    if not path.is_file() or path.is_symlink():
        raise FileNotFoundError(f"Learning DB unavailable: {path}")
    uri = path.resolve().as_uri() + "?mode=ro"
    with sqlite3.connect(uri, uri=True, timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='labels'"
        ).fetchone()
        if not has_table:
            raise RuntimeError("Learning Engine labels table missing")
        rows = conn.execute("""
          SELECT asset_key, playlist_id, series_title, series_normalized,
                 season, segment_type, start_ms, end_ms, verified, active
          FROM labels WHERE verified=1 AND active=1
        """).fetchall()
    return [dict(r) for r in rows]


def main():
    if len(sys.argv) > 2:
        raise SystemExit("Usage: segment_profiles.py [learning-db-path]")
    rows = load_verified_rows(sys.argv[1] if len(sys.argv) == 2 else DB_PATH)
    profiles = verified_profiles(rows)
    print(json.dumps({
        "mode": "shadow", "automatic_publication_enabled": False,
        "verified_active_labels_scanned": len(rows),
        "profiles": profiles,
        "note": "Duration is advisory, not a hard threshold. Audio/visual evidence must verify boundaries."
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
