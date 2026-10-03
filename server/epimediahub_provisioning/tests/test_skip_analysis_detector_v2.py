"""V2 precision, independent consensus and real worker/release regressions."""
import contextlib
import json
from pathlib import Path
import random
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from skip_detector_v2 import Config, IntroOutroDetectorV2, MarkerType, Status, POLICY
from test_skip_analysis_automation import AutomationFixture
import test_skip_analysis_boundaries as boundary_tests
from skip_analysis import fingerprint, probe, run
from skip_markers import add_record, now, review_record
from skip_release import accept_pending, approve_scope
from skip_analysis_worker import busy_check, process_one
import skip_automation as auto


class DetectorTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(9881)
        self.detector = IntroOutroDetectorV2(Config(item_duration_sec=.125))

    def words(self, n):
        return [self.rng.getrandbits(32) for _ in range(n)]

    def episodes(self, count=5, noise=0):
        shared = self.words(220)
        return [self.words(100 + i * 31) + [w ^ noise for w in shared] + self.words(80) for i in range(count)]

    def test_shifted_titles_get_individual_boundaries_and_three_independent_partners(self):
        for i, result in self.detector.detect_all(self.episodes(), MarkerType.INTRO).items():
            self.assertEqual(result.status, Status.AUTO_CONFIRMED)
            self.assertEqual(result.segment.start, (100 + i * 31) * .125)
            self.assertEqual(result.segment.length, 27.5)
            self.assertEqual(result.support, 4)
            self.assertNotIn(i, result.supported_partners)

    def test_two_partners_stay_review_and_stable_encoding_bit_difference_is_found(self):
        fps = self.episodes(3)
        fps[1] = [w ^ 0xF0000000 for w in fps[1]]
        result = self.detector.detect_for_episode(0, fps, MarkerType.INTRO)
        self.assertEqual(result.status, Status.REVIEW)
        self.assertEqual(result.support, 2)
        self.assertGreater(result.min_match_ratio, .99)

    def test_signed_kotlin_words_and_exclusive_end_are_handled(self):
        fps = self.episodes(4)
        fps[1] = [w if w < 2**31 else w - 2**32 for w in fps[1]]
        match = self.detector.find_pair_candidate(fps[0], fps[1], MarkerType.INTRO)
        self.assertEqual(match.segment.end, 40.0)
        self.assertEqual(match.partner_segment.start, 131 * .125)

    def test_silence_tiny_loops_unrelated_music_and_sparse_matches_are_rejected(self):
        self.assertIsNone(self.detector.find_pair_candidate([0] * 5800, [0] * 5800, MarkerType.INTRO))
        self.assertIsNone(self.detector.find_pair_candidate(list(range(8)) * 80, list(range(8)) * 80, MarkerType.INTRO))
        self.assertIsNone(self.detector.find_pair_candidate(self.words(5800), self.words(5800), MarkerType.INTRO))
        a = self.words(220)
        b = [w if i % 9 == 0 else w ^ 0xFFFFFFFF for i, w in enumerate(a)]
        self.assertIsNone(self.detector.find_pair_candidate(a, b, MarkerType.INTRO))

    def test_overlong_scene_is_rejected_without_hiding_a_later_valid_title(self):
        scene, title = self.words(1050), self.words(220)
        a = scene + self.words(50) + title + self.words(50)
        b = scene + self.words(50) + title + self.words(50)
        match = self.detector.find_pair_candidate(a, b, MarkerType.INTRO)
        self.assertIsNotNone(match)
        self.assertEqual(match.segment.start, 137.5)
        self.assertEqual(match.segment.length, 27.5)
        self.assertIsNone(self.detector.find_pair_candidate(scene, scene, MarkerType.INTRO))

    def test_multiple_comparable_occurrences_in_either_file_are_ambiguous(self):
        title = self.words(220)
        once = self.words(100) + title + self.words(80)
        twice = self.words(100) + title + self.words(100) + title + self.words(80)
        self.assertIsNone(self.detector.find_pair_candidate(once, twice, MarkerType.INTRO))
        self.assertIsNone(self.detector.find_pair_candidate(twice, once, MarkerType.INTRO))

    def test_equal_competing_consensus_clusters_are_rejected(self):
        first, second = self.words(220), self.words(220)
        target = self.words(100) + first + self.words(100) + second + self.words(80)
        fps = [target, self.words(100) + first, self.words(120) + first,
               self.words(100) + second, self.words(120) + second]
        self.assertEqual(self.detector.detect_for_episode(0, fps, MarkerType.INTRO).status, Status.REJECTED)

    def test_small_gaps_are_tolerated_but_boundary_disagreement_stays_review(self):
        fps = self.episodes(4)
        for i in (1, 2, 3):
            begin = 100 + i * 31 + 100
            for j in range(begin, begin + 5):
                fps[i][j] ^= 0xFFFFFFFF
        result = self.detector.detect_for_episode(0, fps, MarkerType.INTRO)
        self.assertEqual(result.status, Status.AUTO_CONFIRMED)
        # One episode cuts off several seconds of the shared opening.
        fps[3][193:213] = self.words(20)
        result = self.detector.detect_for_episode(0, fps, MarkerType.INTRO)
        self.assertEqual(result.status, Status.REVIEW)
        self.assertGreater(result.boundary_spread_sec, 1)

    def test_busy_playback_interrupts_and_pair_work_is_bounded_by_top_offsets(self):
        fps = self.episodes(4)
        with self.assertRaisesRegex(ValueError, 'analysis_deferred'):
            IntroOutroDetectorV2(busy=lambda: True).detect_for_episode(0, fps, MarkerType.INTRO)
        title = self.words(400)
        a = self.words(2600) + title + self.words(2800)
        b = self.words(3100) + title + self.words(2300)
        with mock.patch.object(self.detector, '_ham', wraps=self.detector._ham) as hamming:
            self.assertIsNotNone(self.detector.find_pair_candidate(a, b, MarkerType.INTRO))
            self.assertLess(hamming.call_count, 12 * 5800 + 2000)

    def test_outro_uses_tail_window_and_invalid_inputs_do_not_match(self):
        fps = self.episodes(4)
        result = self.detector.detect_for_episode(0, fps, MarkerType.OUTRO)
        self.assertEqual(result.status, Status.AUTO_CONFIRMED)
        for bad in ([True] * 200, ['1'] * 200, [2**32] * 200, [0] * 36001):
            self.assertIsNone(self.detector.find_pair_candidate(bad, fps[0], MarkerType.INTRO))
        with self.assertRaisesRegex(ValueError, 'configuration'):
            IntroOutroDetectorV2(Config(item_duration_sec=float('nan')))


class IntegrationTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with self.db() as con:
            con.execute('DELETE FROM skip_release_settings')

    def cached(self, count=4, kind='intro', start_episode=12):
        rng = random.Random(3307)
        shared = [rng.getrandbits(32) for _ in range(220)]
        items = []
        for i in range(count):
            item = self.descriptor(str(81+i), start_episode+i)
            self.registered(item); items.append(item)
            words = [rng.getrandbits(32) for _ in range(200+i*40)] + shared + [rng.getrandbits(32) for _ in range(80)]
            offset = 0 if kind == 'intro' else item['duration_ms'] - (len(words) * 125 + 1500)
            with self.db() as con:
                auto.save_window(con, item, kind, words, 125, offset, len(words)*125+1500)
        return items

    def test_review_is_not_automatically_accepted_or_bypassed_and_bulk_approval_works(self):
        items = self.cached(3)
        with self.db() as con:
            auto.store_proposal(con, items[0], 'intro', 25000, 52500, 'audio', .80)
            self.assertTrue(auto.bootstrap(con, items[0], 'intro'))
            self.assertEqual(accept_pending(con), 0)
            row = con.execute("SELECT r.*,e.evidence_json FROM skip_records r JOIN skip_auto_evidence e ON e.record_id=r.id WHERE r.status='pending'").fetchone()
            self.assertEqual(json.loads(row['evidence_json'])['status'], 'REVIEW')
            self.assertEqual(approve_scope(con, items[0]['source_key'], items[0]['season'])['approved'], 1)

    def test_four_independent_episodes_autoapprove_once_then_user_correction_wins(self):
        items = self.cached()
        with self.db() as con:
            self.assertTrue(auto.bootstrap(con, items[0], 'intro'))
            self.assertEqual(accept_pending(con), 1)
            self.assertEqual(accept_pending(con), 0)
            row = con.execute("SELECT * FROM skip_records WHERE status='approved'").fetchone()
            review_record(con, row, 'approve', 26000, 53000, False)
            self.assertFalse(auto.bootstrap(con, items[0], 'intro'))
            self.assertEqual(con.execute('SELECT start_ms,end_ms FROM skip_records WHERE id=?', (row['id'],)).fetchone()[:], (26000,53000))

    def test_stale_donor_duplicate_episode_and_short_coverage_cannot_create_quorum(self):
        for change in ("UPDATE skip_assets SET duration_ms=duration_ms+10000 WHERE episode=15",
                       "UPDATE skip_assets SET episode=14 WHERE episode=15",
                       "UPDATE skip_auto_windows SET length_ms=15000 WHERE asset_key IN (SELECT asset_key FROM skip_assets WHERE episode=15)"):
            items = self.cached()
            with self.db() as con:
                con.execute(change)
                self.assertTrue(auto.bootstrap(con, items[0], 'intro'))
                self.assertEqual(accept_pending(con), 0)
                con.execute('DELETE FROM skip_records')
                con.execute('DELETE FROM skip_auto_windows')

    def test_changed_donor_during_release_is_not_published(self):
        items = self.cached()
        with self.db() as con:
            self.assertTrue(auto.bootstrap(con, items[0], 'intro'))
            con.execute('UPDATE skip_assets SET episode=99 WHERE asset_key=?', (items[-1]['asset_key'],))
            self.assertEqual(accept_pending(con), 0)

    def test_withdrawn_donor_does_not_authorize_other_episodes(self):
        items = self.cached()
        with self.db() as con:
            self.assertTrue(auto.bootstrap(con, items[0], 'intro'))
            con.execute('INSERT INTO skip_auto_blocks VALUES(?,?,?,?)', (items[-1]['asset_key'],'intro',items[-1]['duration_ms'],now()))
            self.assertEqual(accept_pending(con), 0)
            self.assertTrue(auto.bootstrap(con, items[0], 'intro'))
            self.assertEqual(accept_pending(con), 0)

    def test_new_partner_refreshes_earlier_cached_episodes_without_decoding(self):
        items = self.cached()
        with mock.patch.object(auto, 'fingerprint', side_effect=AssertionError('no audio decode')):
            auto.refresh_neighbour_consensus(self.db, items[-1], 'intro')
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE status='approved'").fetchone()[0], 3)

    def test_actual_worker_path_uses_current_fft_detector_and_twelve_minute_windows_with_existing_budget(self):
        items = self.cached()
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='no_match'")
            con.execute("UPDATE skip_jobs SET status='queued' WHERE asset_key=?", (items[0]['asset_key'],))
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,10)', (now()[:10],))
            own = con.execute('SELECT * FROM skip_auto_windows WHERE asset_key=?', (items[0]['asset_key'],)).fetchone()
        target = json.loads(own['words_json'])
        def fp(source, offset, length, busy, **kwargs):
            self.assertEqual(length, 720000)
            return (target if offset == 0 else [0]*600), 125, length
        with mock.patch.object(auto, 'discover_one', return_value='idle'), \
             mock.patch.object(auto, 'provider_proxy', side_effect=lambda *_: contextlib.nullcontext('fixture')), \
             mock.patch.object(auto, 'probe', return_value=(items[0]['duration_ms'], [])), \
             mock.patch.object(auto, 'fingerprint', side_effect=fp):
            self.assertEqual(process_one(self.db), 'done')
        with self.db() as con:
            row = con.execute("SELECT r.*,e.evidence_json FROM skip_records r JOIN skip_auto_evidence e ON e.record_id=r.id WHERE r.asset_key=? AND r.status='approved'", (items[0]['asset_key'],)).fetchone()
            self.assertEqual(json.loads(row['evidence_json'])['policy'], auto.DETECTOR_POLICY)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 11)

    def test_outro_offsets_are_per_episode_and_migration_preserves_limits_and_decisions(self):
        items = self.cached(kind='outro')
        with self.db() as con:
            self.assertTrue(auto.bootstrap(con, items[0], 'outro'))
            self.assertEqual(accept_pending(con), 1)
            row = con.execute("SELECT * FROM skip_records WHERE status='approved'").fetchone()
            self.assertLessEqual(items[0]['duration_ms'] - row['end_ms'], 15000)
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,24)', (now()[:10],))
            record = add_record(con, items[1], 'intro', 10000, 40000, False, self.device)
            review_record(con, con.execute('SELECT * FROM skip_records WHERE id=?', (record['id'],)).fetchone(), 'reject', 10000,40000,False)
            # V3 revisits both kinds. Protect the other kind as well so a
            # rejected intro does not hide legitimate unfinished outro work.
            con.execute('INSERT INTO skip_auto_blocks VALUES(?,?,?,?)',
                        (items[1]['asset_key'], 'outro', items[1]['duration_ms'], now()))
            con.execute("UPDATE skip_jobs SET status='no_match',attempts=3")
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?', (auto.DETECTOR_POLICY,))
            auto.migrate_detector(con)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 24)
            self.assertEqual(con.execute('SELECT status FROM skip_jobs WHERE asset_key=?', (items[1]['asset_key'],)).fetchone()[0], 'no_match')
            self.assertEqual(con.execute('SELECT status FROM skip_jobs WHERE asset_key=?', (items[0]['asset_key'],)).fetchone()[0], 'queued')
            con.execute("UPDATE skip_jobs SET status='done'")
            auto.migrate_detector(con)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0], 0)


class RealAudioTests(AutomationFixture, unittest.TestCase):
    rate = boundary_tests.RealBoundaryTests.rate
    clip = boundary_tests.RealBoundaryTests.clip

    def setUp(self):
        super().setUp()
        with self.db() as con:
            con.execute('DELETE FROM skip_release_settings')

    @classmethod
    def setUpClass(cls):
        boundary_tests.RealBoundaryTests.setUpClass()
        cls.music = boundary_tests.RealBoundaryTests.music

    def test_actual_chromaprint_boundary_disagreement_is_not_published_automatically(self):
        items = []
        for i, (prefix, gain) in enumerate(((0,1), (6000,.8), (12000,.65), (18000,.9))):
            path = self.clip(f'episode{i}.wav', prefix, gain)
            if i == 2:
                encoded = Path(self.temp.name) / 'episode2.m4a'
                run(['ffmpeg','-nostdin','-v','error','-threads','1','-i',str(path),'-c:a','aac','-b:a','96k',str(encoded)], timeout=20)
                path = encoded
            duration = probe(str(path))[0]
            item = self.descriptor(str(81+i), 12+i, duration_ms=duration)
            self.registered(item); items.append(item)
            words, step, coverage = fingerprint(str(path), 0, duration, with_coverage=True)
            with self.db() as con:
                auto.save_window(con, item, 'intro', words, step, 0, round(coverage))
        with self.db() as con:
            self.assertTrue(auto.bootstrap(con, items[2], 'intro'))
            # The former V2 fixture has identical silence at the file boundary.
            # V3 finds shared music but the measured boundary disagreement is
            # too large for publication. Keep the stricter release safeguard.
            self.assertEqual(accept_pending(con), 0)
            row = con.execute("SELECT r.status,e.evidence_json FROM skip_records r JOIN skip_auto_evidence e ON e.record_id=r.id").fetchone()
            self.assertEqual(row['status'], 'pending')
            self.assertGreater(json.loads(row['evidence_json'])['boundary_spread_sec'], 2.0)


if __name__ == '__main__':
    unittest.main()
