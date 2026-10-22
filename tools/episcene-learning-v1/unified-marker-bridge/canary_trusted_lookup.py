#!/usr/bin/env python3
"""Read-only EpiScene trusted external marker lookup canary.

Scans at most 100 existing 4K ANALYSE / THE BEST inventory assets.
Confirms that the existing trusted cache can be read via the SAME matcher
intended for the original /v1/device/skip/lookup response. No app/API changes,
customer access, HTTP calls or IPTV streaming. Emits aggregate counts only.
"""
from __future__ import annotations

import json
import tempfile
from collections import Counter
from pathlib import Path

from analysis_identity import catalog_batch
from production_lookup_cache import augment_authorized_segments

PRODUCTION = Path("/var/lib/epimediahub/provisioning.db")
CACHE = Path("/var/lib/episcene-learning/trusted-sources.sqlite3")
PRIVATE = Path("/var/lib/episcene-learning")


def canary(prod=PRODUCTION, cache=CACHE, private=PRIVATE, limit=100):
    stats = Counter()
    result = {
        "mode": "READ_ONLY_SHADOW",
        "production_database_written": False,
        "public_device_endpoint_modified": False,
        "external_network_calls": 0,
        "provider_streams_opened": 0,
        "customer_identifiers_emitted": False,
        "scope": "analysis playlists 8 and 10 only",
    }
    if (not private.is_dir() or private.is_symlink() or
            not prod.is_file() or prod.is_symlink() or
            not cache.is_file() or cache.is_symlink()):
        return dict(result, status="STOP_REQUIRED_INPUT_MISSING")
    try:
        with tempfile.TemporaryDirectory(prefix="episcene-lookup-canary-",
                                         dir=private) as scratch:
            rows, status, meta = catalog_batch(prod, Path(scratch)/"cursor.db", limit)
            result["identity_status"] = status
            result["identity_candidates_checked"] = meta.get("candidates",0)
            result["identity_conflicts_skipped"] = meta.get("conflicts",0)
            if status != "ok":
                return dict(result, status="STOP_METADATA_UNAVAILABLE")
            for row in rows:
                if row.get("playlist_id") not in (8, 10):
                    continue
                # Both values are built from server-side read-only metadata.
                descriptor = {
                    "media_type": "episode", "source_key": "verified-analysis",
                    "asset_key": row["asset_key"],
                    "season": row["season"], "episode": row["episode"],
                    "duration_ms": row["duration_ms"],
                }
                identity = dict(
                    row, source_key="verified-analysis")
                matched = augment_authorized_segments(
                    [], descriptor=descriptor, persisted_identity=identity,
                    cache=cache)
                stats["episodes_evaluated"] += 1
                if matched:
                    stats["episodes_with_trusted_segments"] += 1
                    stats["external_segments_ready"] += len(matched)
                    stats["playlist_" + str(row["playlist_id"]) +
                          "_matched_episodes"] += 1
                    for seg in matched:
                        if seg.get("source") in ("introdb","theintrodb"):
                            stats["source_" + seg["source"]] += 1
    except (OSError, ValueError, TypeError):
        return dict(result, status="STOP_SHADOW_READ_FAILED")
    result.update({
        "status": "SHADOW_CHECK_COMPLETE",
        "episodes_evaluated": stats["episodes_evaluated"],
        "episodes_with_trusted_segments": stats["episodes_with_trusted_segments"],
        "external_segments_ready": stats["external_segments_ready"],
        "analysis_4k_matched_episodes": stats["playlist_8_matched_episodes"],
        "analysis_the_best_matched_episodes": stats["playlist_10_matched_episodes"],
        "markers_from_introdb": stats["source_introdb"],
        "markers_from_theintrodb": stats["source_theintrodb"],
        "customer_lookup_proven": False,
        "next_gate": "Exact live Flask handler check, service account, then controlled rollout",
    })
    return result


if __name__ == "__main__":
    print(json.dumps(canary(), ensure_ascii=False, indent=2))
