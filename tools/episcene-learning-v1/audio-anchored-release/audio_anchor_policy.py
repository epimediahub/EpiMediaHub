#!/usr/bin/env python3
"""EpiScene audio + manual anchor safety policy (SHADOW ONLY).

Pure function: does not read production files, change DB status, release
markers, restart workers or change an existing visual/audio gate. Before use
as an alternative gate, source-version proof and original release-path
integration must be tested separately against the installed server.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable

AUDIO_SOURCES = frozenset({'audio', 'audio_repetition', 'auto_audio', 'episcene'})
KINDS = frozenset({'intro', 'outro'})
MAX_BOUNDARY_ERROR_MS = 1500
MIN_PEER_EPISODES = 3
MIN_APPROVED_HUMAN_PEERS = 1


@dataclass(frozen=True)
class Evidence:
    asset_key: str
    playlist_id: int
    source_key: str
    season: int
    episode: int
    media_type: str
    kind: str
    source: str
    state: str
    start_ms: int
    end_ms: int
    duration_ms: int
    disabled: bool = False
    audio_confirmed: bool = False
    human_verified: bool = False
    visual_disagreement: bool = False
    visual_decision: str = ''


def valid(x: Evidence) -> bool:
    if x.playlist_id not in (8, 10) or x.media_type != 'episode' or x.kind not in KINDS:
        return False
    if not x.asset_key or not x.source_key or type(x.season) is not int or type(x.episode) is not int:
        return False
    if any(type(v) is not int for v in (x.start_ms, x.end_ms, x.duration_ms)):
        return False
    if x.duration_ms < 300_000 or x.disabled or not 0 <= x.start_ms < x.end_ms <= x.duration_ms:
        return False
    length = x.end_ms - x.start_ms
    max_length = 300_000 if x.kind == 'intro' else 900_000
    return 15_000 <= length <= max_length


def aligned(target: Evidence, peer: Evidence) -> bool:
    if not valid(peer):
        return False
    if (target.playlist_id, target.source_key, target.season, target.kind) != (
            peer.playlist_id, peer.source_key, peer.season, peer.kind):
        return False
    if target.episode == peer.episode or target.asset_key == peer.asset_key:
        return False
    if target.kind == 'intro':
        ta = (target.start_ms, target.end_ms)
        pa = (peer.start_ms, peer.end_ms)
    else:
        ta = (target.duration_ms - target.end_ms, target.duration_ms - target.start_ms)
        pa = (peer.duration_ms - peer.end_ms, peer.duration_ms - peer.start_ms)
    return max(abs(ta[0] - pa[0]), abs(ta[1] - pa[1])) <= MAX_BOUNDARY_ERROR_MS


def nominate(target: Evidence, peers: Iterable[Evidence], *, blocked: bool = False,
             owner_correction_pending: bool = False,
             source_version_current: bool = False) -> str:
    """Return SHADOW_ELIGIBLE_NOT_RELEASED, never permission to approve.

    source_version_current must come from the original trusted server check;
    absent an independent check, default to rejecting.
    """
    if not valid(target) or target.state != 'pending' or target.source not in AUDIO_SOURCES:
        return 'INVALID_TARGET'
    if not target.audio_confirmed:
        return 'AUDIO_NOT_CONFIRMED'
    if blocked or owner_correction_pending or target.disabled:
        return 'BLOCKED_OR_HUMAN_CORRECTION'
    if target.visual_disagreement or target.visual_decision in ('NO_MATCH', 'REVIEW', 'rejected'):
        return 'CONTRADICTING_VISUAL'
    if not source_version_current:
        return 'SOURCE_REVISION_NOT_VERIFIED'

    peer_audio: set[int] = set()
    human: set[int] = set()
    conflicting_peer: set[int] = set()
    for peer in peers:
        if not valid(peer):
            continue
        if (peer.playlist_id, peer.source_key, peer.season, peer.kind) != (
                target.playlist_id, target.source_key, target.season, target.kind):
            continue
        if peer.episode == target.episode or peer.asset_key == target.asset_key:
            continue
        if peer.visual_disagreement or peer.visual_decision in ('NO_MATCH', 'rejected'):
            continue
        human_proof = (peer.source == 'device' and peer.state == 'approved'
                       and peer.human_verified)
        audio_proof = (peer.source in AUDIO_SOURCES and peer.state in ('pending', 'approved')
                       and peer.audio_confirmed)
        if not (human_proof or audio_proof):
            continue
        if aligned(target, peer):
            if human_proof:
                human.add(peer.episode)
            if audio_proof:
                peer_audio.add(peer.episode)
        else:
            conflicting_peer.add(peer.episode)
    if conflicting_peer:
        return 'CONFLICTING_EPISODES'
    if len(human) < MIN_APPROVED_HUMAN_PEERS:
        return 'NO_MATCHING_HUMAN_ANCHOR'
    if len(peer_audio) < MIN_PEER_EPISODES:
        return 'INSUFFICIENT_INDEPENDENT_AUDIO_PEERS'
    return 'SHADOW_ELIGIBLE_NOT_RELEASED'


if __name__ == '__main__':
    raise SystemExit('SHADOW library only. Do not run as a production release action.')
