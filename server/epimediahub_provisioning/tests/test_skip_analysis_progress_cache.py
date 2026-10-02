"""Incremental progress, concurrent publications and actual cache read cost."""
from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_skip_analysis_references import ReferenceFixture
from skip_database import connect, enable_wal
import skip_progress as progress
from skip_markers import review_record


class CacheTests(ReferenceFixture, unittest.TestCase):
    def db(self):
        return connect(self.db_path)

    def setUp(self):
        super().setUp()
        with self.db() as con:
            enable_wal(con)
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Customer'")
        self.waiting(status='done')

    def item(self, **params):
        with self.db() as con:
            return progress.overview(con, **params)['rows'][0]

    def test_warm_pages_and_filters_do_not_read_episode_or_marker_tables(self):
        self.marker(self.target)
        with self.db() as con:
            progress.populate(con)
            def guard(action, table, *_):
                if action == sqlite3.SQLITE_READ and table in ('skip_assets','skip_records','skip_catalogue_episodes'):
                    return sqlite3.SQLITE_DENY
                return sqlite3.SQLITE_OK
            con.set_authorizer(guard)
            for params in ({}, dict(selected='with_intro'), dict(selected='completed'), dict(search='Lie to Me'), dict(page=2)):
                result=progress.overview(con, **params)
                self.assertEqual(result['totals']['files'],1)
                self.assertEqual(result['rows'][0]['intros'],1)

    def test_new_job_status_and_player_correction_refresh_their_series(self):
        record=self.marker(self.target)
        self.assertEqual(self.item()['intros'],1)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='failed'")
            row=con.execute('SELECT * FROM skip_records WHERE id=?',(record,)).fetchone()
            review_record(con,row,'approve',0,0,True)
        item=self.item()
        self.assertEqual((item['failed'],item['intros'],item['disabled']),(1,0,1))
        self.assertFalse(item['complete'])

    def test_pending_intro_is_removed_when_approved_or_deleted(self):
        record=self.marker(self.target,status='pending')
        self.assertEqual(self.item()['pending'],1)
        with self.db() as con:
            con.execute("UPDATE skip_records SET status='approved' WHERE id=?",(record,))
        self.assertEqual((self.item()['pending'],self.item()['intros']),(0,1))
        with self.db() as con:
            con.execute('DELETE FROM skip_records WHERE id=?',(record,))
        self.assertEqual(self.item()['intros'],0)

    def test_runtime_and_source_reassignment_remove_stale_coverage_and_empty_groups(self):
        self.marker(self.target)
        self.assertEqual(self.item()['intros'],1)
        with self.db() as con:
            con.execute("UPDATE skip_assets SET duration_ms=duration_ms+10000")
        self.assertEqual(self.item()['intros'],0)
        with self.db() as con:
            con.execute("UPDATE skip_assets SET source_key=?,title='Different series'",('c'*64,))
            result=progress.overview(con)
        self.assertEqual(result['total'],1)
        self.assertEqual(result['rows'][0]['source_key'],'c'*64)

    def test_inventory_status_and_episode_membership_are_refreshed(self):
        self.assertTrue(self.item()['complete'])
        with self.db() as con:
            con.execute("INSERT INTO skip_catalogue_series VALUES(1,'501','{}','sig',0,1,1,0,'','')")
            con.execute('INSERT INTO skip_catalogue_episodes VALUES(?,?,?,?,?)',(1,'501',self.target['asset_key'],'sig',1))
        self.assertFalse(self.item()['complete'])
        with self.db() as con:
            con.execute("UPDATE skip_catalogue_series SET pending_generation=0,status='ok'")
        self.assertTrue(self.item()['complete'])
        with self.db() as con:
            con.execute("UPDATE skip_catalogue_series SET status='failed'")
        self.assertFalse(self.item()['complete'])
        with self.db() as con:
            con.execute('DELETE FROM skip_catalogue_episodes')
        self.assertTrue(self.item()['complete'])

    def test_names_analysis_preferences_and_customer_state_are_read_live(self):
        self.item()
        with self.db() as con:
            con.execute("UPDATE customer_playlists SET name='Neue Playlist' WHERE id=1")
            con.execute("UPDATE customers SET name='Neuer Kunde',enabled=0 WHERE id=1")
            con.execute("UPDATE skip_jobs SET status='queued'")
        item=self.item(search='Neue Playlist')
        self.assertEqual((item['playlist_name'],item['customer_name'],item['status']),('Neue Playlist','Neuer Kunde','Analyse pausiert'))

    def test_unchanged_player_registration_does_not_invalidate_warm_progress(self):
        from skip_analysis import register_asset
        self.item()
        with self.db() as con:
            self.assertTrue(register_asset(con,self.target,self.target,self.device))
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0],0)

    def test_deleting_playlist_preserves_customer_deletion_and_cleans_cached_rows(self):
        self.item()
        with self.db() as con:
            con.execute('DELETE FROM customer_playlists WHERE id=1')
            result=progress.overview(con)
            self.assertEqual(result['totals']['series'],0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0],0)

    def test_late_committed_change_is_not_erased_by_a_stale_refresh(self):
        self.item()
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='queued'")
        original=progress._metrics
        def concurrent(reader,playlist,source):
            result=original(reader,playlist,source)
            with self.db() as writer:
                writer.execute("UPDATE skip_jobs SET status='failed'")
            return result
        with self.db() as con, mock.patch.object(progress,'_metrics',side_effect=concurrent):
            self.assertEqual(progress.refresh(con),0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0],1)
        self.assertEqual(self.item()['failed'],1)

    def test_another_refresh_then_a_new_change_cannot_reuse_a_cleaned_revision(self):
        self.item()
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='queued'")
        original=progress._metrics
        raced=False
        def concurrent(reader,playlist,source):
            nonlocal raced
            result=original(reader,playlist,source)
            if not raced:
                raced=True
                with self.db() as writer:
                    progress.refresh(writer)
                    writer.execute("UPDATE skip_jobs SET status='done'")
            return result
        with self.db() as con, mock.patch.object(progress,'_metrics',side_effect=concurrent):
            self.assertEqual(progress.refresh(con),0)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0],1)
        self.assertTrue(self.item()['complete'])

    def test_bounded_refresh_keeps_other_series_pending_and_prioritizes_selection(self):
        for n in range(5):
            data=self.descriptor(str(200+n),1,source_key=hashlib.sha256(str(n).encode()).hexdigest(),title=f'Serie {n}')
            self.waiting(data,status='done')
        with self.db() as con:
            self.assertEqual(progress.refresh(con,limit=1,budget=None,preferred_source=data['source_key']),1)
            self.assertEqual(con.execute('SELECT source_key FROM skip_progress_series').fetchone()[0],data['source_key'])
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0],5)
            progress.populate(con)
            self.assertEqual(progress.overview(con)['total'],6)

    def test_warmed_snapshot_checker_reports_phase_timings_and_preserves_live_dirty_state(self):
        from deploy.check_skip_dashboard import check
        with self.db() as con:
            before=con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0]
        timings=check(self.db_path,Path(__file__).resolve().parents[1]/'templates')
        self.assertEqual(set(timings),{'snapshot','progress','render'})
        self.assertTrue(all(t>=0 for t in timings.values()))
        with self.db() as con:
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_progress_dirty').fetchone()[0],before)


if __name__=='__main__':
    unittest.main()
