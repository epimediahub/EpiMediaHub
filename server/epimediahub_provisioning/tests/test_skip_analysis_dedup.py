"""Consolidated proposals, migration of old jobs and high-score publication safeguards."""
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_skip_analysis_automation as fixtures
from skip_markers import add_record, now
import skip_automation as auto


class ProposalTests(fixtures.AutomationFixture, unittest.TestCase):
    def test_four_near_identical_reference_matches_keep_one_stable_best_proposal(self):
        with self.db() as con:
            ids = [auto.store_proposal(con, self.target, 'intro', 48000+shift, 74530+shift, 'audio', score)['id']
                   for shift, score in ((0,.92),(125,.937),(250,.95),(150,.93))]
            rows = con.execute("SELECT * FROM skip_records WHERE asset_key=?", (self.target['asset_key'],)).fetchall()
            self.assertEqual(len(set(ids)), 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual((rows[0]['start_ms'],rows[0]['end_ms'],rows[0]['confidence']), (48250,74780,.95))

    def test_matching_online_chapter_and_audio_results_share_one_proposal(self):
        with self.db() as con:
            online = auto.store_proposal(con, self.target, 'intro', 48000, 74530, 'theintrodb')
            chapter = auto.store_proposal(con, self.target, 'intro', 48000, 74530, 'chapter')
            audio = auto.store_proposal(con, self.target, 'intro', 48100, 74630, 'audio', .937)
            self.assertEqual((online['id'],chapter['id']), (audio['id'],audio['id']))
            self.assertEqual((audio['source'],audio['confidence']), ('audio',.937))

    def test_conflicting_boundaries_files_runtimes_and_segment_types_stay_separate(self):
        other = self.descriptor('84', self.target['episode'])
        with self.db() as con:
            for data, kind, start in ((self.target,'intro',48000), (self.target,'intro',50000),
                                      (other,'intro',48000), (self.target | {'duration_ms':self.target['duration_ms']+1},'intro',48000),
                                      (self.target,'recap',48000)):
                auto.store_proposal(con, data, kind, start, start+26530, 'audio', .937)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0], 5)

    def test_own_pending_marker_and_rejection_block_generated_replacement(self):
        self.marker(self.target, status='pending')
        with self.db() as con:
            self.assertIsNone(auto.store_proposal(con, self.target, 'intro', 48000,74530,'audio',.99))
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],1)
            con.execute("UPDATE skip_records SET status='rejected'")
            self.assertIsNone(auto.store_proposal(con, self.target, 'intro', 48000,74530,'audio',.99))
            self.assertEqual(con.execute('SELECT source,status FROM skip_records').fetchone()[:],('device','rejected'))

    def test_existing_pending_duplicates_archive_only_matching_machine_records(self):
        with self.db() as con:
            for shift, score in ((0,.92),(100,.937),(200,.95),(250,.93)):
                add_record(con,self.target,'intro',48000+shift,74530+shift,False,source='audio',confidence=score)
            add_record(con,self.target,'intro',52000,78530,False,source='audio',confidence=.93)
            kept = auto.consolidate_proposals(con,self.target,'intro')
            self.assertEqual(len(kept),2)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE status='superseded'").fetchone()[0],3)
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],5)

    def test_pending_human_reviewed_record_is_not_folded_into_machine_result(self):
        with self.db() as con:
            human = add_record(con,self.target,'intro',48000,74530,False,source='audio')['id']
            con.execute("INSERT INTO skip_auto_evidence VALUES(?,'{}',1)",(human,))
            self.assertIsNone(auto.store_proposal(con,self.target,'intro',48100,74630,'audio',.937))
            self.assertEqual(con.execute('SELECT start_ms,confidence FROM skip_records WHERE id=?',(human,)).fetchone()[:],(48000,1.0))
            self.assertEqual(con.execute('SELECT COUNT(*) FROM skip_records').fetchone()[0],1)


class MaintenanceTests(fixtures.AutomationFixture, unittest.TestCase):
    def old_job(self, confidence=.937):
        self.registered(self.target)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='review',attempts=2,detail='old result'")
            for shift in (0,125,250,375):
                add_record(con,self.target,'intro',48000+shift,74530+shift,False,source='audio',confidence=confidence)
            con.execute('DELETE FROM skip_auto_maintenance WHERE name=?',(auto.POLICY_VERSION,))

    def test_cleanup_requeues_existing_high_matches_without_approving_from_old_scores(self):
        self.old_job()
        with self.db() as con:
            con.execute('INSERT INTO skip_analysis_budget VALUES(?,96)',(now()[:10],))
            auto.migrate(con)
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:],('queued',0))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE status='pending'").fetchone()[0],1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE status='approved'").fetchone()[0],0)
            self.assertEqual(con.execute('SELECT count FROM skip_analysis_budget').fetchone()[0],96)
            con.execute("UPDATE skip_jobs SET status='review',attempts=1")
            auto.migrate(con)
            self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:],('review',1))

    def test_cleanup_does_not_restart_disabled_or_weak_results(self):
        for confidence, disabled in ((.91,False),(.937,True)):
            with self.subTest(confidence=confidence,disabled=disabled):
                with self.db() as con:
                    con.execute('DELETE FROM skip_records')
                self.old_job(confidence)
                with self.db() as con:
                    con.execute('UPDATE skip_auto_settings SET enabled=?',(0 if disabled else 1,))
                    auto.migrate(con)
                    self.assertEqual(con.execute('SELECT status,attempts FROM skip_jobs').fetchone()[:],('review',2))

    def test_existing_disjoint_human_choice_does_not_erase_another_intro(self):
        self.old_job()
        manual = self.marker(self.target)  # Different section at 04:43.
        with self.db() as con:
            auto.migrate(con)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE status='pending'").fetchone()[0],1)
            row = con.execute('SELECT status,start_ms,end_ms FROM skip_records WHERE id=?',(manual,)).fetchone()
            self.assertEqual(row[:],('approved',283043,309573))
            # An independent candidate is not silently discarded by a review.
            candidate = con.execute("SELECT start_ms,end_ms FROM skip_records WHERE status='pending'").fetchone()
            self.assertTrue(candidate['end_ms'] < row['start_ms'])


class PublicationGuards(fixtures.AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registered(self.target)

    def test_vote_cannot_be_relabelled_as_another_episode_or_file(self):
        one = self.voted(12,'81')
        for altered in (one | {'episode':11},one | {'asset_key':'c'*64}):
            decision=auto.consensus([altered],[],self.target['duration_ms'],'intro')
            with self.db() as con:
                self.assertFalse(auto.publish(con,self.target,'intro',decision))

    def test_machine_approval_cannot_become_a_reviewed_reference_even_if_evidence_is_missing(self):
        one = self.voted(12,'81')
        with self.db() as con:
            con.execute("UPDATE skip_records SET source='auto_audio' WHERE id=?",(one['record_id'],))
            self.assertEqual(auto.reference_rows(con,self.target,'intro'),[])
            decision=auto.consensus([one],[],self.target['duration_ms'],'intro')
            self.assertFalse(auto.publish(con,self.target,'intro',decision))

    def test_single_approval_archives_all_generated_alternatives_and_is_idempotent(self):
        one = self.voted(12,'81')
        with self.db() as con:
            add_record(con,self.target,'intro',48000,74530,False,source='audio',confidence=.937)
            add_record(con,self.target,'intro',49000,75530,False,source='theintrodb')
            decision=auto.consensus([one],[],self.target['duration_ms'],'intro')
            self.assertTrue(auto.publish(con,self.target,'intro',decision))
            self.assertFalse(auto.publish(con,self.target,'intro',decision))
            rows=con.execute('SELECT status,source FROM skip_records WHERE asset_key=?',(self.target['asset_key'],)).fetchall()
            self.assertEqual([row['status'] for row in rows].count('approved'),1)
            self.assertEqual([row['status'] for row in rows].count('pending'),0)
            evidence=con.execute("SELECT evidence_json FROM skip_auto_evidence e JOIN skip_records r ON r.id=e.record_id WHERE r.source='auto_audio'").fetchone()
            self.assertEqual(json.loads(evidence[0])['policy'],auto.POLICY_VERSION)


if __name__=='__main__':
    unittest.main()
