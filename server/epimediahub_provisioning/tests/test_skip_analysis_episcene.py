"""EpiScene visual precision, independent evidence and durable corrections."""
import copy
import json
import random
import sys
import time
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import skip_scene as scene
import skip_visual as visual
import skip_automation as auto
import skip_release as release
import skip_remote_client as remote
from skip_markers import now
from test_skip_analysis_automation import AutomationFixture


def pixel_frames(seed, count):
    rng = np.random.default_rng(seed)
    small = rng.integers(15, 235, (count, 8, 8), dtype=np.uint8)
    return np.repeat(np.repeat(small, 4, axis=1), 4, axis=2)


def sequence(seed, start=30, shared=None, trusted=False, episode=None):
    frames = visual.hashes(pixel_frames(seed, 180))
    common = shared if shared is not None else visual.hashes(pixel_frames(4817, 48))
    frames[start:start + len(common)] = copy.deepcopy(common)
    bounds = [[start * 500, (start + len(common)) * 500]] if trusted else []
    return visual.VisualWindow(frames, 0, 500, 90000, 2_640_325,
                              f'{seed:064x}', episode or seed, bounds)


class VisualPrecisionTests(unittest.TestCase):
    def test_one_human_reference_recognizes_changed_sound_without_using_audio(self):
        target, ref = sequence(13, 40), sequence(12, 28, trusted=True)
        result = visual.detect(target, [ref], 'intro')
        self.assertEqual(result['status'], 'AUTO_CONFIRMED')
        self.assertEqual((result['start_ms'], result['end_ms']), (20000, 43750))
        visual.validate_result(result, target, [ref], 'intro')

    def test_three_independent_partners_are_required_without_human_reference(self):
        target = sequence(13)
        refs = [sequence(episode, 20 + episode) for episode in (10, 11, 12)]
        self.assertEqual(visual.detect(target, refs[:2], 'intro')['status'], 'REVIEW')
        result = visual.detect(target, refs, 'intro')
        self.assertEqual(result['status'], 'AUTO_CONFIRMED')
        self.assertEqual(result['support'], 3)
        visual.validate_result(result, target, refs, 'intro')

    def test_duplicate_files_or_same_episode_do_not_inflate_support(self):
        target, ref = sequence(13), sequence(12)
        copies = [copy.deepcopy(ref) for _ in range(3)]
        for i, item in enumerate(copies):
            item.episode_id = str(i)
        result = visual.detect(target, copies, 'intro')
        self.assertEqual(result['support'], 1)
        self.assertEqual(result['status'], 'REVIEW')
        copies[0].episode = target.episode
        self.assertEqual(visual.detect(target, copies[:1], 'intro')['status'], 'NO_MATCH')

    def test_black_and_static_high_contrast_logos_cannot_authorize_skip(self):
        for pixels in (np.zeros((180, 32, 32), dtype=np.uint8),
                       np.repeat(pixel_frames(51, 1), 180, axis=0)):
            frames = visual.hashes(pixels)
            target = visual.VisualWindow(frames, 0, 500, 90000, 2_640_325, 'target', 5)
            refs = [visual.VisualWindow(copy.deepcopy(frames), 0, 500, 90000, 2_640_325, str(i), i) for i in (1,2,3)]
            self.assertEqual(visual.detect(target, refs, 'intro')['status'], 'NO_MATCH')

    def test_two_plausible_positions_require_review(self):
        target, ref = sequence(13, 20), sequence(12, 30, trusted=True)
        target.frames[100:148] = copy.deepcopy(target.frames[20:68])
        result = visual.detect(target, [ref], 'intro')
        self.assertTrue(result['ambiguous'])
        self.assertEqual(result['status'], 'REVIEW')

    def test_same_room_with_minor_face_changes_is_not_visual_only_intro_evidence(self):
        rng=random.Random(71);base=rng.getrandbits(63)
        common=[[base ^ rng.getrandbits(9),rng.getrandbits(64),35,120] for _ in range(48)]
        target=sequence(13,30,shared=common)
        refs=[sequence(i,20+i,shared=common) for i in (10,11,12)]
        self.assertEqual(visual.detect(target,refs,'intro')['status'],'NO_MATCH')

    def test_matching_prefix_clipped_at_window_end_is_not_auto_confirmed(self):
        target = sequence(13, 132)
        refs = [sequence(i, 20) for i in (10,11,12)]
        result = visual.detect(target, refs, 'intro')
        self.assertEqual(result['status'], 'REVIEW')
        self.assertFalse(result['boundaries_confirmed'])

    def test_post_credit_scene_is_retained(self):
        target = sequence(13, 60)
        target.offset_ms = target.duration_ms - 90000
        refs = [sequence(i, 20) for i in (10,11,12)]
        for ref in refs:
            ref.offset_ms = ref.duration_ms - 90000
        result = visual.detect(target, refs, 'outro')
        self.assertEqual(result['status'], 'REVIEW')
        self.assertLess(result['end_ms'], target.duration_ms - 10000)

    def test_perceptual_hash_survives_brightness_change_and_small_pixel_noise(self):
        reference = pixel_frames(7, 48)
        noisy = np.clip(reference.astype(int) + 8 + np.random.default_rng(90).integers(-2, 3, reference.shape), 0,255).astype(np.uint8)
        left, right = visual.hashes(reference), visual.hashes(noisy)
        distances = [(a[0] ^ b[0]).bit_count() + (a[1] ^ b[1]).bit_count() for a,b in zip(left,right)]
        self.assertLess(sum(distances) / len(distances), 3)

    def test_cache_is_bounded_and_changes_in_pixels_or_reference_bounds_invalidate_it(self):
        cache = visual.VisualCache(capacity=2)
        target, ref = sequence(13), sequence(12, trusted=True)
        visual.detect(target, [ref], 'intro', cache=cache)
        visual.detect(target, [ref], 'intro', cache=cache)
        self.assertEqual(cache.hits, 1)
        ref.trusted_ranges[0][0] += 500
        visual.detect(target, [ref], 'intro', cache=cache)
        ref.frames[0][0] ^= 31
        visual.detect(target, [ref], 'intro', cache=cache)
        self.assertEqual(cache.stats()['pairs'], 2)
        self.assertEqual(cache.misses, 3)

    def test_rpc_result_cannot_claim_fake_partner_or_out_of_window_boundary(self):
        target, ref = sequence(13), sequence(12, trusted=True)
        result = visual.detect(target, [ref], 'intro')
        for field, value in (('support', 4), ('start_ms', 90001), ('confidence', float('nan'))):
            bad = copy.deepcopy(result); bad[field] = value
            with self.assertRaises(ValueError):
                visual.validate_result(bad, target, [ref], 'intro')
        bad = copy.deepcopy(result); bad['matches'][0]['partner'] = 'another-file'
        with self.assertRaises(ValueError):
            visual.validate_result(bad, target, [ref], 'intro')

    def test_cancel_before_cache_hit_and_during_comparison(self):
        target, ref = sequence(13), sequence(12)
        cache = visual.VisualCache()
        visual.detect(target, [ref], 'intro', cache=cache)
        with self.assertRaisesRegex(ValueError, 'analysis_deferred'):
            visual.detect(target, [ref], 'intro', busy=lambda: True, cache=cache)


class ScenePublicationTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registered(self.target)
        with self.db() as con:
            con.execute("UPDATE skip_release_settings SET enabled=1")
            con.execute("INSERT INTO skip_auto_metadata_config VALUES('episcene_enabled','1',?)", (now(),))
        patch = mock.patch.object(remote, 'visual_detect', side_effect=lambda t,p,k,b: visual.detect(t,p,k,b))
        patch.start(); self.addCleanup(patch.stop)

    def add_window(self, data, start=30):
        self.registered(data)
        window = sequence(data['episode'], start)
        with self.db() as con:
            row = scene._save(con, data, 'intro', 0, 90000, window.frames)
        return row

    def test_new_audio_proposal_is_held_until_visual_stage_supplies_evidence(self):
        with self.db() as con:
            row = auto.store_proposal(con, self.target, 'intro', 20000, 45000, 'audio', .99)
            self.assertTrue(json.loads(row['evidence_json'])['episcene_required'])
            self.assertEqual(release.accept_pending(con), 0)
            self.assertEqual(con.execute('SELECT status FROM skip_records').fetchone()[0], 'pending')

    def test_three_visual_neighbours_publish_and_cached_refresh_finishes_earlier_episodes(self):
        own = self.add_window(self.target)
        partners = []
        for episode in (10,11,12):
            data = self.descriptor(str(100+episode), episode)
            partners.append((self.add_window(data, 20+episode), data))
        outcome = scene._compare(self.db, self.target, 'intro', own, partners, lambda: False)
        self.assertEqual(outcome['approvals'], 1)
        with self.db() as con:
            result = con.execute("SELECT * FROM skip_records WHERE asset_key=?", (self.target['asset_key'],)).fetchone()
            self.assertEqual((result['source'],result['status']), ('episcene','approved'))
        with mock.patch.object(auto, 'provider_proxy', side_effect=AssertionError('No provider in cache refresh')):
            scene.refresh_neighbours(self.db, self.target, 'intro', lambda: False)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE status='approved'").fetchone()[0], 4)

    def pending_evidence(self):
        with self.db() as con:
            con.execute('UPDATE skip_release_settings SET enabled=0')
        own = self.add_window(self.target)
        partners = []
        for episode in (10,11,12):
            data = self.descriptor(str(100+episode), episode)
            partners.append((self.add_window(data, 20+episode), data))
        scene._compare(self.db, self.target, 'intro', own, partners, lambda: False)
        with self.db() as con:
            con.execute('UPDATE skip_release_settings SET enabled=1')
        return partners

    def test_changed_pixels_runtime_or_disabled_provider_invalidate_pending_evidence(self):
        partners = self.pending_evidence()
        with self.db() as con:
            original = con.execute('SELECT frames_json FROM skip_scene_windows WHERE id=?', (partners[0][0]['id'],)).fetchone()[0]
            con.execute("UPDATE skip_scene_windows SET frames_json='[]' WHERE id=?", (partners[0][0]['id'],))
            self.assertEqual(release.accept_pending(con), 0)
            con.execute('UPDATE skip_scene_windows SET frames_json=? WHERE id=?', (original,partners[0][0]['id']))
            con.execute('UPDATE skip_assets SET duration_ms=duration_ms+500 WHERE asset_key=?', (partners[0][1]['asset_key'],))
            self.assertEqual(release.accept_pending(con), 0)
            con.execute('UPDATE skip_assets SET duration_ms=duration_ms-500 WHERE asset_key=?', (partners[0][1]['asset_key'],))
            con.execute('UPDATE skip_analysis_sources SET enabled=0')
            self.assertEqual(release.accept_pending(con), 0)

    def test_visual_disagreement_retains_audio_for_manual_review(self):
        vote = self.voted(9, '99')
        with self.db() as con:
            auto.store_proposal(con, self.target, 'intro', 48000, 74530, 'audio', .95,
                                dict(method='reviewed_audio_match',vote=vote))
        own = self.add_window(self.target)
        partners = []
        for episode in (10,11,12):
            data = self.descriptor(str(100+episode), episode)
            partners.append((self.add_window(data, 20+episode),data))
        outcome = scene._compare(self.db, self.target, 'intro', own, partners, lambda: False)
        self.assertEqual(outcome['approvals'], 0)
        self.assertTrue(outcome['disagreement'])
        repeated=scene._compare(self.db,self.target,'intro',own,partners,lambda:False)
        self.assertEqual(repeated['approvals'],0)
        self.assertTrue(repeated['disagreement'])
        with self.db() as con:
            self.assertEqual(release.accept_pending(con), 0)
            self.assertFalse(con.execute("SELECT 1 FROM skip_records WHERE asset_key=? AND status='approved'", (self.target['asset_key'],)).fetchone())

    def test_human_correction_is_not_overwritten_by_visual_consensus(self):
        own = self.add_window(self.target)
        self.marker(self.target)
        partners = []
        for episode in (10,11,12):
            data = self.descriptor(str(100+episode), episode)
            partners.append((self.add_window(data,20+episode),data))
        outcome = scene._compare(self.db, self.target, 'intro', own, partners, lambda: False)
        self.assertEqual(outcome['approvals'], 0)
        with self.db() as con:
            self.assertEqual(con.execute('SELECT start_ms,end_ms,source FROM skip_records').fetchone()[:], (283043,309573,'device'))

    def test_cache_chunks_resume_without_provider_and_preserve_absolute_time_grid(self):
        frames = visual.hashes(pixel_frames(5, 180))
        with self.db() as con:
            scene._save(con,self.target,'intro',0,60000,frames[:120])
            scene._save(con,self.target,'intro',60000,30000,frames[120:])
        with mock.patch('skip_analysis.provider_proxy',side_effect=AssertionError('No provider on cache hit')):
            row = scene.capture(self.db,self.target,'intro',0,90000,lambda:False)
        self.assertEqual(json.loads(row['frames_json']),frames)

    def test_visual_cache_contains_no_provider_credentials_and_expires(self):
        row = self.add_window(self.target)
        self.assertNotIn('TEST_PROVIDER_SECRET',row['frames_json'])
        self.assertNotIn('http',row['frames_json'])
        with self.db() as con:
            con.execute('UPDATE skip_scene_windows SET created_at=?',(int(time.time())-scene.CACHE_SECONDS-1,))
            self.assertIsNone(scene._cache(con,self.target,'intro',0,90000))

    def human_visual_pair(self):
        vote=self.voted(12,'112')
        reference=self.descriptor('112',12)
        common=visual.hashes(pixel_frames(4817,53))
        target_frames=visual.hashes(pixel_frames(13,180));target_frames[96:149]=copy.deepcopy(common)
        reference_frames=visual.hashes(pixel_frames(12,720));reference_frames[566:619]=copy.deepcopy(common)
        with self.db() as con:
            own=scene._save(con,self.target,'intro',0,90000,target_frames)
            ref=scene._save(con,reference,'intro',0,360000,reference_frames)
        return vote,reference,own,ref

    def test_audio_and_visual_evidence_can_merge_the_same_pending_row_and_publish(self):
        vote,reference,own,ref=self.human_visual_pair()
        with self.db() as con:
            original=auto.store_proposal(con,self.target,'intro',48000,74530,'audio',.95,
                                        dict(method='reviewed_audio_match',vote=vote))
        outcome=scene._compare(self.db,self.target,'intro',own,[(ref,reference)],lambda:False)
        self.assertEqual(outcome['approvals'],1)
        with self.db() as con:
            saved=con.execute('SELECT * FROM skip_records WHERE asset_key=?',(self.target['asset_key'],)).fetchone()
            self.assertEqual(saved['id'],original['id'])
            self.assertEqual((saved['source'],saved['status']),('episcene','approved'))
            self.assertLessEqual(abs(saved['start_ms']-48000),500)
            self.assertLessEqual(abs(saved['end_ms']-74530),500)

    def test_reference_changed_between_image_comparison_and_publication_invalidates_result(self):
        vote,reference,own,ref=self.human_visual_pair()
        with self.db() as con:
            con.execute('UPDATE skip_release_settings SET enabled=0')
        outcome=scene._compare(self.db,self.target,'intro',own,[(ref,reference)],lambda:False)
        self.assertEqual(outcome['approvals'],0)
        with self.db() as con:
            con.execute('UPDATE skip_release_settings SET enabled=1')
            con.execute('UPDATE skip_records SET start_ms=start_ms+2000 WHERE id=?',(vote['record_id'],))
            self.assertEqual(release.accept_pending(con),0)

    def test_cancellation_preserves_finished_chunks_and_retry_reads_only_missing_part(self):
        from contextlib import nullcontext
        frames=visual.hashes(pixel_frames(15,180))
        def read(source,start,length,step,busy):
            if start==60000:
                raise ValueError('analysis_deferred')
            return frames[:120]
        with (mock.patch('skip_analysis.provider_proxy',return_value=nullcontext('private')),
              mock.patch.object(remote,'visual_fingerprint',side_effect=read)):
            with self.assertRaisesRegex(ValueError,'analysis_deferred'):
                scene.capture(self.db,self.target,'intro',0,90000,lambda:False,verified=True)
        with self.db() as con:
            self.assertIsNotNone(scene._cache(con,self.target,'intro',0,60000))
        with (mock.patch('skip_analysis.provider_proxy',return_value=nullcontext('private')),
              mock.patch.object(remote,'visual_fingerprint',return_value=frames[120:]) as read):
            row=scene.capture(self.db,self.target,'intro',0,90000,lambda:False,verified=True)
        self.assertEqual(read.call_count,1)
        self.assertEqual(read.call_args.args[1:4],(60000,30000,500))
        self.assertEqual(json.loads(row['frames_json']),frames)

    def test_visual_deferral_keeps_attempts_daily_budget_and_provider_playback_protection(self):
        from skip_analysis_worker import process_one
        self.waiting()
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='queued' WHERE asset_key=?",(self.target['asset_key'],))
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,5)',(now()[:10],))
        with mock.patch.object(auto,'analyze',side_effect=remote.RemoteDeferred('EpiScene: Cache fortsetzen')):
            self.assertEqual(process_one(self.db),'queued')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT attempts FROM skip_jobs WHERE asset_key=?',(self.target['asset_key'],)).fetchone()[0],2)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],5)
            con.execute('INSERT INTO skip_presence VALUES(1,1,?)',(int(time.time())+70,))
        with mock.patch.object(remote,'visual_fingerprint') as decode:
            self.assertEqual(process_one(self.db),'queued')
            decode.assert_not_called()

    def test_episcene_without_reproducible_evidence_never_auto_publishes(self):
        with self.db() as con:
            row=auto.store_proposal(con,self.target,'intro',20000,44000,'episcene',1.0,{'method':'episcene_consensus'})
            self.assertEqual(release.accept_pending(con),0)
            con.execute("UPDATE skip_auto_evidence SET evidence_json='{}' WHERE record_id=?",(row['id'],))
            self.assertEqual(release.accept_pending(con),0)

    def test_successful_visual_seed_does_not_fail_a_silent_episode_for_missing_audio(self):
        from contextlib import nullcontext
        def images(db,asset,kind,refs,busy):
            scene._state(db,asset,kind,'EpiScene: Bilder für weitere Staffelvergleiche gespeichert')
            return 0,0
        with (mock.patch.object(auto,'provider_proxy',return_value=nullcontext('private')),
              mock.patch.object(auto,'probe',return_value=(self.target['duration_ms'],[])),
              mock.patch.object(auto,'fingerprint',side_effect=ValueError('analysis_failed')),
              mock.patch.object(scene,'analyze',side_effect=images)):
            status,detail=auto.analyze(self.db,self.job(),lambda *_:lambda:False)
        self.assertEqual(status,'no_match')
        self.assertIn('EpiScene',detail)

    def test_late_intro_expands_short_seed_and_target_only_until_a_match_is_found(self):
        parent=self.descriptor('112',12);self.registered(parent)
        common=visual.hashes(pixel_frames(4817,48))
        target=visual.hashes(pixel_frames(13,1440));target[450:498]=copy.deepcopy(common)
        reference=visual.hashes(pixel_frames(12,1440));reference[410:458]=copy.deepcopy(common)
        with self.db() as con:
            scene._save(con,parent,'intro',0,180000,reference[:360])
        calls=[]
        def capture(db,asset,kind,start,end,busy,verified=False):
            calls.append((asset['episode'],start,end))
            data=target if asset['episode']==13 else reference
            with db() as con:
                return scene._save(con,asset,kind,start,end-start,data[start//500:end//500])
        with mock.patch.object(scene,'capture',side_effect=capture):
            proposals,approvals=scene.analyze(self.db,self.target,'intro',[],lambda:False)
        self.assertEqual((proposals,approvals),(1,0))
        self.assertIn((13,0,180000),calls)
        self.assertIn((13,0,360000),calls)
        self.assertIn((12,0,360000),calls)
        self.assertFalse(any(end>360000 for _,_,end in calls))

    def test_derived_pixel_cache_has_a_fixed_row_limit(self):
        with self.db() as con:
            for i in range(scene.CACHE_ROWS+5):
                scene._save(con,self.target,'intro',i*500,5000,[[0,0,0,0] for _ in range(10)])
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_scene_windows').fetchone()[0],scene.CACHE_ROWS)
            self.assertIsNone(scene._cache(con,self.target,'intro',0,5000))

    def test_new_silent_reference_learns_images_after_closing_audio_relay(self):
        import skip_analysis_worker as worker
        from contextlib import contextmanager
        from skip_schedule import request_series
        self.marker(self.target)
        with self.db() as con:
            request_series(con,self.target['asset_key'],'reference')
        active=[False]
        @contextmanager
        def relay(*_):
            active[0]=True
            try:yield 'private'
            finally:active[0]=False
        def learn(*_):
            self.assertFalse(active[0])
            return True
        with (mock.patch.object(worker,'provider_proxy',side_effect=relay),
              mock.patch.object(worker,'probe',return_value=(self.target['duration_ms'],[])),
              mock.patch.object(worker,'fingerprint',side_effect=ValueError('analysis_failed')),
              mock.patch.object(scene,'learn_reference',side_effect=learn) as learn):
            status,detail=worker.learn_requested_reference(self.db,self.job(),lambda *_:lambda:False)
        self.assertEqual(status,'done')
        self.assertIn('visuell',detail)
        self.assertEqual(learn.call_count,1)


if __name__ == '__main__':
    unittest.main()
