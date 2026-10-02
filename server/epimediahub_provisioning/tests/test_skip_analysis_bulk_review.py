"""Series/season approvals against real SQLite and Flask, including all pages."""
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from test_skip_analysis_dashboard import DashboardFixture, automation_tests
import skip_markers as markers
from skip_markers import add_record, install, now


@unittest.skipUnless(automation_tests.REAL_FLASK, 'Flask required for bulk review API')
class BulkReviewTests(DashboardFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        from flask import redirect
        site = automation_tests.REAL_FLASK('bulk-review-fixture', template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        site.secret_key = 'fixture-session-only'
        site.testing = True
        self.authenticated = True
        with self.db() as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture customer'")
        @site.get('/dashboard', endpoint='dashboard')
        def dashboard():
            return 'Dashboard'
        @site.get('/health', endpoint='health')
        def health():
            return site.response_class(json.dumps({'status': 'ok'}), mimetype='application/json')
        backend = types.ModuleType('app')
        backend.digest = lambda value: value
        backend.web_auth = lambda: None if self.authenticated else redirect('/admin/login')
        with mock.patch.dict(sys.modules, {'app': backend}):
            install(site, self.db)
        self.client = site.test_client()
        with self.client.session_transaction() as session:
            session['skip_csrf'] = 'fixture-csrf'

    def approve(self, season=None, **fields):
        data = dict(csrf='fixture-csrf', source_key=self.seed['source_key'], scope='series' if season is None else 'season',
                    return_page='1', return_episode_page='1')
        if season is not None:
            data['season'] = str(season)
        data.update(fields)
        return self.client.post('/admin/skip/bulk-review', data=data)

    def statuses(self):
        with self.db() as con:
            return dict(row[:] for row in con.execute('SELECT id,status FROM skip_records ORDER BY id'))

    def notice(self, response):
        self.assertEqual(response.status_code, 302)
        return parse_qs(urlsplit(response.headers['Location']).query)['notice'][0]

    def alternative(self, stream=1001, episode=1, start=10000, end=40000, disabled=False, source='audio', **changes):
        data = self.descriptor(str(stream), episode, **changes)
        with self.db() as con:
            row = add_record(con, data, 'intro', start, end, disabled, self.device, source=source, confidence=.95)
            con.execute('INSERT OR IGNORE INTO skip_auto_evidence VALUES(?,?,0)', (row['id'], '{}'))
        return row['id']

    def test_series_approval_includes_other_seasons_all_pages_and_all_segment_types(self):
        ids = []
        for episode in range(1, 31):
            ids.append(self.mark(1000 + episode, episode, kind='intro'))
            ids.append(self.mark(1000 + episode, episode, kind='outro'))
        ids.append(self.mark(2001, 1, season=3))
        other = self.mark(3001, 1, source_key='c' * 64)
        self.assertIn('61 Zeitmarken freigegeben', self.notice(self.approve()))
        statuses = self.statuses()
        self.assertTrue(all(statuses[record] == 'approved' for record in ids))
        self.assertEqual(statuses[other], 'pending')

    def test_season_approval_stays_in_exact_source_and_season_including_specials(self):
        special = self.mark(1001, 1, season=0)
        second = self.mark(1002, 1, season=2)
        third = self.mark(1003, 1, season=3)
        other = self.mark(1004, 1, season=0, source_key='c' * 64)
        self.notice(self.approve(season=0))
        self.assertEqual(self.statuses(), {special: 'approved', second: 'pending', third: 'pending', other: 'pending'})

    def test_different_file_versions_can_both_be_approved(self):
        first = self.mark(1001, 1)
        second = self.mark(1002, 1)
        self.assertIn('2 Zeitmarken freigegeben', self.notice(self.approve(season=2)))
        self.assertEqual(self.statuses(), {first: 'approved', second: 'approved'})

    def test_repeated_nearby_proposals_publish_one_marker_and_archive_duplicates(self):
        ids = [self.alternative(start=10000 + shift, end=40000 + shift) for shift in (0, 100, 200, 300)]
        notice = self.notice(self.approve())
        self.assertIn('1 Zeitmarken freigegeben', notice)
        self.assertIn('3 doppelte Vorschläge zusammengeführt', notice)
        values = [self.statuses()[record] for record in ids]
        self.assertEqual(values.count('approved'), 1)
        self.assertEqual(values.count('superseded'), 3)

    def test_conflicting_times_stay_pending_but_other_episodes_are_approved(self):
        first = self.alternative()
        second = self.alternative(start=60000, end=90000)
        other = self.mark(1002, 2)
        notice = self.notice(self.approve())
        self.assertIn('2 widersprüchliche Vorschläge bleiben zur Einzelprüfung', notice)
        self.assertEqual(self.statuses(), {first: 'pending', second: 'pending', other: 'approved'})

    def test_conflicting_disable_marker_and_ordinary_marker_stay_pending(self):
        first = self.alternative()
        second = self.alternative(start=0, end=0, disabled=True)
        self.notice(self.approve())
        self.assertEqual(self.statuses(), {first: 'pending', second: 'pending'})

    def test_existing_approvals_rejections_and_blocks_are_preserved(self):
        for stream, status in ((1001, 'approved'), (1002, 'rejected')):
            record = self.mark(stream, stream - 1000)
            with self.db() as con:
                con.execute('UPDATE skip_records SET status=?,reviewed_at=? WHERE id=?', (status, 'previous-review', record))
            self.alternative(stream=stream, episode=stream - 1000, start=11000, end=41000)
        blocked = self.mark(1003, 3)
        with self.db() as con:
            row = con.execute('SELECT * FROM skip_records WHERE id=?', (blocked,)).fetchone()
            con.execute('INSERT INTO skip_auto_blocks VALUES(?,?,?,?)', (row['asset_key'], 'intro', row['duration_ms'], 'previous-block'))
            before = [row[:] for row in con.execute("SELECT * FROM skip_records WHERE status IN ('approved','rejected')")]
        notice = self.notice(self.approve())
        self.assertIn('3 Vorschläge mit bestehender Entscheidung unverändert', notice)
        with self.db() as con:
            self.assertEqual([row[:] for row in con.execute("SELECT * FROM skip_records WHERE status IN ('approved','rejected')")], before)
            self.assertEqual(con.execute('SELECT updated_at FROM skip_auto_blocks').fetchone()[0], 'previous-block')

    def test_pending_same_file_under_another_identity_is_not_silently_retired(self):
        first = self.alternative()
        other = self.alternative(source_key='c' * 64, start=60000, end=90000)
        self.notice(self.approve())
        self.assertEqual(self.statuses(), {first: 'pending', other: 'pending'})

    def test_invalid_time_ranges_are_not_approved(self):
        record = self.mark(1001, 1)
        with self.db() as con:
            con.execute('UPDATE skip_records SET end_ms=duration_ms+1 WHERE id=?', (record,))
        self.assertIn('1 ungültige Vorschläge bleiben zur Einzelprüfung', self.notice(self.approve()))
        self.assertEqual(self.statuses()[record], 'pending')

    def test_reviewed_evidence_and_fingerprint_invalidation_match_individual_review(self):
        record = self.alternative()
        with self.db() as con:
            con.execute('INSERT INTO skip_fingerprints VALUES(?,?,?,?,?,?)', (record, '[1,2]', 125.0, 10000, 30000, now()))
        self.notice(self.approve())
        with self.db() as con:
            self.assertEqual(con.execute('SELECT human_review FROM skip_auto_evidence WHERE record_id=?', (record,)).fetchone()[0], 1)
            self.assertFalse(con.execute('SELECT 1 FROM skip_fingerprints WHERE record_id=?', (record,)).fetchone())
            self.assertIsNotNone(con.execute('SELECT reviewed_at FROM skip_records WHERE id=?', (record,)).fetchone()[0])

    def test_only_approved_season_jobs_are_woken_and_audio_budget_is_preserved(self):
        self.registered(self.descriptor('1001', 1, season=2)); self.mark(1001, 1, season=2)
        self.registered(self.descriptor('1002', 1, season=3)); self.mark(1002, 1, season=3)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='no_reference',attempts=2")
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,96)', (now()[:10],))
        self.notice(self.approve(season=2))
        with self.db() as con:
            jobs = con.execute('SELECT season,status,attempts FROM skip_jobs JOIN skip_assets USING(asset_key) ORDER BY season').fetchall()
            self.assertEqual([row[:] for row in jobs], [(2, 'queued', 0), (3, 'no_reference', 2)])
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0], 96)

    def test_repeated_submission_is_idempotent_and_does_not_reset_jobs_again(self):
        self.registered(self.descriptor('1001', 1)); self.mark(1001, 1)
        self.notice(self.approve())
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='done',attempts=2")
        self.assertIn('0 Zeitmarken freigegeben', self.notice(self.approve()))
        with self.db() as con:
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:], ('done', 2))

    def test_atomic_failure_does_not_leave_partial_approvals(self):
        self.mark(1001, 1); self.mark(1002, 2)
        original = markers.review_record
        calls = 0
        def fail_on_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('fixture failure')
            return original(*args, **kwargs)
        with mock.patch.object(markers, 'review_record', side_effect=fail_on_second), self.assertRaises(RuntimeError):
            self.approve()
        self.assertEqual(set(self.statuses().values()), {'pending'})

    def test_bulk_route_requires_admin_csrf_and_valid_bounded_scope(self):
        self.mark(1001, 1)
        self.authenticated = False
        self.assertEqual(urlsplit(self.approve().headers['Location']).path, '/admin/login')
        self.authenticated = True
        for fields, status in (({'csrf': 'wrong'}, 403), ({'source_key': 'bad'}, 400),
                               ({'scope': 'everything'}, 400), ({'scope': 'season', 'season': '-1'}, 400),
                               ({'scope': 'season', 'season': '1001'}, 400), ({'source_key': 'd' * 64}, 404)):
            with self.subTest(fields=fields):
                self.assertEqual(self.approve(**fields).status_code, status)
        self.assertEqual(set(self.statuses().values()), {'pending'})

    def test_pending_series_and_seasons_have_buttons_with_whole_scope_counts(self):
        for episode in range(1, 31):
            self.mark(1000 + episode, episode)
        self.mark(2001, 1, season=3)
        body = self.client.get('/admin/skip', query_string={'series': self.seed['source_key'], 'season': 2}).get_data(as_text=True)
        self.assertIn('Alle Vorschläge dieser Serie freigeben (31)', body)
        self.assertIn('Alle Vorschläge dieser Staffel freigeben (30)', body)
        self.assertIn('Alle Vorschläge dieser Staffel freigeben (1)', body)
        self.assertIn('name="scope" value="season"', body)
        self.assertIn('name="csrf" value="fixture-csrf"', body)

    def test_other_filters_and_films_do_not_offer_series_bulk_buttons(self):
        record = self.mark(1001, 1)
        with self.db() as con:
            con.execute("UPDATE skip_records SET status='approved' WHERE id=?", (record,))
        body = self.client.get('/admin/skip', query_string={'state': 'approved', 'series': self.seed['source_key']}).get_data(as_text=True)
        self.assertNotIn('class="tools bulk-approval"', body)
        self.mark(1002, 0, season=0, media_type='movie', source_key='c' * 64)
        body = self.client.get('/admin/skip', query_string={'series': 'c' * 64}).get_data(as_text=True)
        self.assertNotIn('class="tools bulk-approval"', body)

    def test_redirect_keeps_the_selected_season_and_page(self):
        self.mark(1001, 1, season=2)
        response = self.approve(season=2, return_page='2', return_episode_page='3')
        query = parse_qs(urlsplit(response.headers['Location']).query)
        self.assertEqual((query['series'], query['season'], query['page'], query['episode_page']),
                         ([self.seed['source_key']], ['2'], ['2'], ['3']))
        self.assertEqual(urlsplit(response.headers['Location']).fragment, 'season-2')


if __name__ == '__main__':
    unittest.main()
