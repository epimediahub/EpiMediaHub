"""Automatic acceptance, bootstrap references, player corrections and complete progress."""
import contextlib
import json
import random
import time
import unittest
from unittest import mock

from test_skip_analysis_automation import AutomationFixture
from test_skip_analysis_bulk_review import BulkReviewFixture
import test_skip_analysis_automation as automation_tests
from skip_markers import add_record, migrate, now, review_record
from skip_release import accept_pending, enabled, POLICY
from skip_progress import overview
import skip_automation as auto
from skip_analysis_worker import busy_check, process_one


class AcceptanceTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with self.db() as con:
            con.execute('DELETE FROM skip_release_settings')
        self.registered(self.target)

    def proposal(self, data=None, kind='intro', source='audio', start=10000, end=40000, confidence=.81):
        data = data or self.target
        with self.db() as con:
            saved = add_record(con, data, kind, start, end, False, source=source, confidence=confidence)
        return saved['id']

    def test_default_accepts_all_detected_sources_and_kinds_without_a_human_seed(self):
        ids = []
        for n, source in enumerate(('audio','chapter','theintrodb','audio_repetition')):
            data = self.descriptor(str(100+n), n+1)
            self.registered(data)
            for kind in ('intro','recap','outro'):
                ids.append(self.proposal(data,kind,source,confidence=.81))
        with self.db() as con:
            self.assertTrue(enabled(con,1))
            self.assertEqual(accept_pending(con),12)
            self.assertEqual(accept_pending(con),0)
            self.assertEqual(set(r[0] for r in con.execute('SELECT status FROM skip_records')),{'approved'})
            self.assertEqual(set(r[0] for r in con.execute('SELECT human_review FROM skip_auto_evidence')),{0})

    def test_first_update_automatically_accepts_backlog_and_preserves_budget_and_done_jobs(self):
        record = self.proposal()
        with self.db() as con:
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?',(POLICY,))
            con.execute("UPDATE skip_jobs SET status='done',attempts=2")
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,96)',(now()[:10],))
            migrate(con)
            self.assertEqual(con.execute('SELECT status FROM skip_records WHERE id=?',(record,)).fetchone()[0],'approved')
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:],('done',2))
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],96)

    def test_manual_mode_inactive_source_and_wrong_version_do_not_publish(self):
        record = self.proposal()
        with self.db() as con:
            con.execute('INSERT INTO skip_release_settings VALUES(1,0,?)',(now(),))
            self.assertEqual(accept_pending(con),0)
            con.execute('DELETE FROM skip_release_settings')
            con.execute('UPDATE skip_analysis_sources SET enabled=0 WHERE playlist_id=1')
            self.assertEqual(accept_pending(con),0)
            con.execute('UPDATE skip_analysis_sources SET enabled=1 WHERE playlist_id=1')
            con.execute('UPDATE skip_assets SET episode=99')
            self.assertEqual(accept_pending(con),0)
            self.assertEqual(con.execute('SELECT status FROM skip_records WHERE id=?',(record,)).fetchone()[0],'pending')

    def test_strongest_alternative_wins_and_existing_rejection_or_correction_stays_authoritative(self):
        first = self.proposal(source='theintrodb')
        second = self.proposal(source='audio',start=60000,end=90000)
        with self.db() as con:
            self.assertEqual(accept_pending(con),1)
            self.assertEqual(dict(con.execute('SELECT id,status FROM skip_records')), {first:'superseded',second:'approved'})
            row=con.execute('SELECT * FROM skip_records WHERE id=?',(second,)).fetchone()
            review_record(con,row,'approve',70000,100000,False)
            later=add_record(con,self.target,'intro',10000,20000,False,source='chapter')['id']
            self.assertEqual(accept_pending(con),0)
            self.assertEqual(con.execute('SELECT status,start_ms,end_ms FROM skip_records WHERE id=?',(second,)).fetchone()[:],('approved',70000,100000))
            review_record(con,row,'reject',70000,100000,False)
            self.assertEqual(accept_pending(con),0)
            self.assertEqual(con.execute('SELECT status FROM skip_records WHERE id=?',(later,)).fetchone()[0],'superseded')

    def test_pending_human_correction_is_not_bypassed_and_invalid_ranges_never_publish(self):
        self.proposal()
        with self.db() as con:
            add_record(con,self.target,'intro',20000,50000,False,self.device)
            self.assertEqual(accept_pending(con),0)
            self.assertEqual(set(r[0] for r in con.execute('SELECT status FROM skip_records')),{'pending'})
            con.execute('DELETE FROM skip_records')
        record=self.proposal(end=self.target['duration_ms']+1000)
        with self.db() as con:
            self.assertEqual(accept_pending(con),0)
            self.assertEqual(con.execute('SELECT status FROM skip_records WHERE id=?',(record,)).fetchone()[0],'pending')

    def test_repetition_seeds_automatic_reference_without_self_training_from_derived_audio(self):
        rng=random.Random(8401); shared=[rng.getrandbits(32) for _ in range(220)]
        data=[]
        for stream,episode,position in (('81',12,200),('82',13,300),('83',14,400)):
            item=self.descriptor(stream,episode);self.registered(item);data.append(item)
            words=[rng.getrandbits(32) for _ in range(position)]+shared+[rng.getrandbits(32) for _ in range(80)]
            with self.db() as con: auto.save_window(con,item,'intro',words,125,0,120000)
        with self.db() as con:
            self.assertTrue(auto.bootstrap(con,data[-1],'intro'))
            self.assertEqual(accept_pending(con),1)
            refs=auto.reference_rows(con,data[0],'intro')
            self.assertEqual(len(refs),1)
            self.assertEqual(refs[0]['source'],'audio_repetition')
        self.proposal(data[1],source='audio')
        with self.db() as con:
            self.assertEqual(accept_pending(con),1)
            self.assertEqual(len(auto.reference_rows(con,data[0],'intro')),1)

    def test_direct_worker_finishes_published_proposals_without_review(self):
        self.proposal(source='chapter')
        with mock.patch.object(auto,'discover_one',return_value='idle'),mock.patch('skip_analysis_worker.analyze',return_value=('review','fixture')):
            self.assertEqual(process_one(self.db),'done')
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status FROM skip_records').fetchone()[0],'approved')

    def test_result_from_a_reference_corrected_during_analysis_is_discarded(self):
        vote=self.voted(12,'81')
        with self.db() as con:
            candidate=auto.store_proposal(con,self.target,'intro',48000,74530,'audio',.98,
                                         {'method':'reviewed_audio_match','vote':vote})
            reference=con.execute('SELECT * FROM skip_records WHERE id=?',(vote['record_id'],)).fetchone()
            review_record(con,reference,'approve',reference['start_ms']+1000,reference['end_ms']+1000,False)
            self.assertEqual(accept_pending(con),0)
            self.assertEqual(con.execute('SELECT status FROM skip_records WHERE id=?',(candidate['id'],)).fetchone()[0],'superseded')


@unittest.skipUnless(automation_tests.REAL_FLASK, 'Flask required for player/dashboard integration')
class AutomaticPlayerTests(BulkReviewFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with self.db() as con: con.execute('DELETE FROM skip_release_settings')

    def submit(self,data,token='fixture-token'):
        return self.client.post('/v1/device/skip/submit',json=data|dict(segment_type='intro',start_ms=20000,end_ms=50000,disabled=False),headers={'Authorization':'Bearer '+token})

    def test_player_correction_is_immediately_available_then_disabling_it_blocks_automation(self):
        self.registered(self.target)
        with self.db() as con:
            add_record(con,self.target,'intro',10000,40000,False,source='chapter')
            accept_pending(con)
        response=self.submit(self.target)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['status'],'approved')
        lookup=self.client.post('/v1/device/skip/lookup',json=self.target,headers={'Authorization':'Bearer fixture-token'})
        self.assertEqual(lookup.json['segments'][0]['start_ms'],20000)
        off=self.target|dict(segment_type='intro',start_ms=0,end_ms=0,disabled=True)
        response=self.client.post('/v1/device/skip/submit',json=off,headers={'Authorization':'Bearer fixture-token'})
        self.assertEqual(response.json['status'],'approved')
        with self.db() as con:
            self.assertTrue(con.execute('SELECT 1 FROM skip_auto_blocks').fetchone())
            self.assertIsNone(auto.store_proposal(con,self.target,'intro',10000,40000,'audio',.99))

    def test_foreign_playlist_or_unregistered_descriptor_is_not_automatically_published(self):
        response=self.submit(self.target,token='foreign-token')
        self.assertEqual(response.json['status'],'pending')
        response=self.submit(self.target|dict(asset_key='d'*64))
        self.assertEqual(response.json['status'],'pending')

    def test_saving_preferences_does_not_requeue_completed_analysis(self):
        self.registered(self.target)
        with self.db() as con: con.execute("UPDATE skip_jobs SET status='done',attempts=2")
        response=self.client.post('/admin/skip/automatic/1',data=dict(csrf='fixture-csrf',enabled='1',auto_accept='1'))
        self.assertEqual(response.status_code,302)
        with self.db() as con: self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:],('done',2))

    def test_bulk_approval_can_apply_a_pending_player_correction_over_an_automatic_mark(self):
        self.registered(self.target)
        with self.db() as con:
            add_record(con,self.target,'intro',10000,40000,False,source='chapter')
            accept_pending(con)
        corrected=self.mark('82',13)
        with self.db() as con: con.execute('UPDATE skip_records SET start_ms=20000,end_ms=50000 WHERE id=?',(corrected,))
        self.assertIn('1 Zeitmarken freigegeben',self.notice(self.approve(season=2)))
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status FROM skip_records WHERE id=?',(corrected,)).fetchone()[0],'approved')

    def test_dashboard_renders_all_series_progress_filters_and_automatic_acceptance(self):
        self.registered(self.target)
        body=self.client.get('/admin/skip').get_data(as_text=True)
        self.assertIn('Serienfortschritt',body)
        self.assertIn('Intro vorhanden: 0 / 1',body)
        self.assertIn('name="auto_accept" value="1" checked',body)


class ProgressTests(AutomationFixture, unittest.TestCase):
    def test_completion_is_distinct_from_intro_coverage_and_includes_all_jobs(self):
        for n,status in enumerate(('done','no_match','failed','no_reference','queued')):
            data=self.descriptor(str(200+n),n+1);self.registered(data)
            with self.db() as con:
                con.execute('UPDATE skip_jobs SET status=? WHERE asset_key=?',(status,data['asset_key']))
                if n==0:
                    record=add_record(con,data,'intro',10000,40000,False,source='chapter')
                    con.execute("UPDATE skip_records SET status='approved' WHERE id=?",(record['id'],))
        with self.db() as con:
            # Production has customer names; fixtures add them for this query.
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture'")
            item=overview(con)['rows'][0]
            self.assertEqual((item['files'],item['analyzed'],item['intros'],item['not_found'],item['waiting'],item['failed'],item['no_reference']),(5,2,1,1,1,1,1))
            self.assertFalse(item['complete'])
            con.execute("UPDATE skip_jobs SET status='no_match'")
            item=overview(con,'completed')['rows'][0]
            self.assertTrue(item['complete'])
            self.assertEqual((item['intros'],item['missing'],item['percent']),(1,4,100))

    def test_overview_pages_more_than_twenty_series_and_preserves_source_identity(self):
        with self.db() as con: con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture'")
        for n in range(23):
            import hashlib
            data=self.descriptor(str(400+n),1,title=f'Serie {n:02d}',source_key=hashlib.sha256(str(n).encode()).hexdigest())
            self.registered(data)
        with self.db() as con:
            first=overview(con);last=overview(con,page=2)
            self.assertEqual((first['total'],first['pages'],len(first['rows'])),(23,2,20))
            self.assertEqual([r['title'] for r in last['rows']],['Serie 20','Serie 21','Serie 22'])
            self.assertEqual(overview(con,search='Serie 22')['total'],1)
            self.assertEqual(overview(con,'with_intro')['total'],0)
            self.assertEqual(overview(con,'missing_intro')['total'],23)

    def test_wrong_runtime_disabled_intro_and_pending_inventory_are_not_reported_as_all_intros_done(self):
        self.registered(self.target)
        with self.db() as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture'")
            con.execute("UPDATE skip_jobs SET status='done'")
            record=add_record(con,self.target,'intro',0,0,True,self.device)
            con.execute("UPDATE skip_records SET status='approved' WHERE id=?",(record['id'],))
            item=overview(con)['rows'][0]
            self.assertEqual((item['intros'],item['disabled'],item['not_found']),(0,1,1))
            con.execute('UPDATE skip_records SET disabled=0,start_ms=10000,end_ms=40000,duration_ms=duration_ms+10000')
            self.assertEqual(overview(con)['rows'][0]['intros'],0)
            con.execute("INSERT INTO skip_catalogue_series VALUES(1,'501','{}','version',0,1,1,0,'','')")
            con.execute('INSERT INTO skip_catalogue_episodes VALUES(?,?,?,?,?)',(1,'501',self.target['asset_key'],'version',1))
            self.assertFalse(overview(con)['rows'][0]['complete'])


class ReferenceCacheTests(AutomationFixture, unittest.TestCase):
    def test_complete_reference_is_reused_and_redecoded_after_a_manual_correction(self):
        audio=automation_tests.WorkerTests.setup_audio(self,two=False)
        def analyze(data):
            with mock.patch.object(auto,'provider_proxy',side_effect=lambda *a:contextlib.nullcontext('fixture')), \
                 mock.patch.object(auto,'probe',return_value=(data['duration_ms'],[])), \
                 mock.patch.object(auto,'fingerprint',side_effect=audio) as decode:
                result=auto.analyze(self.db,self.job(data),busy_check)
                return result,sum(bool(call.kwargs.get('require_complete')) for call in decode.call_args_list)
        result,calls=analyze(self.target)
        self.assertEqual((result[0],calls),('done',1))
        other=self.descriptor('84',14);self.registered(other)
        result,calls=analyze(other)
        self.assertEqual((result[0],calls),('done',0))
        with self.db() as con:
            reference=con.execute("SELECT * FROM skip_records WHERE source='device'").fetchone()
            review_record(con,reference,'approve',reference['start_ms'],reference['end_ms'],False)
            self.assertFalse(con.execute('SELECT 1 FROM skip_auto_reference_checks').fetchone())
        third=self.descriptor('85',15);self.registered(third)
        self.assertEqual(analyze(third)[1],1)


if __name__=='__main__': unittest.main()
