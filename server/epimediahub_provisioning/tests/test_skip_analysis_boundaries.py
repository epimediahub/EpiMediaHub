"""Measured audio alignment and corrected-reference cache regression checks."""
from __future__ import annotations

import array
import contextlib
import ctypes.util
import json
import math
from pathlib import Path
import random
import shutil
import sys
import types
import unittest
from unittest import mock
import wave

from test_skip_analysis_references import ReferenceFixture, REAL_FLASK
from skip_analysis import fingerprint, matching_offset, register_asset, run
from skip_analysis_worker import process_one, store_fingerprint
from skip_markers import add_record, install, now


class BoundaryFixture(ReferenceFixture):
    def reference(self):
        record_id = self.marker()
        with self.db() as con:
            register_asset(con, self.seed, self.seed, self.device)
            con.execute("UPDATE skip_jobs SET status='done'")
            record = con.execute("SELECT * FROM skip_records WHERE id=?", (record_id,)).fetchone()
        self.waiting(status="queued")
        return record

    def words(self):
        rng = random.Random(721)
        reference = [rng.getrandbits(32) for _ in range(80)]
        target = [rng.getrandbits(32) for _ in range(240)] + reference + [rng.getrandbits(32) for _ in range(80)]
        return reference, target


class BoundaryCacheTests(BoundaryFixture, unittest.TestCase):
    def test_current_cache_projects_reviewed_boundaries_without_one_second_crop(self):
        record = self.reference()
        reference, target = self.words()
        with self.db() as con:
            store_fingerprint(con, record, reference, 125)
        with mock.patch("skip_analysis_worker.provider_proxy", side_effect=lambda *_: contextlib.nullcontext("fixture")), \
             mock.patch("skip_analysis_worker.probe", return_value=(self.target["duration_ms"], [])), \
             mock.patch("skip_analysis_worker.fingerprint", return_value=(target, 125)) as decoder:
            self.assertEqual(process_one(self.db), "review")
        self.assertEqual(decoder.call_count, 1)
        with self.db() as con:
            proposal = con.execute("SELECT * FROM skip_records WHERE source='audio'").fetchone()
        self.assertEqual((proposal["start_ms"], proposal["end_ms"]), (28000, 54530))
        self.assertEqual(proposal["status"], "pending")

    def test_marker_shift_recalculates_stale_cache_even_when_length_is_unchanged(self):
        record = self.reference()
        reference, target = self.words()
        with self.db() as con:
            store_fingerprint(con, record, [0] * 80, 125)
            con.execute("UPDATE skip_records SET start_ms=start_ms+5000,end_ms=end_ms+5000,reviewed_at=? WHERE id=?",
                        (now(), record["id"]))
        def decode(_source, start, length, _busy):
            if start:
                self.assertEqual(start, record["start_ms"] + 7000)
                self.assertEqual(length, record["end_ms"] - record["start_ms"] - 4000)
                return reference, 125
            return target, 125
        with mock.patch("skip_analysis_worker.provider_proxy", side_effect=lambda *_: contextlib.nullcontext("fixture")), \
             mock.patch("skip_analysis_worker.probe", return_value=(self.target["duration_ms"], [])), \
             mock.patch("skip_analysis_worker.fingerprint", side_effect=decode):
            self.assertEqual(process_one(self.db), "review")
        with self.db() as con:
            learned = con.execute("SELECT words_json FROM skip_fingerprints WHERE record_id=?", (record["id"],)).fetchone()
            corrected = con.execute("SELECT * FROM skip_records WHERE id=?", (record["id"],)).fetchone()
        self.assertEqual(json.loads(learned[0]), reference)
        self.assertEqual(corrected["status"], "approved")
        self.assertEqual(corrected["start_ms"], record["start_ms"] + 5000)

    def test_review_during_decode_cannot_store_audio_under_the_new_marker_version(self):
        record = self.reference()
        with self.db() as con:
            con.execute("UPDATE skip_records SET start_ms=start_ms+5000,end_ms=end_ms+5000,reviewed_at=? WHERE id=?",
                        (now(), record["id"]))
            store_fingerprint(con, record, self.words()[0], 125)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_fingerprints").fetchone()[0], 0)


@unittest.skipUnless(shutil.which("ffmpeg") and ctypes.util.find_library("chromaprint"),
                     "FFmpeg and Chromaprint required for measured audio checks")
class RealBoundaryTests(BoundaryFixture, unittest.TestCase):
    rate = 11025

    @classmethod
    def setUpClass(cls):
        rng = random.Random(170)
        cls.music = array.array("h")
        for _ in range(56):
            frequency = rng.choice([110, 146.83, 196, 220, 261.63, 329.63, 392, 493.88, 587.33])
            cls.music.extend(int(5500 * math.sin(2 * math.pi * frequency * n / cls.rate)
                                + 2400 * math.sin(2 * math.pi * frequency * 1.5 * n / cls.rate)
                                + 1200 * math.sin(2 * math.pi * (frequency * 2 + 13) * n / cls.rate))
                             for n in range(cls.rate // 2))

    def clip(self, name, prefix_ms, gain=1):
        path = Path(self.temp.name) / name
        samples = array.array("h", [0]) * round(self.rate * prefix_ms / 1000)
        samples.extend(round(value * gain) for value in self.music)
        samples.extend(array.array("h", [0]) * self.rate * 6)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(self.rate)
            wav.writeframes(samples.tobytes())
        return path

    def test_fractional_offsets_retain_subsecond_start_and_end(self):
        source = self.clip("reference.wav", 18043)
        words, step = fingerprint(str(source), 20043, 24000)
        for actual in (0, 29000, 29347, 41783, 67049):
            with self.subTest(start_ms=actual):
                target = self.clip("target.wav", actual, gain=.63)
                target_words, target_step = fingerprint(str(target), 0, 120000)
                self.assertAlmostEqual(step, target_step)
                match = matching_offset(words, target_words, step)
                self.assertIsNotNone(match)
                start = match[0] - 2000
                self.assertLessEqual(abs(start - actual), 100)
                self.assertLessEqual(abs(start + 28000 - (actual + 28000)), 100)
                self.assertGreaterEqual(match[1], .9)

    def test_real_aac_worker_proposal_is_accurate_and_preserves_approval(self):
        reference_path = self.clip("reference.wav", 18043)
        raw_target = self.clip("target.wav", 29347, gain=.63)
        target_path = Path(self.temp.name) / "target.m4a"
        run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-i", str(raw_target),
             "-c:a", "aac", "-b:a", "96k", str(target_path)], timeout=20)
        self.seed = self.descriptor("81", 12, duration_ms=52040)
        self.target = self.descriptor("82", 13, duration_ms=63344)
        with self.db() as con:
            record = add_record(con, self.seed, "intro", 18043, 46043, False, self.device)
            con.execute("UPDATE skip_records SET status='approved',reviewed_at=? WHERE id=?", (now(), record["id"]))
            register_asset(con, self.seed, self.seed, self.device)
            register_asset(con, self.target, self.target, self.device)
        def local_file(url, _busy):
            return contextlib.nullcontext(str(reference_path if url.endswith("/81.mkv") else target_path))
        with mock.patch("skip_analysis_worker.provider_proxy", side_effect=local_file):
            self.assertEqual(process_one(self.db), "done")
            self.assertEqual(process_one(self.db), "review")
        with self.db() as con:
            proposal = con.execute("SELECT * FROM skip_records WHERE source='audio'").fetchone()
            approved = con.execute("SELECT * FROM skip_records WHERE id=?", (record["id"],)).fetchone()
        self.assertEqual(proposal["status"], "pending")
        self.assertLessEqual(abs(proposal["start_ms"] - 29347), 150)
        self.assertLessEqual(abs(proposal["end_ms"] - 57347), 150)
        self.assertEqual((approved["status"], approved["start_ms"], approved["end_ms"]),
                         ("approved", 18043, 46043))

    def test_repeated_real_intro_remains_ambiguous(self):
        source = self.clip("reference.wav", 18043)
        words, step = fingerprint(str(source), 20043, 24000)
        target = self.clip("repeated.wav", 0)
        with wave.open(str(target), "rb") as wav:
            first = wav.readframes(wav.getnframes())
        with wave.open(str(target), "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(self.rate)
            wav.writeframes(first + first)
        target_words, _ = fingerprint(str(target), 0, 120000)
        self.assertIsNone(matching_offset(words, target_words, step))


@unittest.skipUnless(REAL_FLASK, "Flask required for dashboard review checks")
class BoundaryReviewTests(BoundaryFixture, unittest.TestCase):
    def test_dashboard_correction_invalidates_only_that_reference_cache(self):
        record = self.reference()
        reference, _ = self.words()
        other = self.marker(self.descriptor("83", 14))
        with self.db() as con:
            store_fingerprint(con, record, reference, 125)
            con.execute("INSERT INTO skip_fingerprints VALUES(?,'[1,2,3]',125,2000,26530,?)", (other, now()))
        site = REAL_FLASK("boundary-review-fixture")
        site.secret_key = "fixture-session-only"
        @site.get("/health", endpoint="health")
        def health():
            return {"status": "ok", "api_version": "0.8.2"}
        backend = types.ModuleType("app")
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        with mock.patch.dict(sys.modules, {"app": backend}):
            install(site, self.db)
        client = site.test_client()
        with client.session_transaction() as session:
            session["skip_csrf"] = "fixture-csrf"
        response = client.post(f"/admin/skip/{record['id']}/review", data={
            "csrf": "fixture-csrf", "decision": "approve", "start": "00:04:48.043", "end": "00:05:14.573"})
        self.assertEqual(response.status_code, 302)
        with self.db() as con:
            cached_ids = [row[0] for row in con.execute("SELECT record_id FROM skip_fingerprints")]
            corrected = con.execute("SELECT * FROM skip_records WHERE id=?", (record["id"],)).fetchone()
        self.assertEqual(cached_ids, [other])
        self.assertEqual((corrected["status"], corrected["start_ms"], corrected["end_ms"]),
                         ("approved", 288043, 314573))


if __name__ == "__main__":
    unittest.main()
