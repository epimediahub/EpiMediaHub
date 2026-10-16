"""Read-only EpiScene automation pilot report regressions."""
import sqlite3
import unittest

import automation_pilot_report as r


def dbs():
    p=sqlite3.connect(':memory:'); l=sqlite3.connect(':memory:')
    p.row_factory=sqlite3.Row
    l.row_factory=sqlite3.Row
    p.executescript("""
    CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,
      source_key TEXT,season INTEGER,media_type TEXT);
    CREATE TABLE skip_jobs(id INTEGER,asset_key TEXT,status TEXT);
    CREATE TABLE skip_records(id INTEGER,asset_key TEXT,segment_type TEXT,
      status TEXT,source TEXT,disabled INTEGER);
    CREATE TABLE skip_auto_evidence(record_id INTEGER,human_review INTEGER);
    INSERT INTO skip_assets VALUES
      ('a',8,'series-secret',1,'episode'),
      ('b',8,'series-secret',1,'episode'),
      ('c',8,'series-secret',1,'episode'),
      ('x',10,'other',1,'episode');
    INSERT INTO skip_jobs VALUES
      (1,'a','done'),(2,'b','queued'),(3,'c','review');
    INSERT INTO skip_records VALUES
      (1,'a','intro','approved','device',0),
      (2,'b','intro','pending','episcene',0),
      (3,'c','intro','approved','episcene',0);
    INSERT INTO skip_auto_evidence VALUES(3,0);
    """)
    l.executescript("""
    CREATE TABLE shadow_calibrations(playlist_id INTEGER,source_key TEXT,
      season INTEGER,kind TEXT,machine_source TEXT,
      independent_episodes INTEGER,loo_median_start_error_ms INTEGER,
      status TEXT,auto_publish_allowed INTEGER);
    CREATE TABLE feedback_versions(decision TEXT,active INTEGER);
    INSERT INTO shadow_calibrations VALUES
      (8,'series-secret',1,'intro','episcene',5,1400,'SHADOW_ONLY',0);
    INSERT INTO feedback_versions VALUES('positive',1),('positive',1),
      ('negative',1),('negative',0);
    """)
    return p,l


class TestAutonomyPilot(unittest.TestCase):
    def test_matches_training_groups_without_publishing(self):
        p,l=dbs()
        before=p.total_changes
        data=r.report(p,l)
        self.assertEqual(data['active_verified_labels'],{'positive':2,'negative':1})
        self.assertEqual(data['negative_training'],1)
        self.assertEqual(data['source_model_counts'],{'8':1})
        self.assertIn('NO_LEARNED_MODEL_FOR_ANALYSIS_PLAYLIST_10',
                      data['automatic_model_publication_blockers'])
        self.assertEqual(data['pilot_summary']['pilot_model_groups'],1)
        self.assertEqual(data['pilot_summary']['episodes'],3)
        self.assertEqual(data['pilot_summary']['human_references'],1)
        self.assertEqual(data['pilot_summary']['machine_approved'],1)
        self.assertEqual(data['pilot_summary']['machine_pending'],1)
        self.assertEqual(data['pilot_summary']['jobs_waiting_or_active'],1)
        self.assertEqual(data['pilot_summary']['jobs_finished_or_review'],2)
        self.assertFalse(data['production_modified'])
        self.assertEqual(data['new_markers_approved'],0)
        self.assertEqual(p.total_changes,before)
        self.assertNotIn('series-secret',str(data))

    def test_never_accepts_model_with_autopublish_flag(self):
        p,l=dbs()
        l.execute('UPDATE shadow_calibrations SET auto_publish_allowed=1')
        data=r.report(p,l)
        self.assertEqual(data['pilot_summary'].get('pilot_model_groups',0),0)
        self.assertEqual(data['pilot_summary']['models_not_eligible_for_pilot'],1)

    def test_all_positive_labels_are_not_a_safety_clearance(self):
        p,l=dbs()
        l.execute("UPDATE feedback_versions SET active=0 WHERE decision='negative'")
        data=r.report(p,l)
        self.assertEqual(data['negative_training'],0)
        self.assertIn('NO_VERIFIED_NEGATIVE_TRAINING_EXAMPLES',
                      data['automatic_model_publication_blockers'])
        self.assertEqual(data['new_markers_approved'],0)

    def test_human_reviewed_machine_is_reference(self):
        p,l=dbs()
        p.execute('UPDATE skip_auto_evidence SET human_review=1 WHERE record_id=3')
        data=r.report(p,l)
        self.assertEqual(data['pilot_summary']['human_references'],2)
        self.assertEqual(data['pilot_summary'].get('machine_approved',0),0)


if __name__=='__main__':
    unittest.main()
