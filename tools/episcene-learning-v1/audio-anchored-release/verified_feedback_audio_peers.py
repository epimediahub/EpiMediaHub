#!/usr/bin/env python3
"""Use authenticated historical feedback as audio-reference *candidates*.

Only same playlist + series source key + season + segment type, other episode.
Manual marks from different providers/playlists require independent verified
cut identity before reuse. Matching validates actual 15s+ content using V2.
NO side effects, approvals, downloads or worker changes.
"""
from __future__ import annotations
from collections import defaultdict

from authenticated_feedback_reference_bank import VerifiedReference
from fingerprint_cohort_v2 import match, near_record


def reference_index(references):
    index=defaultdict(list)
    for ref in references:
        if not isinstance(ref,VerifiedReference):
            continue
        if ref.playlist_id not in (8,10):
            continue
        index[(ref.playlist_id,ref.source_key,ref.season,ref.kind)].append(ref)
    for value in index.values():
        value.sort(key=lambda p:(p.episode,p.asset_key))
    return index


def trusted_peers_for_target(index,target):
    """Return verified historical positives for *other* episodes only."""
    key=(target["playlist_id"],target["source_key"],
         target["season"],target["segment_type"])
    for peer in index.get(key,()):
        if peer.asset_key==target["asset_key"] or peer.episode==target["episode"]:
            continue
        yield peer


def compare_authenticated_mark(target,reference,target_window,reference_window):
    """Return a fingerprint hit only inside the saved human-marked boundaries."""
    if (reference.playlist_id!=target["playlist_id"]
            or reference.source_key!=target["source_key"]
            or reference.season!=target["season"]
            or reference.kind!=target["segment_type"]
            or reference.episode==target["episode"]
            or reference.asset_key==target["asset_key"]):
        return None
    if reference_window is None or target_window is None:
        return None
    found=match(target_window,reference_window)
    if found is None:
        return None
    if not near_record(found,start_ms=target["start_ms"],
                       end_ms=target["end_ms"]):
        return None
    if not near_record(found,start_ms=reference.start_ms,
                       end_ms=reference.end_ms,target=False):
        return None
    return found


def peer_record_for_cache(ref):
    """Compatible with existing cached() helper, not a DB row or approval."""
    return {"asset_key":ref.asset_key, "segment_type":ref.kind,
            "asset_duration_ms":ref.duration_ms}


def anchor_is_blocked(con,ref):
    # Reject explicit blocks/corrections, but a validated user approved row
    # is not itself an automatic veto against using their reference.
    if con.execute("""SELECT 1 FROM skip_auto_blocks
        WHERE asset_key=? AND kind=? AND ABS(duration_ms-?)<=2000 LIMIT 1""",
        (ref.asset_key,ref.kind,ref.duration_ms)).fetchone():
        return True
    return bool(con.execute("""SELECT 1 FROM skip_records
       WHERE asset_key=? AND segment_type=? AND status IN ('rejected','disabled')
         AND ABS(duration_ms-?)<=2000 LIMIT 1""",
       (ref.asset_key,ref.kind,ref.duration_ms)).fetchone())
