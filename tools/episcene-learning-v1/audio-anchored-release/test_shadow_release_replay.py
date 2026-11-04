"""Synthetic read-only audit plumbing checks; never imports live server modules."""
import json
import sqlite3
import unittest
from shadow_release_replay import as_json, mapped, evidence, schemas_ok


def row(**overrides):
    data={
        'asset_key':'asset-one','playlist_id':8,
        'source_key':'series','asset_source_key':'series',
        'season':1,'asset_season':1,
        'episode':2,'asset_episode':2,
        'media_type':'episode','asset_media_type':'episode',
        'duration_ms':2400000,'asset_duration_ms':2400000,
        'segment_type':'intro','start_ms':30000,'end_ms':50000,
        'disabled':0,'source':'audio','status':'pending','device_id':None,
        'customer_id':None,'device_customer_id':None,'device_enabled':None,
        'customer_enabled':None,'evidence_json':None,'human_review':0,
    }
    data.update(overrides)
    return data


class AuditInputTests(unittest.TestCase):
    def test_requires_exact_asset_identity(self):
        self.assertTrue(mapped(row()))
        self.assertFalse(mapped(row(asset_episode=5)))
        self.assertFalse(mapped(row(asset_source_key='another')))
        self.assertFalse(mapped(row(asset_duration_ms=2399000)))

    def test_manual_must_be_owned_and_current(self):
        a=row(source='device',status='approved',device_id=7,
              customer_id=11,device_customer_id=11,device_enabled=1,
              customer_enabled=1)
        self.assertTrue(evidence(a).human_verified)
        self.assertFalse(evidence({**a,'device_enabled':0}).human_verified)
        self.assertFalse(evidence({**a,'customer_id':12}).human_verified)
        self.assertFalse(evidence({**a,'asset_episode':5}).human_verified)

    def test_audio_confirmation_requires_machine_evidence(self):
        good=json.dumps({'episcene_required':True,'status':'AUTO_CONFIRMED',
                         'method':'episode_consensus_v3'})
        self.assertTrue(evidence(row(evidence_json=good)).audio_confirmed)
        self.assertFalse(evidence(row(evidence_json=good,human_review=1)).audio_confirmed)
        self.assertFalse(evidence(row(evidence_json=json.dumps(
            {'status':'AUTO_CONFIRMED'}))).audio_confirmed)

    def test_visual_disagreement_blocks(self):
        bad=json.dumps({'episcene_required':True,'status':'AUTO_CONFIRMED',
                        'method':'episode_consensus_v3','audio_visual_disagreement':True,
                        'decision':{'status':'NO_MATCH'}})
        obj=evidence(row(evidence_json=bad))
        self.assertFalse(obj.audio_confirmed)
        self.assertTrue(obj.visual_disagreement)
        self.assertEqual(obj.visual_decision,'NO_MATCH')

    def test_invalid_evidence_is_empty(self):
        self.assertEqual(as_json('{broken'),{})
        self.assertEqual(as_json('[]'),{})

    def test_missing_original_schema_fails_closed(self):
        with sqlite3.connect(':memory:') as con:
            con.execute('CREATE TABLE skip_records(id INTEGER)')
            self.assertFalse(schemas_ok(con))


if __name__ == '__main__':
    unittest.main()
