#!/usr/bin/env python3
"""EpiScene: inventory ALL authenticated historical manual feedback, read-only.

Authoritative positives live in feedback_versions, not in skip_records.source='device'.
The database may include thousands of user-marked series, older revocations and
machine suggestions. A trusted reference must be active + positive with signed
backend provenance, exact asset identity and current segment bounds.

This module NEVER inserts approvals or exposes customer/stream/asset identifiers.
A returned candidate is NOT authorization to release or copy a marker.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
import sqlite3

FEEDBACK=Path("/var/lib/episcene-learning/reference-round-40/feedback.sqlite3")
PRODUCTION=Path("/var/lib/epimediahub/provisioning.db")
TRUSTED_PROVENANCE=frozenset(("device_authenticated_direct","admin_reviewed_machine"))
USER_PROVENANCE="device_authenticated_direct"
KINDS=frozenset(("intro","outro","recap"))
ANALYSIS_PLAYLISTS=frozenset((8,10))
MAX_FEEDBACK_ROWS=100_000
MAX_ASSET_LOOKUPS=40_000


@dataclass(frozen=True)
class VerifiedReference:
    playlist_id: int
    asset_key: str
    source_key: str
    season: int
    episode: int
    kind: str
    start_ms: int
    end_ms: int
    duration_ms: int
    provenance: str

    @property
    def is_user_marker(self):
        return self.provenance == USER_PROVENANCE


def _columns(con,table):
    return {r[1] for r in con.execute("PRAGMA table_info("+table+")")}


def _schema(fb,prod):
    expected={
        "feedback_versions": {
            "marker_id","asset_key","playlist_id","season","episode","kind",
            "decision","active","start_ms","end_ms","provenance","reviewed_at"},
        "skip_assets": {
            "asset_key","playlist_id","source_key","season","episode","media_type",
            "duration_ms"},
    }
    for table,need in expected.items():
        con=fb if table=="feedback_versions" else prod
        if not need<=_columns(con,table):
            raise RuntimeError("STOP_UNRECOGNIZED_"+table.upper()+"_SCHEMA")


def _valid_marker(r,asset):
    dur=asset["duration_ms"]
    if (r["playlist_id"]!=asset["playlist_id"]
        or r["season"]!=asset["season"]
        or r["episode"]!=asset["episode"]
        or asset["media_type"]!="episode"):
        return False
    if (type(dur) is not int or type(r["start_ms"]) is not int
        or type(r["end_ms"]) is not int
        or not 0<=r["start_ms"]<r["end_ms"]<=dur):
        return False
    size=r["end_ms"]-r["start_ms"]
    max_size=(600_000 if r["kind"]=="intro" else
              900_000 if r["kind"]=="outro" else 180_000)
    return 1_000<=size<=max_size


def select_references(fb,prod):
    """Trust only current direct-device or admin-reviewed records.

    Suppress contradictory active positives and active negative/veto decisions
    for the same playlist/asset/kind. Never infer provenance from skip_records.
    Returns only exact-asset references; outside analysis playlists are reported
    for future identity reconciliation, not silently copied across playlists.
    """
    _schema(fb,prod)
    count=fb.execute("SELECT COUNT(*) FROM feedback_versions").fetchone()[0]
    if count>MAX_FEEDBACK_ROWS:
        raise RuntimeError("STOP_FEEDBACK_INVENTORY_TOO_LARGE")
    rows=fb.execute("""
      SELECT marker_id,asset_key,playlist_id,season,episode,kind,decision,
             active,start_ms,end_ms,provenance,reviewed_at
      FROM feedback_versions ORDER BY marker_id
    """).fetchall()
    counts=Counter()
    all_groups=defaultdict(list)
    for r in rows:
        counts["total_feedback_versions"]+=1
        if r["active"]!=1:
            counts["inactive_or_revoked"]+=1
            continue
        counts["active_feedback_versions"]+=1
        if r["kind"] not in KINDS:
            counts["unsupported_segment_type"]+=1
            continue
        if type(r["playlist_id"]) is not int or not isinstance(r["asset_key"],str):
            counts["invalid_identity"]+=1
            continue
        key=(r["playlist_id"],r["asset_key"],r["kind"])
        all_groups[key].append(r)
        if r["decision"]!="positive":
            counts["active_nonpositive"]+=1
    assets={}
    candidates=defaultdict(list)
    for key, versions in all_groups.items():
        positives=[r for r in versions if r["decision"]=="positive"]
        if not positives:
            continue
        # Any simultaneous active negative/correction or incompatible time
        # bounds must suppress the whole group, never silently pick a winner.
        if any(r["decision"]!="positive" for r in versions):
            counts["suppressed_active_negative_groups"]+=1
            continue
        authenticated=[r for r in positives if
                       r["provenance"] in TRUSTED_PROVENANCE and
                       isinstance(r["reviewed_at"],str) and r["reviewed_at"].strip()]
        counts["unauthenticated_positive_rows"]+=len(positives)-len(authenticated)
        if not authenticated:
            continue
        if len({(r["start_ms"],r["end_ms"]) for r in authenticated})!=1:
            counts["suppressed_conflicting_positive_groups"]+=1
            continue
        if key[1] not in assets:
            if len(assets)>=MAX_ASSET_LOOKUPS:
                raise RuntimeError("STOP_TOO_MANY_ASSET_LOOKUPS")
            assets[key[1]]=prod.execute(
                "SELECT * FROM skip_assets WHERE asset_key=? LIMIT 2",(key[1],)
            ).fetchall()
        found=assets[key[1]]
        if len(found)!=1:
            counts["missing_or_ambiguous_asset_groups"]+=1
            continue
        asset=found[0]
        if not asset["source_key"]:
            counts["missing_series_source_key"]+=1
            continue
        if not _valid_marker(authenticated[0],asset):
            counts["rejected_identity_or_bounds"]+=1
            continue
        provenance = (USER_PROVENANCE if any(
            r["provenance"]==USER_PROVENANCE for r in authenticated)
            else "admin_reviewed_machine")
        r=authenticated[0]
        ref=VerifiedReference(
            playlist_id=r["playlist_id"],
            asset_key=r["asset_key"],
            source_key=asset["source_key"],
            season=r["season"],
            episode=r["episode"],
            kind=r["kind"],
            start_ms=r["start_ms"],
            end_ms=r["end_ms"],
            duration_ms=asset["duration_ms"],
            provenance=provenance)
        candidates[key].append(ref)
        counts["authenticated_reference_groups"]+=1
        if ref.is_user_marker:
            counts["direct_user_reference_groups"]+=1
        else:
            counts["admin_reviewed_reference_groups"]+=1
        if ref.playlist_id in ANALYSIS_PLAYLISTS:
            counts["analysis_reference_groups"]+=1
        else:
            counts["other_playlist_reference_groups_identity_required"]+=1
    return [a for group in candidates.values() for a in group],counts


def summarize(references,counts,prod):
    """Bounded aggregated status only; never print asset IDs or names/URLs."""
    out=dict(sorted(counts.items()))
    # Stable zero fields: a complete veto must be visible as 0 rather than
    # masquerading as missing data or crashing audit consumers.
    for key in ("authenticated_reference_groups", "direct_user_reference_groups",
                "admin_reviewed_reference_groups", "analysis_reference_groups",
                "other_playlist_reference_groups_identity_required"):
        out.setdefault(key,0)
    per_playlist=Counter()
    per_kind=Counter()
    series=defaultdict(set)
    cached=Counter()
    cols=_columns(prod,"skip_auto_windows")
    can_check_cache={"asset_key","kind","duration_ms"}<=cols
    for a in references:
        pid="4K ANALYSE" if a.playlist_id==8 else (
            "THE BEST" if a.playlist_id==10 else "OTHER_PLAYLISTS")
        per_playlist[pid]+=1
        per_kind[a.kind]+=1
        series[pid].add((a.playlist_id,a.source_key))
        if can_check_cache and a.playlist_id in ANALYSIS_PLAYLISTS:
            exists=prod.execute("""SELECT 1 FROM skip_auto_windows
                 WHERE asset_key=? AND kind=? AND duration_ms=? LIMIT 1""",
                 (a.asset_key,a.kind,a.duration_ms)).fetchone()
            cached["cache_present" if exists else "cache_missing"]+=1
    out["by_playlist_group"]=dict(sorted(per_playlist.items()))
    out["by_segment"]=dict(sorted(per_kind.items()))
    out["distinct_series_by_group"]={x:len(y) for x,y in sorted(series.items())}
    out["analysis_reference_cache"]=dict(sorted(cached.items())) if can_check_cache else "UNKNOWN_SCHEMA"
    out["ready_for_automatic_release"]=False
    out["automatic_approvals_performed"]=0
    out["unverified_skip_records_are_not_counted_as_human_truth"]=True
    return out


def open_ro(path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("STOP_SOURCE_MISSING_OR_SYMLINK: "+path.name)
    con=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True,timeout=15)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA query_only=ON")
    return con


def run(feedback=FEEDBACK,production=PRODUCTION):
    with open_ro(feedback) as fb,open_ro(production) as prod:
        references,counts=select_references(fb,prod)
        return summarize(references,counts,prod)


if __name__=="__main__":
    print("EPISCENE AUTHENTIFIZIERTE MANUELLE REFERENZEN – READ ONLY")
    print("Historische Bestätigungen zählen; widerrufene und unsichere Marker nicht.")
    print(json.dumps(run(),ensure_ascii=False,indent=2))
