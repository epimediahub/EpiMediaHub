#!/usr/bin/env python3
"""Comprehensive EpiScene diagnostics must never change source data or print PII."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import one_report as d


def fixture(root):
    original=root/'provisioning.db'
    db=sqlite3.connect(original)
    db.executescript("""
        CREATE TABLE skip_records(
          id INTEGER PRIMARY KEY,asset_key TEXT,source TEXT,source_key TEXT,
          status TEXT,segment_type TEXT,device_id INTEGER,customer_id INTEGER,
          media_type TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER,
          title TEXT,start_ms INTEGER,end_ms INTEGER,disabled INTEGER);
        CREATE TABLE devices(id INTEGER PRIMARY KEY,customer_id INTEGER,enabled INTEGER);
        CREATE TABLE customers(id INTEGER PRIMARY KEY,enabled INTEGER);
        CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,customer_id INTEGER);
        CREATE TABLE skip_assets(
          asset_key TEXT PRIMARY KEY,playlist_id INTEGER,source_key TEXT,
          media_type TEXT,season INTEGER,episode INTEGER,duration_ms INTEGER,title TEXT);
        CREATE TABLE skip_analysis_playlists(id INTEGER PRIMARY KEY,archived INTEGER,enabled INTEGER,paused INTEGER);\n        CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
        CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER);
        CREATE TABLE skip_release_settings(playlist_id INTEGER,enabled INTEGER);
        CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT);
        CREATE TABLE skip_jobs(
          id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,attempts INTEGER,updated_at TEXT);
        CREATE TABLE skip_presence(playlist_id INTEGER,expires_at INTEGER);
        CREATE TABLE episcene_safe_release_retries(
          asset_key TEXT PRIMARY KEY,last_requeued_utc TEXT,attempt_count INTEGER,
          original_job_status TEXT);
        INSERT INTO skip_analysis_playlists VALUES(8,0,1,0),(10,0,1,0);\n        INSERT INTO customers VALUES(12,1);
        INSERT INTO customer_playlists VALUES(8,12),(10,12);
        INSERT INTO devices VALUES(1,12,1);
        INSERT INTO skip_analysis_sources VALUES(8,1),(10,1);
        INSERT INTO skip_auto_settings VALUES(8,1),(10,1);
        INSERT INTO skip_release_settings VALUES(8,1),(10,1);
        INSERT INTO skip_assets VALUES('good',8,'series','episode',1,1,2400000,'MobLand');
        INSERT INTO skip_assets VALUES('machine',8,'series','episode',1,2,2400000,'MobLand');
        INSERT INTO skip_records VALUES(1,'good','device','series','pending','intro',NULL,12,'episode',1,1,2400000,'MobLand',30000,60000,0);
        INSERT INTO skip_records VALUES(2,'unlinked','device','series','pending','intro',1,12,'episode',1,3,2400000,'MobLand',30000,60000,0);
        INSERT INTO skip_records VALUES(3,'good','device','series','approved','outro',1,12,'episode',1,1,2400000,'MobLand',2300000,2390000,0);
        INSERT INTO skip_records VALUES(4,'machine','audio_repetition','series','pending','outro',NULL,NULL,'episode',1,2,2400000,'MobLand',2335000,2390000,0);
        INSERT INTO skip_auto_evidence VALUES(4,'{"episcene_required":true}');
        INSERT INTO skip_jobs VALUES(42,'machine','review',2,'2026-10-14T19:00:00Z');
    """)
    db.commit()
    db.close()
    return original


class Diagnostics(unittest.TestCase):
    def test_ownership_missing_device_and_missing_asset_are_separate(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            before=original.read_bytes()
            with d.open_readonly(original) as db:
                result=d.ownership(db)
            self.assertEqual(result['pending_manual'],2)
            self.assertEqual(result['first_failure']['MISSING_DEVICE_ID'],1)
            self.assertEqual(result['first_failure']['UNLINKED_MEDIA_ASSET'],1)
            self.assertEqual(result['active_device_but_missing_asset'],1)
            self.assertEqual(original.read_bytes(),before)

    def test_visual_requeue_funnel_recognizes_sibling_reference(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            with d.open_readonly(original) as db:
                result=d.queue_funnel(db)
            self.assertEqual(result['counts']['potential_job_marker_pairs'],1)
            self.assertEqual(result['counts']['distinct_assets_considered'],1)
            self.assertEqual(result['first_queue_requeue_blockers']['PASSES_ALL_BEFORE_DAILY_QUOTAS'],1)
            with sqlite3.connect(original) as db:
                db.execute("UPDATE skip_records SET status='pending' WHERE id=3")
            with d.open_readonly(original) as db:
                no_ref=d.queue_funnel(db)
            self.assertEqual(no_ref['first_queue_requeue_blockers']['NO_APPROVED_SAME_SOURCE_SEASON_KIND_SIBLING'],1)

    def test_reason_counts_do_not_pretend_autoapproval(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            with d.open_readonly(original) as db:
                result=d.evidence_breakdown(db)
            self.assertEqual(result['machine_status']['pending'],1)
            self.assertEqual(result['first_evidence_categories']['MISSING_SCENE_CONSENSUS'],1)
            self.assertEqual(result['distinct_pending_records'],1)
            self.assertEqual(result['distinct_pending_assets'],1)
            self.assertEqual(result['distinct_pending_by_analysis_playlist']['8'],{'records':1,'assets':1})

    def test_failed_release_toggle_detected_in_single_report(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            with sqlite3.connect(original) as db:
                db.execute('UPDATE skip_release_settings SET enabled=0 WHERE playlist_id=8')
            with d.open_readonly(original) as db:
                result=d.queue_funnel(db)
            self.assertEqual(result['first_queue_requeue_blockers']['AUTOMATIC_RELEASE_OFF'],1)

    def test_independent_inventory_keeps_sources_distinct_from_customer_records(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            with d.open_readonly(original) as db:
                info=d.analysis_inventory(db)
                self.assertTrue(info['analysis_inventory_present'])
                self.assertEqual(info['missing_from_independent_inventory'],[])
                self.assertEqual(info['expected_analysis_sources']['8']['assets'],2)
                self.assertTrue(info['customer_playlist_lookup_is_inapplicable_to_independent_sources'])
                funnel=d.independent_visual_funnel(db)
                self.assertEqual(funnel['candidate_assets_eligible_before_budget'],1)
                self.assertEqual(funnel['first_visible_blocker_counts']['REQUEUE_ELIGIBLE_BEFORE_BUDGET_AND_RATE'],1)

    def test_archived_independent_source_prevents_fresh_visual_analysis(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            with sqlite3.connect(original) as db:
                db.execute('UPDATE skip_analysis_playlists SET archived=1 WHERE id=8')
            with d.open_readonly(original) as db:
                result=d.independent_visual_funnel(db)
            self.assertEqual(result['candidate_assets_eligible_before_budget'],0)
            self.assertEqual(result['first_visible_blocker_counts']['SOURCE_ARCHIVED'],1)

    def test_no_assumption_that_analysis_inventory_matches_customer_table(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            with sqlite3.connect(original) as db:
                db.execute('DELETE FROM customer_playlists')
            with d.open_readonly(original) as db:
                info=d.analysis_inventory(db)
                self.assertEqual(info['missing_from_independent_inventory'],[])
                self.assertEqual(info['expected_analysis_sources']['8']['assets'],2)

    def test_no_machine_customer_or_provider_data_in_report(self):
        with tempfile.TemporaryDirectory() as td:
            original=fixture(Path(td))
            before=original.read_bytes()
            with mock.patch.object(d,'learning',return_value={'test':'ok'}), \
                 mock.patch.object(d,'services',return_value={'test.timer':'active'}):
                with d.open_readonly(original) as db:
                    report=d.report(db)
            output=json.dumps(report)
            self.assertNotIn('MobLand',output)
            self.assertNotIn('series',output)
            self.assertNotIn('unlinked',output)
            self.assertNotIn('good',output)
            self.assertFalse(report['production_db_modified'])
            self.assertEqual(report['auto_approvals_triggered'],0)
            self.assertEqual(original.read_bytes(),before)


if __name__=='__main__':
    unittest.main(verbosity=2)
