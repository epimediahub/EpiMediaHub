"""Offline classification tests for EpiScene visual-only metadata root cause."""
import json
import sqlite3
import unittest
import visual_consensus_root_cause_isolated as x


def database():
    c=sqlite3.connect(':memory:')
    c.row_factory=sqlite3.Row
    c.executescript("""
        CREATE TABLE skip_assets (
            asset_key TEXT PRIMARY KEY,playlist_id INTEGER,source_key TEXT,
            season INTEGER,episode INTEGER,duration_ms INTEGER
        );
        CREATE TABLE skip_scene_windows (
            id INTEGER PRIMARY KEY, asset_key TEXT, kind TEXT,duration_ms INTEGER
        );
        CREATE TABLE skip_scene_window_versions (
            window_id INTEGER,version TEXT
        );
        CREATE TABLE skip_records (
            id INTEGER PRIMARY KEY,asset_key TEXT,segment_type TEXT,
            start_ms INTEGER,end_ms INTEGER,status TEXT
        );
        CREATE TABLE skip_auto_evidence (
            record_id INTEGER,evidence_json TEXT
        );
    """)
    for ep in (1,2,3):
        c.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?)",
                  ('episode'+str(ep),8,'show',1,ep,3600000))
        c.execute("INSERT INTO skip_scene_windows VALUES(?,?,?,?)",
                  (ep,'episode'+str(ep),'intro',3600000))
        a=c.execute("SELECT * FROM skip_assets WHERE asset_key=?",('episode'+str(ep),)).fetchone()
        c.execute("INSERT INTO skip_scene_window_versions VALUES(?,?)",
                  (ep,x.visual_version(a)))
    c.execute("INSERT INTO skip_records VALUES(1,'episode1','intro',2000,65000,'pending')")
    c.commit()
    return c


class VisualConsensusRootCauseTests(unittest.TestCase):
    def test_two_valid_peers_but_no_matching_consensus(self):
        c=database()
        row=c.execute("SELECT * FROM skip_records WHERE id=1").fetchone()
        a=x.more_visual_evidence(c,row)
        self.assertEqual(a[:2],('TWO_PLUS_VERSION_VALID_PEERS','NO_SAME_ASSET_CONSENSUS'))
        c.close()

    def test_stale_peer_version_is_not_counted(self):
        c=database()
        c.execute("UPDATE skip_scene_window_versions SET version='stale' WHERE window_id=2")
        row=c.execute("SELECT * FROM skip_records WHERE id=1").fetchone()
        a=x.more_visual_evidence(c,row)
        self.assertEqual(a[0],'PEERS_EXIST_BUT_FEWER_THAN_TWO_VERSION_VALID')
        c.close()

    def test_reviewed_consensus_gap_not_automatically_approved(self):
        c=database()
        c.execute("INSERT INTO skip_records VALUES(2,'episode1','intro',9000,70000,'superseded')")
        c.execute("INSERT INTO skip_auto_evidence VALUES(2,?)",
                  (json.dumps({'method':'episcene_consensus',
                               'decision':{'status':'REVIEW','reason':'ambiguous'}}),))
        row=c.execute("SELECT * FROM skip_records WHERE id=1").fetchone()
        a=x.more_visual_evidence(c,row)
        self.assertEqual(a[1],'OFFSET_5_TO_15_SECONDS')
        self.assertEqual(a[2],'record_superseded_decision_REVIEW')
        self.assertEqual(a[3],'ambiguous')
        c.close()

    def test_near_gap_requires_validation_not_automatic_release(self):
        c=database()
        c.execute("INSERT INTO skip_records VALUES(2,'episode1','intro',3000,64000,'pending')")
        c.execute("INSERT INTO skip_auto_evidence VALUES(2,?)",
                  (json.dumps({'method':'episcene_consensus','decision':{'status':'REVIEW'}}),))
        row=c.execute("SELECT * FROM skip_records WHERE id=1").fetchone()
        self.assertEqual(x.more_visual_evidence(c,row)[1],'MATCH_WITHIN_2_SECONDS')
        c.close()


if __name__=='__main__':
    unittest.main()
