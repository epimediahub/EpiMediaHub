#!/usr/bin/env python3
"""Regression tests for the read-only autoapproval blocker audit."""
import sqlite3
import tempfile
import unittest
from pathlib import Path
import auto_release_audit as audit


def fixture():
    db=sqlite3.connect(':memory:')
    db.row_factory=sqlite3.Row
    db.executescript('''
      CREATE TABLE skip_records(id INTEGER,asset_key TEXT,segment_type TEXT,source TEXT,status TEXT,
        start_ms INTEGER,end_ms INTEGER,duration_ms INTEGER,disabled INTEGER,confidence REAL);
      CREATE TABLE skip_assets(asset_key TEXT,playlist_id INTEGER,duration_ms INTEGER);
      CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT,human_review INTEGER);
    ''')
    for a in ('a','b','c','d','e','f','g','h'):
        db.execute('INSERT INTO skip_assets VALUES(?,?,?)',(a,8,3600000))
    def insert(id,asset,source='episcene',status='pending',evidence=None,kind='outro'):
        db.execute('INSERT INTO skip_records VALUES(?,?,?,?,?,?,?,?,?,?)',
            (id,asset,kind,source,status,3000000,3600000,3600000,0,.98))
        if evidence is not None:
            db.execute('INSERT INTO skip_auto_evidence VALUES(?,?,?)',(id,evidence,0))
    insert(1,'a',evidence='{"method":"episcene_consensus","audio_visual_disagreement":true,"decision":{"status":"AUTO_CONFIRMED"}}')
    insert(2,'b',evidence='{"method":"episcene_consensus","audio_visual_disagreement":false,"decision":{"status":"AUTO_CONFIRMED"}}')
    insert(3,'c',source='audio_repetition')
    insert(4,'d',evidence='{"episcene_required":true}')
    insert(5,'e',source='theintrodb')
    insert(6,'f',source='chapter')
    insert(7,'g',source='audio_repetition')
    insert(8,'g',source='device')
    insert(9,'h',source='audio_repetition')
    insert(10,'h',source='device',status='approved')
    db.commit()
    return db


class Blockers(unittest.TestCase):
    def test_blocks_and_dry_run_are_classified_without_approval(self):
        db=fixture()
        with db:
            rows=audit.query_database(db)
            result=audit.diagnostic(rows)
            self.assertEqual(result['pending_machine_markers_checked'],8)
            self.assertEqual(result['reasons']['AUDIO_VISUAL_DISAGREEMENT'],1)
            self.assertEqual(result['reasons']['POSSIBLY_READY_RECHECK_FULL_GATE'],1)
            self.assertEqual(result['reasons']['NEEDS_VISUAL_EVIDENCE'],1)
            self.assertEqual(result['reasons']['ONLINE_HINT_NOT_INDEPENDENT_PROOF'],1)
            self.assertEqual(result['reasons']['CHAPTER_HINT_NOT_INDEPENDENT_PROOF'],1)
            self.assertEqual(result['reasons']['REPETITION_ALONE_NOT_VERIFIED'],1)
            self.assertEqual(result['reasons']['OWNER_CORRECTION_PENDING'],1)
            self.assertEqual(result['reasons']['ALREADY_DECIDED_FOR_SAME_ASSET'],1)
            self.assertEqual(result['new_auto_approvals'],0)

    def test_database_snapshot_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'live.db'
            source=fixture()
            with sqlite3.connect(p) as target:
                source.backup(target)
            before=p.read_bytes()
            with sqlite3.connect(p.resolve().as_uri()+'?mode=ro',uri=True) as read:
                report=audit.diagnostic(audit.query_database(read))
            self.assertFalse(report['production_db_modified'])
            self.assertEqual(p.read_bytes(),before)

    def test_unparseable_evidence_fails_closed(self):
        db=fixture()
        with db:
            db.execute("UPDATE skip_auto_evidence SET evidence_json='invalid-json' WHERE record_id=1")
            result=audit.diagnostic(audit.query_database(db))
            self.assertEqual(result['reasons']['INSUFFICIENT_MACHINE_EVIDENCE'],1)


if __name__=='__main__':
    unittest.main(verbosity=2)
