"""Read-only synthetic data tests for bounded fingerprint cache replay."""
import json
import sqlite3
import unittest
from collections import Counter
from fingerprint_shadow_replay import (
    cached, human_approved, audio_confirmed, valid_asset, is_protected,
)


def fake_row(**updates):
    row={
        'asset_key':'asset-1','playlist_id':8,'source_key':'series',
        'asset_source_key':'series','season':1,'asset_season':1,
        'episode':1,'asset_episode':1,
        'media_type':'episode','asset_media_type':'episode',
        'duration_ms':2400000,'asset_duration_ms':2400000,
        'segment_type':'intro','source':'audio','status':'pending',
        'start_ms':25000,'end_ms':60000,'disabled':0,
        'human_review':0,'evidence_json':json.dumps({
            'episcene_required':True,'status':'AUTO_CONFIRMED',
            'method':'episode_consensus_v3'}),
        'device_id':None,'customer_id':None,'device_customer_id':None,
        'device_enabled':None,'customer_enabled':None,
    }
    row.update(updates)
    return row


def temporary_db():
    con=sqlite3.connect(':memory:')
    con.row_factory=sqlite3.Row
    con.executescript("""
      CREATE TABLE skip_auto_windows(asset_key TEXT,kind TEXT,
        words_json TEXT,offset_ms INTEGER,length_ms INTEGER,step_ms INTEGER,
        duration_ms INTEGER,created_at TEXT);
      CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER);
      CREATE TABLE skip_records(id INTEGER PRIMARY KEY,asset_key TEXT,
        segment_type TEXT,duration_ms INTEGER,status TEXT,source TEXT);
      CREATE TABLE skip_auto_evidence(record_id INTEGER,human_review INTEGER);
    """)
    return con


class CacheTests(unittest.TestCase):
    def test_current_duration_words_available(self):
        con=temporary_db()
        with con:
            con.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?,?)",
                        ('asset-1','intro',json.dumps(list(range(45))),
                         20000,25000,500,2400000,'2026-01-01'))
            counts=Counter()
            result=cached(con,fake_row(),counts)
            self.assertIsNotNone(result)
            self.assertEqual(result.step_ms,500)
            self.assertEqual(len(result.words),45)
            self.assertEqual(counts['MISSING_CACHED_AUDIO_WINDOW'],0)
        con.close()

    def test_stale_duration_disallowed(self):
        con=temporary_db()
        with con:
            con.execute("INSERT INTO skip_auto_windows VALUES (?,?,?,?,?,?,?,?)",
                        ('asset-1','intro',json.dumps([3]*45),
                         20000,25000,500,2390000,'2026-01-01'))
            counts=Counter()
            self.assertIsNone(cached(con,fake_row(),counts))
            self.assertEqual(counts['MISSING_CACHED_AUDIO_WINDOW'],1)
        con.close()

    def test_explicit_block_rejected(self):
        con=temporary_db()
        with con:
            con.execute("INSERT INTO skip_auto_blocks VALUES (?,?,?)",
                        ('asset-1','intro',2400000))
            self.assertTrue(is_protected(con,dict(fake_row(),id=5)))
        con.close()

    def test_human_requires_identity_and_device(self):
        human=fake_row(source='device',status='approved',
                       customer_id=11,device_customer_id=11,
                       device_id=5,device_enabled=1,customer_enabled=1)
        self.assertTrue(human_approved(human))
        self.assertFalse(human_approved(dict(human,device_enabled=0)))
        self.assertFalse(human_approved(dict(human,asset_episode=2)))
        self.assertFalse(audio_confirmed(human))
        self.assertTrue(audio_confirmed(fake_row()))
        self.assertFalse(audio_confirmed(fake_row(
            evidence_json=json.dumps({'episcene_required':True,
              'status':'AUTO_CONFIRMED','method':'episode_consensus_v3',
              'audio_visual_disagreement':True}))))

    def test_wrong_playlist_asset_is_not_current(self):
        self.assertTrue(valid_asset(fake_row()))
        self.assertFalse(valid_asset(fake_row(asset_source_key='different')))
        self.assertFalse(valid_asset(fake_row(asset_duration_ms=2380000)))


if __name__=='__main__':
    unittest.main()
