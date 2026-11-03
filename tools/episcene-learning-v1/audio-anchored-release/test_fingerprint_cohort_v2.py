"""Real-format audio-cache regression tests (synthetic data only)."""
from __future__ import annotations
import json
import random
import unittest
from fingerprint_cohort_v2 import decode, match, near_record, MAX_WORDS


def fp(seq, offset=0, step=123.81):
    return decode(json.dumps(seq), step_ms=step, offset_ms=offset)


class RealFormatTests(unittest.TestCase):
    def setUp(self):
        self.rng = random.Random(717)
        self.common = [self.rng.getrandbits(32) for _ in range(230)]

    def test_real_step_and_long_cached_reference(self):
        first = [self.rng.getrandbits(32) for _ in range(400)]
        tail = [self.rng.getrandbits(32) for _ in range(1900)]
        target = fp(self.common, 40_000)
        peer = fp(first + self.common + tail, 280_000)
        self.assertGreater(len(peer.words), 2000)
        result = match(target,peer)
        self.assertIsNotNone(result)
        self.assertEqual(result.frame_ratio, 1.0)
        self.assertAlmostEqual(result.target_start_ms, 40000, delta=200)
        self.assertAlmostEqual(result.reference_start_ms,
                               280000 + round(400 * 123.81), delta=200)
        self.assertTrue(near_record(result,start_ms=39000,end_ms=69000))

    def test_low_noise_and_different_episode_time(self):
        target = fp(self.common, 20000)
        peer = fp([x ^ 3 for x in self.common], 145000)
        r = match(target,peer)
        self.assertIsNotNone(r)
        self.assertGreaterEqual(r.frame_ratio, 0.90)
        self.assertNotEqual(r.shift_ms,0)

    def test_unrelated_content_rejected(self):
        another = [self.rng.getrandbits(32) for _ in range(2400)]
        self.assertIsNone(match(fp(self.common), fp(another)))

    def test_flat_and_silent_content_rejected(self):
        self.assertIsNone(match(fp([112233]*200), fp([112233]*2500)))

    def test_bad_cache_shape_rejected(self):
        with self.assertRaises(ValueError):
            decode('{"words":[1,2,3]}',step_ms=123.81,offset_ms=0)
        with self.assertRaises(ValueError):
            decode(json.dumps([3]*(MAX_WORDS+1)),step_ms=123.81,offset_ms=0)
        with self.assertRaises(ValueError):
            decode(json.dumps([4.4]*220),step_ms=123.81,offset_ms=0)
        with self.assertRaises(ValueError):
            decode('[]',step_ms=12.2,offset_ms=0)

    def test_mismatched_audio_sampling_step_does_not_match(self):
        self.assertIsNone(match(fp(self.common,step=123.81),
                                fp(self.common,step=124.4)))

    def test_short_overlap_does_not_count(self):
        short=[self.rng.getrandbits(32) for _ in range(90)]
        long=[self.rng.getrandbits(32) for _ in range(100)]
        self.assertIsNone(match(fp(short),fp(long)))

    def test_clipping_to_intro_has_no_out_of_marker_match(self):
        target=fp([self.rng.getrandbits(32) for _ in range(130)] + self.common,
                  offset=10000)
        reference=fp(self.common,offset=200000)
        found=match(target,reference)
        self.assertIsNotNone(found)
        self.assertFalse(near_record(found,start_ms=10000,end_ms=20000))

if __name__=="__main__":
    unittest.main()
