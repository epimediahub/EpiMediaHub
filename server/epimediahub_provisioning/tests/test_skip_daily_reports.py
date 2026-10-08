"""Real SQLite history, DST, restarts, security and original dashboard integration."""
import concurrent.futures
from datetime import datetime
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest import mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from test_skip_analysis_references import ReferenceFixture
import skip_daily_reports as reports
from skip_markers import add_record


class Reports(ReferenceFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        with self.db() as con:
            reports.migrate(con)
            con.execute("UPDATE episcene_report_meta SET value='0' WHERE name='collection_started'")
            d = self.seed
            con.execute('INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                tuple(d[k] for k in ('asset_key','source_key','playlist_id','stream_id','extension','media_type',
                                    'duration_ms','season','episode','title','year')) + ('2026-10-08T00:00:00Z',))
            con.execute("INSERT INTO skip_jobs(asset_key,created_at,updated_at) VALUES(?,?,?)",
                (d['asset_key'],'2026-10-08T00:00:00Z','2026-10-08T00:00:00Z'))
        self.day = reports.due_day().isoformat()
        self.start,self.end = reports.period(self.day)
        self.at = self.end.timestamp()+10

    def event_time(self):
        with self.db() as con:
            con.execute('UPDATE episcene_report_events SET at=?', (self.end.timestamp()-60,))

    def attempt(self,status='done',detail='ok'):
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='running'")
            con.execute('UPDATE episcene_report_active SET started=?', (time.time()-30,))
            con.execute('UPDATE skip_jobs SET status=?,attempts=attempts+1,detail=?', (status,detail))
        self.event_time()

    def report(self):
        with self.db() as con:
            return reports.build_report(con,self.day,self.at)

    def test_retries_are_not_counted_as_new_episodes(self):
        self.attempt('failed','timeout')
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='queued'")
        self.attempt()
        r=self.report()
        self.assertEqual((r['summary']['attempts'],r['summary']['episodes'],r['summary']['series']),(2,1,1))
        self.assertEqual(r['summary']['outcomes'],{'failed':1,'done':1})
        self.assertAlmostEqual(r['summary']['seconds'],60,delta=.1)
        self.assertEqual(r['series'][0]['episodes'][0]['status'],'done')

    def test_pause_and_unknown_start_do_not_fabricate_runtime(self):
        self.attempt('queued')
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='running'")
            con.execute('DELETE FROM episcene_report_active')
            con.execute("UPDATE skip_jobs SET status='failed'")
        self.event_time()
        r=self.report()['summary']
        self.assertEqual((r['interrupted'],r['attempts'],r['runtime_samples']),(1,1,0))
        self.assertIsNone(r['median_seconds'])

    def test_evidence_written_after_marker_captures_automatic_and_manual_decisions(self):
        with self.db() as con:
            row=add_record(con,self.seed,'intro',10000,60000,False,source='episcene',confidence=.97)
            rid=row['id']
            con.execute('INSERT INTO skip_auto_evidence VALUES(?,?,0)', (rid,json.dumps({'method':'episcene_consensus','automatic_acceptance':True})))
            con.execute("UPDATE skip_records SET status='approved' WHERE id=?",(rid,))
            con.execute('UPDATE skip_records SET start_ms=11000 WHERE id=?',(rid,))
            con.execute('UPDATE skip_auto_evidence SET human_review=1 WHERE record_id=?',(rid,))
        self.event_time()
        r=self.report()
        self.assertEqual(r['summary']['proposals'],1)
        self.assertEqual(r['summary']['automatic_approvals'],1)
        self.assertEqual(r['summary']['corrections'],1)
        self.assertEqual(r['markers'][-1]['payload']['before']['start_ms'],10000)

    def test_later_marker_edit_does_not_rewrite_yesterday(self):
        with self.db() as con:
            row=add_record(con,self.seed,'intro',10000,60000,False)
        self.event_time()
        old=self.report()
        with self.db() as con:
            con.execute('UPDATE skip_records SET start_ms=20000 WHERE id=?',(row['id'],))
            con.execute('UPDATE episcene_report_events SET at=? WHERE id=(SELECT MAX(id) FROM episcene_report_events)',(self.end.timestamp()+1,))
        self.assertEqual(old,self.report())

    def test_daily_boundaries_are_half_open_and_timezone_aware(self):
        self.attempt()
        with self.db() as con:
            con.execute("UPDATE episcene_report_events SET at=? WHERE kind='job'",(self.end.timestamp(),))
        self.assertEqual(self.report()['summary']['attempts'],0)
        with self.db() as con:
            con.execute("UPDATE episcene_report_events SET at=? WHERE kind='job'",(self.start.timestamp(),))
        self.assertEqual(self.report()['summary']['attempts'],1)
        for day,hours in [('2026-03-29',23),('2026-10-25',25),('2026-10-08',24)]:
            start,end=reports.period(day)
            self.assertEqual((end.timestamp()-start.timestamp())/3600,hours)
            self.assertEqual(reports.due_day(end.timestamp()-1).isoformat(),start.date().isoformat())
            self.assertEqual(reports.due_day(end.timestamp()).isoformat(),day)

    def test_partial_coverage_is_explicit_and_no_prehistory_is_invented(self):
        with self.db() as con:
            con.execute("UPDATE episcene_report_meta SET value=? WHERE name='collection_started'",(str(self.end.timestamp()+30),))
        r=self.report()
        self.assertFalse(r['complete'])
        self.assertEqual(r['summary']['attempts'],0)
        self.assertIn('Unvollständiger Zeitraum',r['findings'][0])

    def test_migration_is_idempotent_and_preserves_business_rows(self):
        with self.db() as con:
            before=[tuple(r) for r in con.execute('SELECT * FROM skip_jobs')]
            reports.migrate(con); reports.migrate(con)
            self.assertEqual(before,[tuple(r) for r in con.execute('SELECT * FROM skip_jobs')])
        self.attempt()
        self.assertEqual(self.report()['summary']['attempts'],1)

    def test_reports_are_immutable_and_missing_days_are_caught_up(self):
        with self.db() as con:
            con.execute("UPDATE episcene_report_meta SET value=? WHERE name='collection_started'",(str(self.start.timestamp()-86400),))
        self.attempt()
        generated=reports.generate_due(self.db,self.at)
        self.assertEqual(len(generated),3)
        with self.db() as con:
            original=reports.read_report(con,self.day)
        self.attempt('failed')
        self.assertEqual(reports.generate_due(self.db,self.at),[])
        with self.db() as con:
            self.assertEqual(original,reports.read_report(con,self.day))

    def test_concurrent_generators_publish_only_one_report_per_day(self):
        with self.db() as con:
            con.execute("UPDATE episcene_report_meta SET value=? WHERE name='collection_started'",(str(self.end.timestamp()-3600),))
        self.attempt()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _:reports.generate_due(self.db,self.at),range(2)))
        with self.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM episcene_daily_reports').fetchone()[0],1)

    def test_export_removes_urls_and_credentials_in_nested_evidence_and_titles(self):
        self.attempt('failed','upstream https://name:secret@provider.invalid/series/user/pass password=TOP_SECRET')
        with self.db() as con:
            row=add_record(con,self.seed,'intro',10000,60000,False)
            con.execute('INSERT INTO skip_auto_evidence VALUES(?,?,0)', (row['id'],json.dumps({
                'authorization':'TOP_SECRET','nested':{'stream_url':'https://provider.invalid/TOP_SECRET'},
                'score':.99})))
        self.event_time()
        exported=reports.encode(self.report())
        self.assertNotIn('TOP_SECRET',exported)
        self.assertNotIn('provider.invalid',exported)
        self.assertIn('0.99',exported)

    def test_report_does_not_read_credentials_from_playlist_config(self):
        self.attempt()
        self.assertNotIn('TEST_PROVIDER_SECRET',reports.encode(self.report()))

    def test_admin_routes_are_guarded_and_html_escapes_titles(self):
        from flask import Flask,session,redirect
        folder=Path(__file__).resolve().parents[1]
        app=Flask('report-fixture',template_folder=str(folder/'templates'))
        app.secret_key='fixture-only'
        @app.get('/admin/skip',endpoint='v082_skip_dashboard')
        def dashboard():return 'dashboard'
        backend=types.ModuleType('app')
        backend.web_auth=lambda:None if session.get('admin') else redirect('/login')
        with mock.patch.dict(sys.modules,{'app':backend}),mock.patch('skip_report_telemetry.install'):
            reports.install(app,self.db)
        with self.db() as con:
            con.execute("UPDATE episcene_report_meta SET value=? WHERE name='collection_started'",(str(self.end.timestamp()-3600),))
            con.execute('UPDATE skip_assets SET title=?',('<script>alert(1)</script>',))
        self.attempt()
        reports.generate_due(self.db,self.at)
        client=app.test_client()
        for path in ['/admin/skip/reports','/admin/skip/reports/latest',f'/admin/skip/reports/{self.day}.json']:
            self.assertEqual(client.get(path).status_code,302)
        with client.session_transaction() as s:s['admin']=True
        page=client.get('/admin/skip/reports')
        self.assertEqual(page.status_code,200)
        self.assertNotIn('<script>alert(1)</script>',page.text)
        self.assertIn('&lt;script&gt;',page.text)
        self.assertEqual(client.get('/admin/skip/reports?day=2099-01-01').status_code,404)
        data=client.get(f'/admin/skip/reports/{self.day}.json')
        self.assertEqual(data.headers['Cache-Control'],'no-store')
        self.assertEqual(data.json['summary']['attempts'],1)


if __name__=='__main__':unittest.main()
