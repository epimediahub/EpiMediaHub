#!/usr/bin/env python3
"""Read-only overlap between historic device-approved records and signed reviews.

This is an inventory tool. Even exact overlap is merely corroborating
provenance; a legacy row without feedback is not silently authenticated.
No writes, no names, keys, user IDs or credentials in returned counts.
"""
from __future__ import annotations
from collections import Counter, defaultdict

MAX_LEGACY_ROWS=10_000


def audit_overlap(con, validated_refs):
    refs=defaultdict(list)
    for x in validated_refs:
        refs[(x.asset_key,x.kind)].append(x)
    rows=con.execute("""
      SELECT r.asset_key,r.segment_type,r.start_ms,r.end_ms,
             r.duration_ms,r.disabled,
             a.playlist_id,a.source_key,a.season,a.episode,a.duration_ms
      FROM skip_records r
      JOIN skip_assets a ON a.asset_key=r.asset_key
      WHERE r.source='device' AND r.status='approved'
      ORDER BY r.id LIMIT ?
    """,(MAX_LEGACY_ROWS+1,)).fetchall()
    if len(rows)>MAX_LEGACY_ROWS:
        raise RuntimeError("STOP: TOO_MANY_LEGACY_DEVICE_ROWS")
    counts=Counter()
    distinct_series=set()
    unmatched_series=set()
    for (asset_key,kind,start,end,duration,disabled,pid,source,season,episode,
         asset_duration) in rows:
        counts["legacy_approved_device_rows"]+=1
        distinct_series.add((pid,source))
        if disabled:
            counts["disabled_or_revoked_legacy_rows"]+=1
            continue
        choices=[r for r in refs[(asset_key,kind)]
                 if (r.playlist_id,r.source_key,r.season,r.episode,
                     r.duration_ms)==(pid,source,season,episode,asset_duration)]
        if not choices:
            counts["without_matching_signed_asset_reference"]+=1
            unmatched_series.add((pid,source))
            continue
        exact=any((r.start_ms,r.end_ms)==(start,end) for r in choices)
        near=any(isinstance(start,int) and isinstance(end,int)
                 and abs(r.start_ms-start)<=1500
                 and abs(r.end_ms-end)<=1500 for r in choices)
        if exact:
            counts["signed_feedback_exact_bounds"]+=1
        elif near:
            counts["signed_feedback_within_1500ms"]+=1
        else:
            counts["signed_asset_but_different_boundaries"]+=1
            unmatched_series.add((pid,source))
    out=dict(sorted(counts.items()))
    out["distinct_series_with_legacy_approved_rows"]=len(distinct_series)
    out["distinct_series_needing_provenance_review"]=len(unmatched_series)
    out["all_unmatched_legacy_rows_are_held_not_promoted"]=True
    return out
