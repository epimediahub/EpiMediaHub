"""Synthetic tests: make old signed user markers the first learning target."""
import unittest

from fingerprint_user_reference_shadow_v6 import (
    prioritize_manual_cohorts,manual_coverage_counts,
)


def pending_audio(**overrides):
    row={
        "asset_key":"asset-1","playlist_id":8,"source_key":"show",
        "asset_source_key":"show","season":1,"asset_season":1,
        "episode":1,"asset_episode":1,"media_type":"episode",
        "asset_media_type":"episode","duration_ms":2400000,
        "asset_duration_ms":2400000,"segment_type":"intro",
        "source":"audio","status":"pending","disabled":0,
        "human_review":0,
        "evidence_json":'{"episcene_required":true,"status":"AUTO_CONFIRMED","method":"audio_repeat"}',
    }
    row.update(overrides)
    return row


class UserReferenceTargetingTests(unittest.TestCase):
    def test_historic_reference_cohorts_precede_unmarked_series(self):
        key_manual=(8,"lupin",1,"intro")
        key_no_manual=(8,"navy",13,"intro")
        key_other_manual=(10,"lie-to-me",1,"outro")
        groups={
            key_no_manual:[pending_audio(source_key="navy",asset_source_key="navy")],
            key_manual:[pending_audio(source_key="lupin",asset_source_key="lupin")],
            key_other_manual:[pending_audio(playlist_id=10,source_key="lie-to-me",
                                            asset_source_key="lie-to-me",
                                            segment_type="outro")],
        }
        index={key_manual:[1,2],key_other_manual:[3]}
        ordered=[k for k,_ in prioritize_manual_cohorts(groups,index)]
        self.assertEqual(ordered[0],key_manual)
        self.assertEqual(ordered[1],key_other_manual)
        self.assertEqual(ordered[2],key_no_manual)

    def test_diagnostic_distinguishes_candidate_coverage_from_approvals(self):
        key_manual=(8,"lupin",1,"intro")
        key_unrelated=(8,"navy",13,"intro")
        groups={
            key_manual:[
                pending_audio(source_key="lupin",asset_source_key="lupin"),
                pending_audio(source_key="lupin",asset_source_key="lupin",
                              episode=2,asset_episode=2,status="approved")],
            key_unrelated:[
                pending_audio(source_key="navy",asset_source_key="navy")],
        }
        result=manual_coverage_counts(groups,{key_manual:[1,2,3]})
        self.assertEqual(result["historical_reference_cohorts"],1)
        self.assertEqual(result["record_cohorts_with_historical_references"],1)
        self.assertEqual(result["record_cohorts_without_historical_references"],1)
        self.assertEqual(result["pending_audio_records_in_historical_reference_cohorts"],1)
        self.assertEqual(result["historical_reference_cohorts_with_pending_audio"],1)
        self.assertNotIn("approved",str(result).lower())

    def test_weak_audio_cannot_be_reinterpreted_as_candidate(self):
        k=(10,"mobland",1,"intro")
        groups={k:[pending_audio(playlist_id=10,source_key="mobland",
                                 asset_source_key="mobland",
                                 evidence_json='{}')]}
        result=manual_coverage_counts(groups,{k:[1]})
        self.assertEqual(result["pending_audio_records_in_historical_reference_cohorts"],0)


if __name__=="__main__":
    unittest.main()
