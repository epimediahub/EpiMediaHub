"""Synthetic shifted-content tests; no production data or provider traffic."""
import json
import random
import unittest
from fingerprint_cohort import decode, match, near_record, inspect_cohort


def fp(words, offset=0, step=500):
    return decode(json.dumps(words),step_ms=step,offset_ms=offset)


class FingerprintTests(unittest.TestCase):
    def setUp(self):
        rng=random.Random(42)
        self.common=[rng.getrandbits(32) for _ in range(70)]
        self.prefix=[rng.getrandbits(32) for _ in range(18)]
        self.suffix=[rng.getrandbits(32) for _ in range(21)]

    def test_identical_content_different_positions(self):
        a=fp(self.prefix + self.common + self.suffix,offset=20_000)
        b=fp(self.common,offset=90_000)
        found=match(a,b)
        self.assertIsNotNone(found)
        self.assertGreaterEqual(found.length_ms,15_000)
        self.assertNotEqual(found.target_start_ms,found.reference_start_ms)
        self.assertGreaterEqual(found.frame_ratio,0.9)

    def test_1_bit_noise_survives_but_very_different_audio_does_not(self):
        own=fp(self.common)
        changed=fp([x ^ 3 for x in self.common],offset=150_000)
        self.assertIsNotNone(match(own,changed))
        rng=random.Random(1234)
        random_other=fp([rng.getrandbits(32) for _ in self.common])
        self.assertIsNone(match(own,random_other))

    def test_unrelated_silence_is_not_repeat_structure(self):
        own=fp([123456]*50)
        ref=fp([123456]*50)
        self.assertIsNone(match(own,ref))

    def test_reject_unknown_schema_or_large_words(self):
        with self.assertRaises(ValueError):
            decode('{"not":"words"}',step_ms=500,offset_ms=0)
        with self.assertRaises(ValueError):
            decode(json.dumps([3]*721),step_ms=500,offset_ms=0)
        with self.assertRaises(ValueError):
            decode(json.dumps([3.1]*30),step_ms=500,offset_ms=0)

    def test_mismatched_sample_steps_not_inferred(self):
        self.assertIsNone(match(fp(self.common,step=500),fp(self.common,step=1000)))

    def test_candidate_must_overlap_saved_marker(self):
        result=match(fp(self.common,offset=40000),fp(self.common,offset=90000))
        self.assertTrue(near_record(result,start_ms=39000,end_ms=72000))
        self.assertFalse(near_record(result,start_ms=120000,end_ms=150000))

    def test_independent_episode_and_manual_proof(self):
        best=match(fp(self.common,offset=40000),fp(self.common,offset=200000))
        record={'start_ms':40000,'end_ms':72000}
        peer=[(2,best,False),(3,best,False),(4,best,True)]
        self.assertEqual(inspect_cohort(record,peer),
                         'SHADOW_FINGERPRINT_PLUS_MANUAL_NOT_RELEASED')
        self.assertEqual(inspect_cohort(record,peer[:2]),
                         'SHADOW_MULTIPLE_AUDIO_MATCHES_NOT_RELEASED')
        self.assertEqual(inspect_cohort(record,[(2,best,False)]*3),
                         'SHADOW_SINGLE_AUDIO_MATCH_NOT_RELEASED')

    def test_empty_or_incompatible_is_not_proof(self):
        self.assertEqual(inspect_cohort({'start_ms':0,'end_ms':20000}, []),
                         'NO_FINGERPRINT_PROOF')


if __name__=='__main__':
    unittest.main()
