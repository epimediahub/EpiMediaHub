"""Synthetic safety tests for the shadow-only manual-anchored audio policy."""
from dataclasses import replace
import unittest
from audio_anchor_policy import Evidence, aligned, nominate


def row(episode, *, source='audio', state='pending', human=False,
        kind='intro', start_ms=40000, end_ms=62000,
        duration_ms=2_400_000, **kwargs):
    if kind == 'outro' and (start_ms, end_ms) == (40000, 62000):
        start_ms, end_ms = duration_ms - 63000, duration_ms - 41000
    return Evidence(
        asset_key=f'asset-{episode}', playlist_id=8, source_key='series-1',
        season=1, episode=episode, media_type='episode', kind=kind,
        source=source, state=state, start_ms=start_ms, end_ms=end_ms,
        duration_ms=duration_ms, human_verified=human,
        audio_confirmed=(source != 'device'), **kwargs)


class AnchorTests(unittest.TestCase):
    def setUp(self):
        self.target = row(1)
        self.peers = [
            row(2), row(3), row(4),
            row(5, source='device', state='approved', human=True),
        ]

    def call(self, target=None, peers=None, **kwargs):
        return nominate(target or self.target, self.peers if peers is None else peers,
                        source_version_current=True, **kwargs)

    def test_shadow_candidate_never_means_approved(self):
        self.assertEqual(self.call(), 'SHADOW_ELIGIBLE_NOT_RELEASED')

    def test_missing_current_version_is_rejected(self):
        self.assertEqual(nominate(self.target, self.peers), 'SOURCE_REVISION_NOT_VERIFIED')

    def test_missing_manual_anchor_is_rejected(self):
        self.assertEqual(self.call(peers=self.peers[:-1]), 'NO_MATCHING_HUMAN_ANCHOR')

    def test_repeated_same_episode_is_not_an_independent_peer(self):
        peers = [self.peers[0], self.peers[0], self.peers[1], self.peers[3]]
        self.assertEqual(self.call(peers=peers), 'INSUFFICIENT_INDEPENDENT_AUDIO_PEERS')

    def test_conflicting_peer_vetoes(self):
        peers = self.peers + [row(7, start_ms=60000, end_ms=80000)]
        self.assertEqual(self.call(peers=peers), 'CONFLICTING_EPISODES')

    def test_unverified_manual_reference_is_not_a_proof(self):
        peers = self.peers[:-1] + [replace(self.peers[-1], human_verified=False)]
        self.assertEqual(self.call(peers=peers), 'NO_MATCHING_HUMAN_ANCHOR')

    def test_visual_no_match_blocks(self):
        t = replace(self.target, visual_decision='NO_MATCH')
        self.assertEqual(self.call(target=t), 'CONTRADICTING_VISUAL')

    def test_visual_disagreement_blocks(self):
        t = replace(self.target, visual_disagreement=True)
        self.assertEqual(self.call(target=t), 'CONTRADICTING_VISUAL')

    def test_pending_human_correction_blocks(self):
        self.assertEqual(self.call(owner_correction_pending=True),
                         'BLOCKED_OR_HUMAN_CORRECTION')

    def test_explicit_block_blocks(self):
        self.assertEqual(self.call(blocked=True), 'BLOCKED_OR_HUMAN_CORRECTION')

    def test_cross_series_manual_anchor_does_not_count(self):
        peers = self.peers[:-1] + [replace(self.peers[-1], source_key='other')]
        self.assertEqual(self.call(peers=peers), 'NO_MATCHING_HUMAN_ANCHOR')

    def test_cross_playlist_audio_peers_do_not_count(self):
        peers = [replace(x, playlist_id=10) if x.source != 'device' else x
                 for x in self.peers]
        self.assertEqual(self.call(peers=peers), 'INSUFFICIENT_INDEPENDENT_AUDIO_PEERS')

    def test_outro_uses_position_relative_to_episode_end(self):
        target = row(1, kind='outro')
        peers = [row(i, kind='outro', duration_ms=2_400_000 + i * 60_000)
                 for i in (2, 3, 4)]
        peers.append(row(5, kind='outro', duration_ms=2_500_000,
                         source='device', state='approved', human=True))
        self.assertTrue(all(aligned(target, p) for p in peers))
        self.assertEqual(self.call(target=target, peers=peers),
                         'SHADOW_ELIGIBLE_NOT_RELEASED')

    def test_invalid_bounds_are_rejected(self):
        self.assertEqual(self.call(target=replace(self.target, end_ms=50)),
                         'INVALID_TARGET')

    def test_chapter_or_web_hint_is_not_audio_evidence(self):
        self.assertEqual(self.call(target=replace(self.target, source='chapter')),
                         'INVALID_TARGET')

    def test_only_known_visual_decisions_permitted(self):
        self.assertEqual(self.call(target=replace(self.target, visual_decision='REVIEW')),
                         'CONTRADICTING_VISUAL')


if __name__ == '__main__':
    unittest.main()
