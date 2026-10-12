"""Adversarial EpiScene progress, language, transfer and tail regressions."""
import contextlib
import copy
from datetime import datetime
import importlib
import importlib.util
import json
import random
import shutil
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_skip_analysis_automation import AutomationFixture
import skip_scene as scene
import skip_visual as visual
import skip_automation as audio
import skip_remote_client as remote
import skip_analysis_worker as worker
import skip_catalogue as catalogue
import skip_schedule as schedule
import skip_scene_reliability as reliability
import skip_source_preferences as preferences
import skip_variant_reuse as variants
import skip_tail_check as tail
import skip_daily_reports as reports
from test_skip_analysis_episcene import sequence


def frames(start,count,scale=1.,offset=0):
    result=[]
    for i in range(count):
        index=round((start+i*500-offset)/scale/500)
        rng=random.Random(91817+index)
        result.append([rng.getrandbits(63),rng.getrandbits(64),40,120])
    return result


def fresh(module):
    for name in ('_reliability','_source_preferences','_tail_check','_durable_visual'):
        if hasattr(module,name):
            delattr(module,name)
    return importlib.reload(module)


class Base(AutomationFixture,unittest.TestCase):
    def setUp(self):
        for module in (remote,visual,scene,audio,worker,catalogue,schedule,reliability,reports):
            fresh(module)
        super().setUp()
        self.registered(self.target)
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_metadata_config VALUES('episcene_enabled','1','now')")
            reports.migrate(con)
            con.execute("UPDATE episcene_report_meta SET value='0' WHERE name='collection_started'")
        self.addCleanup(self.restore)

    def restore(self):
        for module in (remote,visual,scene,audio,worker,catalogue,schedule,reliability,reports):
            fresh(module)

    def asset(self,key=None):
        with self.db() as con:
            return dict(con.execute('SELECT * FROM skip_assets WHERE asset_key=?',(key or self.target['asset_key'],)).fetchone())


class Progress(Base):
    def test_snapshot_revision_change_blocks_automatic_publication(self):
        reliability.install_scene(scene)
        asset=self.asset()
        with self.db() as con:
            cached=scene._save(con,asset,'intro',0,15000,frames(0,30))
            snapshot=scene._snapshot(cached,asset)
            self.assertEqual(snapshot['source_version'],reliability.asset_version(asset))
            con.execute("UPDATE skip_assets SET updated_at='2026-12-01T00:00:00Z' WHERE asset_key=?",(asset['asset_key'],))
            row=dict(asset,status='pending',source='episcene',segment_type='intro')
            self.assertFalse(scene.release_ready(con,row,{'method':'episcene_consensus','windows':[snapshot]}))

    def test_independent_analysis_id_never_resolves_customer_credentials(self):
        with self.db() as con:
            con.execute('CREATE TABLE skip_analysis_playlists(id INTEGER PRIMARY KEY,name TEXT,config_json TEXT)')
            con.execute("INSERT INTO skip_analysis_playlists VALUES(1,'Independent analysis','analysis-config')")
            self.assertEqual(reliability.analysis_playlist(con,1)['config_json'],'analysis-config')
            self.assertEqual(con.execute('SELECT config_json FROM customer_playlists WHERE id=1').fetchone()[0],json.dumps(self.config))
    def test_failed_chunk_does_not_advance_checkpoint_and_resume_reuses_success(self):
        reliability.install_scene(scene)
        asset=self.asset()
        reads=[]
        def extract(_source,start,length,step,busy):
            reads.append(start)
            if len(reads)==2:
                raise ValueError('visual_incomplete')
            return frames(start,(length+499)//500)
        media=types.SimpleNamespace(url='private',via_pi=False)
        with mock.patch('skip_analysis.provider_proxy',side_effect=lambda *a:contextlib.nullcontext(media)), mock.patch.object(worker,'busy_check',return_value=lambda:False),mock.patch.object(remote,'visual_fingerprint',side_effect=extract):
            with self.assertRaisesRegex(ValueError,'visual_incomplete'):
                scene.capture(self.db,asset,'intro',0,120000,lambda:False,verified=True)
            row=scene.capture(self.db,asset,'intro',0,120000,lambda:False,verified=True)
        self.assertEqual(reads,[0,60000,60000])
        self.assertEqual(len(json.loads(row['frames_json'])),240)

    def test_file_revision_change_invalidates_cached_window(self):
        reliability.install_scene(scene)
        asset=self.asset()
        with self.db() as con:
            scene._save(con,asset,'intro',0,15000,frames(0,30))
            self.assertIsNotNone(scene._cache(con,asset,'intro',0,15000))
            changed=dict(asset,updated_at='new-source-revision')
            self.assertIsNone(scene._cache(con,changed,'intro',0,15000))

    def test_caught_visual_incomplete_cannot_finish_as_no_match(self):
        def visual_analysis(db,asset,kind,refs,busy):
            try:
                raise ValueError('visual_incomplete')
            except ValueError:
                scene._state(db,asset,kind,'EpiScene: Bildprüfung unvollständig; Vorschläge bleiben')
            return 0,0
        scene.analyze=visual_analysis
        reliability.install_scene(scene)
        def analyze(db,job,busy_factory):
            for kind in ('intro','outro'):
                scene.analyze(db,self.asset(),kind,[],lambda:False)
            return 'no_match','old false negative'
        audio.analyze=analyze
        reliability.install_automation(audio)
        with mock.patch.object(variants,'try_reuse',return_value=[]):
            status,_=audio.analyze(self.db,self.job(),lambda *a:lambda:False)
        self.assertEqual(status,'partial')
        with self.db() as con:
            self.assertEqual([r[0] for r in con.execute('SELECT status FROM skip_scene_progress')],['partial','partial'])
            errors=[json.loads(r[0]) for r in con.execute("SELECT payload FROM episcene_report_events WHERE kind='phase_error'")]
            self.assertEqual(len({e['error_id'] for e in errors}),2)
            self.assertEqual({e['error_code'] for e in errors},{'visual_incomplete'})

    def test_missing_partner_is_distinct_from_complete_negative(self):
        def analyze(db,job,busy_factory):
            for kind in ('intro','outro'):
                reliability.state(db,self.asset(),kind,'no_reference')
            return 'no_match','old result'
        audio.analyze=analyze
        reliability.install_automation(audio)
        with mock.patch.object(variants,'try_reuse',return_value=[]):
            status,_=audio.analyze(self.db,self.job(),lambda *a:lambda:False)
        self.assertEqual(status,'no_reference')

    def test_late_batch_does_not_claim_a_new_job(self):
        original=mock.Mock(return_value='done')
        worker.process_one=original
        reliability.install_worker(worker)
        with self.db() as con:
            before=[tuple(r) for r in con.execute('SELECT * FROM skip_jobs')]
        self.assertEqual(worker.process_one(self.db,deadline=time.monotonic()+10),'queued')
        original.assert_not_called()
        with self.db() as con:
            self.assertEqual(before,[tuple(r) for r in con.execute('SELECT * FROM skip_jobs')])

    def test_successful_comparison_survives_another_call_without_recomputing(self):
        local=mock.Mock(side_effect=lambda t,p,k,b:visual.detect(t,p,k,b))
        remote.visual_detect=local
        reliability.install_scene(scene)
        target=sequence(13)
        target.episode_id=self.target['asset_key']
        partners=[sequence(n) for n in (10,11,12)]
        token=reliability.CONTEXT.set(dict(attempt_id='attempt',asset=self.asset(),db=self.db,kind='intro'))
        try:
            one=remote.visual_detect(target,partners,'intro')
            two=remote.visual_detect(target,partners,'intro')
        finally:
            reliability.CONTEXT.reset(token)
        self.assertEqual(one,two)
        self.assertEqual(local.call_count,1)

    def test_failed_comparison_is_not_cached_as_a_completed_checkpoint(self):
        target=sequence(13);target.episode_id=self.target['asset_key']
        partners=[sequence(n) for n in (10,11,12)]
        answer=visual.detect(target,partners,'intro')
        original=mock.Mock(side_effect=[remote.RemoteDeferred(),answer])
        remote.visual_detect=original
        reliability.install_scene(scene)
        token=reliability.CONTEXT.set(dict(attempt_id='attempt',asset=self.asset(),db=self.db,kind='intro'))
        try:
            with self.assertRaises(remote.RemoteDeferred):
                remote.visual_detect(target,partners,'intro')
            with self.db() as con:
                self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_scene_compare_cache').fetchone()[0],0)
            remote.visual_detect(target,partners,'intro')
            remote.visual_detect(target,partners,'intro')
        finally:
            reliability.CONTEXT.reset(token)
        self.assertEqual(original.call_count,2)

    def test_old_incomplete_negatives_are_separate_and_not_claimed_as_verified(self):
        events=[dict(id=1,kind='scene',asset_key='a',at=5,payload={'detail':'Bildprüfung unvollständig'}),
                dict(id=2,kind='job',asset_key='a',at=6,payload={'previous_status':'running','started_at':4,'job':{'status':'no_match'}}),
                dict(id=3,kind='job',asset_key='b',at=7,payload={'previous_status':'running','started_at':4,'job':{'status':'no_match'}})]
        r=dict(events=events,summary={'outcomes':{'no_match':2}},findings=[])
        reliability.enrich_report(r)
        self.assertEqual((r['summary']['incomplete_negative_attempts'],r['summary']['fully_checked_no_match'],r['summary']['legacy_unverified_no_match']),(1,0,1))


class Languages(Base):
    def configure(self):
        with self.db() as con:
            con.execute("UPDATE skip_analysis_sources SET enabled=1 WHERE playlist_id=3")
            con.execute("INSERT INTO skip_auto_settings VALUES(3,1,0,'now')")
            preferences.migrate(con)
            con.executemany('INSERT INTO skip_source_preferences VALUES(?,?)',[(1,'de'),(3,'it')])
        preferences.install(catalogue,schedule)

    def language_asset(self,pid,lang,stream,episode):
        data=self.descriptor(stream,episode,playlist_id=pid,title=f'[{lang.upper()}] Lie to Me',source_key=(lang+str(pid)).ljust(64,'0'))
        self.registered(data)
        with self.db() as con:
            catalogue.set_asset_language(con,data['asset_key'],catalogue.language_priority({'audio_language':lang}))
        return data

    def test_4k_german_and_best_italian_override_other_language_series_focus(self):
        self.configure()
        de=self.language_asset(1,'de','801',1)
        it=self.language_asset(1,'it','802',1)
        best_de=self.language_asset(3,'de','803',1)
        best_it=self.language_asset(3,'it','804',1)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='done' WHERE asset_key=?",(self.target['asset_key'],))
            schedule.remember(con,{'asset_key':it['asset_key']})
            self.assertEqual(schedule.select_job(con,1,stage=0)[0]['asset_key'],de['asset_key'])
            schedule.remember(con,{'asset_key':best_de['asset_key']})
            self.assertEqual(schedule.select_job(con,3,stage=0)[0]['asset_key'],best_it['asset_key'])

    def test_both_sources_get_turns_and_unavailable_source_does_not_block(self):
        self.configure()
        a=self.language_asset(1,'de','805',1)
        b=self.language_asset(3,'it','806',1)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='done' WHERE asset_key=?",(self.target['asset_key'],))
            first=schedule.current_playlist(con,stage=0)
            schedule.remember(con,{'asset_key':a['asset_key'] if first==1 else b['asset_key']})
            second=schedule.current_playlist(con,stage=0)
            self.assertNotEqual(first,second)
            self.assertEqual(schedule.current_playlist(con,excluded=(3,),stage=0),1)

    def test_provider_categories_keep_language_and_unknown_title_is_not_guessed(self):
        preferences.install(catalogue,schedule)
        ranks=catalogue.category_priorities([{'category_id':51,'category_name':'Italian Series'}])
        result=catalogue.language_priority({'category_id':51},ranks)
        self.assertEqual(result.codes,{'it'})
        self.assertEqual(catalogue.language_priority({'name':'Chicago Med'}).codes,frozenset())

    def test_series_language_survives_json_metadata_and_reaches_new_episodes(self):
        self.configure()
        data=self.language_asset(3,'it','811',2)
        with self.db() as con:
            con.execute('DELETE FROM skip_asset_languages WHERE asset_key=?',(data['asset_key'],))
            catalogue.set_series_language(con,3,'701',catalogue.language_priority({'audio_language':'it'}))
            con.execute('INSERT INTO skip_catalogue_episodes VALUES(?,?,?,?,?)',(3,'701',data['asset_key'],'signature',1))
            catalogue.set_asset_language(con,data['asset_key'],catalogue.language_priority({},fallback=0))
            row=con.execute('SELECT codes FROM skip_asset_languages WHERE asset_key=?',(data['asset_key'],)).fetchone()
            self.assertEqual(json.loads(row[0]),['it'])

    def test_existing_saved_provider_tag_can_prioritize_clean_asset_title(self):
        self.configure()
        data=self.language_asset(3,'it','812',2)
        with self.db() as con:
            con.execute('UPDATE skip_assets SET title=? WHERE asset_key=?',('Lie to Me',data['asset_key']))
            con.execute('DELETE FROM skip_asset_languages WHERE asset_key=?',(data['asset_key'],))
            con.execute('INSERT INTO skip_catalogue_series(playlist_id,series_id,payload_json,signature,seen_generation) VALUES(?,?,?,?,?)',
                        (3,'702',json.dumps({'name':'[IT] Lie to Me','language_priority':0}),'sig',1))
            con.execute('INSERT INTO skip_catalogue_episodes VALUES(?,?,?,?,?)',(3,'702',data['asset_key'],'signature',1))
            self.assertIn(data['asset_key'],preferences.preferred_keys(con,3,stage=0))


class Transfer(Base):
    def test_human_confirmation_of_generated_marker_remains_authoritative(self):
        self.registered(self.seed)
        rid=self.marker(self.seed)
        with self.db() as con:
            con.execute("UPDATE skip_records SET source='episcene' WHERE id=?",(rid,))
            con.execute('INSERT INTO skip_auto_evidence VALUES(?,?,1)',(rid,json.dumps({'method':'episcene_consensus','decision':{'status':'REVIEW'}})))
            marker=con.execute('SELECT * FROM skip_records WHERE id=?',(rid,)).fetchone()
            self.assertTrue(variants.confirmed_source(con,marker))
            con.execute('UPDATE skip_auto_evidence SET human_review=0 WHERE record_id=?',(rid,))
            self.assertFalse(variants.confirmed_source(con,marker))

    def test_conflicting_external_episode_identity_is_not_rescued_by_same_title(self):
        self.registered(self.seed)
        source=self.asset(self.seed['asset_key'])
        target=dict(source,source_key='c'*64)
        with self.db() as con:
            con.executemany('INSERT INTO skip_auto_identities VALUES(?,?,0,?,?)',[(source['source_key'],'tt1234567','tmdb_title_year_episode','now'),(target['source_key'],'tt7654321','tmdb_title_year_episode','now')])
            self.assertFalse(variants.same_candidate(con,source,target))
    def test_wrong_episode_with_same_intro_fails_story_validation(self):
        shared=frames(0,20)
        other=frames(500000,120)
        with self.assertRaisesRegex(ValueError,'variant_anchor_mismatch'):
            variants.match_anchor(shared,other,0,0)

    def test_constant_shift_and_uniform_speed_have_consistent_mapping(self):
        for scale,offset in [(1,3500),(1.025,18000),(.975,-3000)]:
            anchors=[dict(source_ms=x,target_ms=round(scale*x+offset)) for x in (600000,1200000,1800000)]
            result=variants.fit_map(anchors,2400000)
            self.assertAlmostEqual(result['scale'],scale,places=6)
            self.assertAlmostEqual(result['offset_ms'],offset,places=4)
        anchors=[dict(source_ms=x,target_ms=y) for x,y in [(600000,600000),(1200000,1240000),(1800000,1800000)]]
        with self.assertRaisesRegex(ValueError,'variant_edit_mismatch'):
            variants.fit_map(anchors,2400000)

    def test_verified_identical_dub_can_transfer_but_changed_marker_or_pixels_cannot(self):
        self.registered(self.seed)
        target=self.descriptor('891',12,source_key='c'*64,title='[IT] Lie to Me')
        self.registered(target)
        reliability.install_scene(scene)
        source=self.asset(self.seed['asset_key'])
        target=self.asset(target['asset_key'])
        rid=self.marker(self.seed)
        with self.db() as con:
            marker=dict(con.execute('SELECT r.*,e.evidence_json FROM skip_records r LEFT JOIN skip_auto_evidence e ON e.record_id=r.id WHERE r.id=?',(rid,)).fetchone())
        def sample(db,asset,kind,start,length,busy):
            start=max(0,start//500*500)
            length=min(length,asset['duration_ms']-start)
            with self.db() as con:
                row=scene._save(con,asset,kind,start,length,frames(start,(length+499)//500))
            result=scene._window(row,asset)
            result.reuse_snapshot=dict(scene._snapshot(row,asset),source_version=reliability.asset_version(asset))
            return result
        with mock.patch.object(variants,'sample',side_effect=sample):
            evidence=variants.verify(self.db,source,target,marker,lambda:False,[(marker['start_ms'],marker['end_ms'])])
        proposed=dict(target,segment_type='intro',start_ms=evidence['start_ms'],end_ms=evidence['end_ms'])
        with self.db() as con:
            self.assertTrue(variants.release_ready(con,proposed,evidence))
            con.execute('UPDATE skip_records SET start_ms=start_ms+1000 WHERE id=?',(rid,))
            self.assertFalse(variants.release_ready(con,proposed,evidence))
            con.execute('UPDATE skip_records SET start_ms=start_ms-1000 WHERE id=?',(rid,))
            window=evidence['story_anchors'][0]['target_window']['id']
            con.execute("UPDATE skip_scene_windows SET frames_json='[]' WHERE id=?",(window,))
            self.assertFalse(variants.release_ready(con,proposed,evidence))


class Tail(unittest.TestCase):
    @unittest.skipUnless(shutil.which('ffmpeg'),'ffmpeg required')
    def test_real_black_silent_tail_is_decoded_and_dialogue_is_retained(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            for name,audio_filter,expected in [('silent','anullsrc=r=16000:cl=mono',True),('sound','sine=frequency=880:sample_rate=16000',False)]:
                path=Path(directory)/(name+'.mkv')
                subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','color=c=black:s=64x64:r=10:d=5','-f','lavfi','-i',audio_filter,'-t','5','-c:v','ffv1','-c:a','pcm_s16le',str(path)],check=True,timeout=20)
                with mock.patch('skip_analysis.input_options',return_value=[]):
                    result=tail.measure(str(path),1000,4000,lambda:False)
                self.assertEqual(result['empty'],expected)
    def test_empty_gap_can_complete_strong_consensus_but_does_not_lower_partner_rule(self):
        fresh(visual)
        self.addCleanup(lambda:fresh(visual))
        tail.install_visual(visual)
        target=sequence(13,60)
        target.offset_ms=target.duration_ms-55000
        partners=[sequence(i,20) for i in (10,11,12)]
        for p in partners:
            p.offset_ms=p.duration_ms-55000
        value=visual.detect(target,partners,'outro')
        gap=target.duration_ms-value['end_ms']
        # The fixture's common sequence ends within five seconds of EOF.
        self.assertTrue(1000<gap<=5000)
        proof=dict(policy=tail.POLICY,empty=True,asset_key=target.episode_id,duration_ms=target.duration_ms,
                   start_ms=value['end_ms'],end_ms=target.duration_ms,video_max=0,audio_peak=0,
                   video_samples=math_floor(gap/100),audio_samples=math_floor(gap*16),source_version='a'*64)
        approved=dict(value,status='AUTO_CONFIRMED',tail_check=proof)
        visual.validate_result(approved,target,partners,'outro')
        for field,bad in [('video_max',10),('audio_peak',.02),('empty',False),('audio_samples',1)]:
            forged=copy.deepcopy(approved);forged['tail_check'][field]=bad
            with self.assertRaises(ValueError):
                visual.validate_result(forged,target,partners,'outro')
        with self.assertRaises(ValueError):
            visual.validate_result(approved,target,partners[:2],'outro')

    def test_audio_dialogue_or_picture_after_credits_is_not_empty(self):
        for brightness,amplitude in [(0,0),(0,.1),(45,0)]:
            import numpy as np
            raw=bytes([brightness])*(30*1024)
            pcm=np.full(48000,amplitude,dtype='<f4').tobytes()
            with mock.patch('skip_analysis.run',side_effect=[raw,pcm]):
                value=tail.measure('fixture',10000,13000,lambda:False)
            self.assertEqual(value['empty'],brightness==0 and amplitude==0)


def math_floor(value):
    return int(value//1)


class Installer(unittest.TestCase):
    def setUp(self):
        path=Path(__file__).resolve().parents[1]/'deploy/install_episcene_20261012.py'
        spec=importlib.util.spec_from_file_location('episcene_installer',path)
        self.module=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.module)

    def test_overlay_preserves_worker_body_and_exact_main_guard(self):
        text='def process_one(db, **kwargs):\n    return "original_lane"\n\nif __name__ == "__main__":\n    process_one(None)\n'
        result=self.module.add_hook(text,'skip_analysis_worker.py')
        self.assertIn('return "original_lane"',result)
        self.assertLess(result.index(self.module.BEGIN),result.index('if __name__'))
        self.assertEqual(self.module.strip_hook(result,'skip_analysis_worker.py'),text)
        with self.assertRaises(RuntimeError):
            self.module.add_hook(result,'skip_analysis_worker.py')

    def test_preferences_touch_only_independent_named_analysis_accesses(self):
        con=sqlite3.connect(':memory:')
        con.execute('CREATE TABLE skip_analysis_playlists(id INTEGER,name TEXT)')
        con.executemany('INSERT INTO skip_analysis_playlists VALUES(?,?)',[(8,'4K ANALYSE'),(9,'THE BEST'),(10,'THE BEST'),(11,'Unrelated')])
        self.assertEqual(self.module.source_preferences(con),{8:'de',9:'it',10:'it'})
        con.execute('DROP TABLE skip_analysis_playlists')
        con.execute('CREATE TABLE customer_playlists(id INTEGER,name TEXT)')
        con.execute("INSERT INTO customer_playlists VALUES(8,'4K ANALYSE')")
        with self.assertRaises(RuntimeError):
            self.module.source_preferences(con)

    def test_embedded_payload_matches_reviewed_modules(self):
        root=Path(__file__).resolve().parents[1]
        self.assertEqual(self.module.payload(),{name:(root/name).read_text() for name in self.module.MODULES})

    def test_unknown_active_hash_stops_before_any_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            ctl=Path(directory)/'controller';compute=Path(directory)/'compute'
            ctl.mkdir();compute.mkdir()
            for root in (ctl,compute):
                for name in set(self.module.HOOKS)|{'skip_visual.py','skip_release.py'}:
                    (root/name).write_text('# unexpected live source\n')
            with self.assertRaises(RuntimeError):
                self.module.plan(ctl,compute,self.module.payload())
            self.assertEqual((ctl/'skip_scene.py').read_text(),'# unexpected live source\n')

    def test_failed_worker_health_rolls_back_added_files_without_replacing_database(self):
        module=self.module
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);ctl=root/'controller';compute=root/'compute'
            ctl.mkdir();compute.mkdir()
            database=root/'provisioning.db'
            with sqlite3.connect(database) as con:
                con.execute('CREATE TABLE skip_analysis_playlists(id INTEGER,name TEXT,enabled INTEGER)')
                con.executemany('INSERT INTO skip_analysis_playlists VALUES(?,?,?)',[(8,'4K ANALYSE',1),(10,'THE BEST',1)])
                con.execute('CREATE TABLE human_markers(id INTEGER,start_ms INTEGER)')
                con.execute('INSERT INTO human_markers VALUES(1,12345)')
            old=ctl/'skip_scene.py';old.write_text('old scene\n')
            created=compute/'new_module.py'
            originals={old:old.read_bytes(),created:None}
            desired={old:b'new scene\n',created:b'new module\n'}
            for path in (ctl,compute):
                venv=path/'.venv/bin';venv.mkdir(parents=True);(venv/'python').symlink_to(sys.executable)
            (compute/'skip_scene.py').write_text('reference\n')
            with mock.patch.object(module,'plan',return_value=(originals,desired)), mock.patch.object(module,'health',side_effect=[None]+[RuntimeError('worker version mismatch')]*12), mock.patch.object(module,'active',return_value=True), mock.patch.object(module,'run'),mock.patch.object(module.subprocess,'run'),mock.patch.object(module.time,'sleep'),mock.patch.object(module.shutil,'disk_usage',return_value=types.SimpleNamespace(free=2*1024**3)),mock.patch.object(module.os,'geteuid',return_value=0):
                with self.assertRaisesRegex(RuntimeError,'worker version mismatch'):
                    module.main(['--apply','--controller',str(ctl),'--compute',str(compute),'--database',str(database)])
            self.assertEqual(old.read_bytes(),originals[old])
            self.assertFalse(created.exists())
            with sqlite3.connect(database) as con:
                self.assertEqual(con.execute('SELECT * FROM human_markers').fetchall(),[(1,12345)])
                self.assertEqual(con.execute('SELECT enabled FROM skip_analysis_playlists').fetchall(),[(1,),(1,)])


if __name__=='__main__':
    unittest.main()
