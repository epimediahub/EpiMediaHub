"""Real SQLite policy, catalogue association, online data and automatic publishing."""
from __future__ import annotations

import contextlib
import json
from pathlib import Path
import random
import sys
import time
import types
import unittest
from unittest import mock
import urllib.parse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_skip_analysis_references import ReferenceFixture, REAL_FLASK
import skip_automation as auto
from skip_analysis import fingerprint, register_asset
from skip_analysis_worker import busy_check, process_one
from skip_markers import add_record, install, now
import test_skip_analysis_boundaries as boundary_tests
from skip_analysis import probe, run


class AutomationFixture(ReferenceFixture):
    def setUp(self):
        super().setUp()
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_settings VALUES(1,1,0,?)", (now(),))

    def registered(self, data):
        with self.db() as con:
            self.assertTrue(register_asset(con, data, data, self.device))

    def voted(self, episode, stream):
        data = self.descriptor(stream, episode)
        self.registered(data)
        record_id = self.marker(data)
        with self.db() as con:
            row = con.execute("SELECT * FROM skip_records WHERE id=?", (record_id,)).fetchone()
        return dict(start=48000, end=74530, confidence=.95, asset_key=data["asset_key"],
                    boundaries_confirmed=True,
                    episode=episode, record_id=record_id, reviewed_at=row["reviewed_at"],
                    ref_start=row["start_ms"], ref_end=row["end_ms"])


class CatalogueTests(AutomationFixture, unittest.TestCase):
    def anchor(self):
        with self.db() as con:
            playlist = con.execute("SELECT * FROM customer_playlists WHERE id=1").fetchone()
        self.seed["source_key"] = auto.series_key(playlist, self.seed, "501")
        self.registered(self.seed)
        return self.seed

    def provider(self, _playlist, action, _busy, **_params):
        return ([{"series_id": 501}, {"series_id": 502}] if action == "get_series" else
                {"episodes": {"2": [dict(id=81, episode_num=12, container_extension="mkv"),
                                    dict(id=82, episode_num=13, container_extension="mkv"),
                                    dict(id=83, episode_num=14, container_extension="mp4")]}})

    def test_hash_and_anchor_identity_register_whole_season_without_playback(self):
        self.anchor()
        with mock.patch.object(auto, "provider_api", side_effect=self.provider):
            self.assertEqual(auto.discover_one(self.db, busy_check), "discovered")
        with self.db() as con:
            rows = con.execute("SELECT a.*,d.created_at discovered FROM skip_assets a LEFT JOIN skip_auto_assets d USING(asset_key) ORDER BY episode").fetchall()
            self.assertEqual(len(rows), 3)
            self.assertEqual([x["duration_ms"] for x in rows], [2640325, 0, 0])
            self.assertIsNone(rows[0]["discovered"])
            self.assertIsNotNone(rows[1]["discovered"])
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs").fetchone()[0], 3)

    def test_plain_same_name_different_source_key_cannot_register_siblings(self):
        self.registered(self.seed)
        with mock.patch.object(auto, "provider_api", side_effect=self.provider) as fetch:
            self.assertEqual(auto.discover_one(self.db, busy_check), "unmapped")
            self.assertEqual(fetch.call_count, 1)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 1)

    def test_wrong_anchor_file_or_duplicate_numbering_rejects_entire_season(self):
        self.anchor()
        for rows in ([dict(id=99, episode_num=12, container_extension="mkv")],
                     [dict(id=81, episode_num=12, container_extension="mp4")],
                     [dict(id=81, episode_num=12, container_extension="mkv"), dict(id=82, episode_num=12)],
                     [dict(id=81, episode_num=12, season=3, container_extension="mkv")]):
            with self.subTest(rows=rows):
                with self.db() as con:
                    con.execute("DELETE FROM skip_auto_series")
                with mock.patch.object(auto, "provider_api", side_effect=lambda p, a, b, **k: [{"series_id": 501}] if a == "get_series" else {"episodes": {"2": rows}}):
                    self.assertEqual(auto.discover_one(self.db, busy_check), "unmapped")
                with self.db() as con:
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 1)

    def test_existing_client_identity_is_never_overwritten(self):
        other = self.descriptor("82", 99, source_key="c" * 64)
        self.registered(other)
        self.anchor()
        with mock.patch.object(auto, "provider_api", side_effect=self.provider):
            self.assertEqual(auto.discover_one(self.db, busy_check), "discovered")
        with self.db() as con:
            row = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (other["asset_key"],)).fetchone()
            self.assertEqual((row["source_key"], row["episode"]), ("c" * 64, 99))

    def test_disabled_automatic_or_busy_account_never_opens_provider(self):
        self.anchor()
        with self.db() as con:
            con.execute("INSERT INTO skip_presence VALUES(1,1,?)", (int(time.time()) + 70,))
        with mock.patch.object(auto, "provider_api") as fetch:
            self.assertEqual(auto.discover_one(self.db, busy_check), "queued")
            fetch.assert_not_called()
            with self.db() as con:
                con.execute("UPDATE skip_auto_settings SET enabled=0")
            self.assertEqual(auto.discover_one(self.db, busy_check), "idle")
            fetch.assert_not_called()

    def test_successful_catalogue_is_cached_for_a_day_and_contains_no_secrets(self):
        self.anchor()
        with mock.patch.object(auto, "provider_api", side_effect=self.provider) as fetch:
            auto.discover_one(self.db, busy_check)
            self.assertEqual(auto.discover_one(self.db, busy_check), "idle")
            self.assertEqual(fetch.call_count, 2)
        with self.db() as con:
            stored = con.execute("SELECT ids_json FROM skip_auto_catalogue").fetchone()[0]
        self.assertEqual(json.loads(stored), ["501", "502"])
        self.assertNotIn("TEST_PROVIDER_SECRET", stored)


class OnlineTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registered(self.target)
        with self.db() as con:
            con.execute("UPDATE skip_auto_settings SET online_enabled=1")

    def test_upload_noise_is_removed_without_collapsing_different_titles(self):
        for title in ("[DE] Lie to Me (2009) [4K]", "Lie.to.Me.S02E13.1080p.WEB-DL", "GER: Lie to Me [2009]"):
            self.assertEqual(auto.clean_title(title), "lie to me")
        self.assertNotEqual(auto.clean_title("Lie"), auto.clean_title("Lie to Me"))

    def test_exact_title_year_and_episode_resolve_to_stable_id(self):
        replies = [{"results": [{"id": 8358, "name": "Lie to Me", "original_name": "Lie to Me", "first_air_date": "2009-01-21"}]},
                   {"season_number": 2, "episode_number": 13}, {"imdb_id": "tt1235099"}]
        with mock.patch.dict("os.environ", {"EPIMEDIAHUB_TMDB_API_KEY": "TEST_TMDB_KEY"}), mock.patch.object(auto, "fetch_json", side_effect=replies):
            result = auto.resolve_identity(self.db, self.target, lambda: False)
        self.assertTrue(result["verified"])
        self.assertEqual((result["tmdb_id"], result["imdb_id"]), (8358, "tt1235099"))

    def test_ambiguous_year_or_keyword_only_match_stays_unassigned(self):
        cases = [[{"id": 1, "name": "Lie to Me", "first_air_date": "2019-01-01"}],
                 [{"id": 1, "name": "Lie", "first_air_date": "2009-01-01"}],
                 [{"id": x, "name": "Lie to Me", "first_air_date": "2009-01-01"} for x in (1, 2)]]
        for results in cases:
            with self.subTest(results=results), mock.patch.dict("os.environ", {"EPIMEDIAHUB_TMDB_API_KEY": "TEST_TMDB_KEY"}), mock.patch.object(auto, "fetch_json", return_value={"results": results}):
                self.assertIsNone(auto.resolve_identity(self.db, self.target, lambda: False))

    def test_manual_identity_wins_over_machine_and_does_not_need_tmdb_key(self):
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_identities VALUES(?, 'tt9999999', 9, 'client_id_hint', ?)", (self.target["source_key"], now()))
            con.execute("INSERT INTO skip_identities VALUES(?, 'tt1235099', 8358, 'Lie to Me', '2009', ?)", (self.target["source_key"], now()))
        with mock.patch.dict("os.environ", {}, clear=True), mock.patch.object(auto, "fetch_json") as fetch:
            ids = auto.resolve_identity(self.db, self.target, lambda: False)
            self.assertEqual(ids["tmdb_id"], 8358)
            self.assertTrue(ids["verified"])
            fetch.assert_not_called()

    def test_online_lookup_uses_only_ids_numbering_runtime_and_caches(self):
        with self.db() as con:
            con.execute("INSERT INTO skip_identities VALUES(?, 'tt1235099', 8358, 'Lie to Me', '2009', ?)", (self.target["source_key"], now()))
        body = {"type": "tv", "tmdb_id": 8358, "intro": [{"start_ms": 48000, "end_ms": 74530}]}
        with mock.patch.object(auto, "fetch_json", return_value=body) as fetch:
            first = auto.online_segments(self.db, self.target, lambda: False)
            self.assertEqual(auto.online_segments(self.db, self.target, lambda: False), first)
            self.assertEqual(fetch.call_count, 1)
            url = fetch.call_args.args[0]
        self.assertEqual(set(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)), {"tmdb_id", "season", "episode", "duration_ms"})
        self.assertNotIn("provider.example", url)
        self.assertNotIn("TEST_PROVIDER_SECRET", url)
        self.assertTrue(first[0]["identity_verified"])

    def test_malformed_out_of_bounds_and_wrong_media_are_rejected(self):
        body = {"type": "tv", "intro": [{"start_ms": True, "end_ms": 20000}, {"start_ms": 20000, "end_ms": 10000}, {"start_ms": 0, "end_ms": 3_000_000}],
                "credits": [{"start_ms": 2_620_000, "end_ms": None}]}
        result = auto.parse_online(body, 2_640_325)
        self.assertEqual(result, [dict(kind="outro", start=2_620_000, end=2_640_325, source="theintrodb")])
        self.assertEqual(auto.parse_online(body | {"type": "movie"}, 2_640_325), [])

    def test_client_metadata_is_only_a_hint_and_cannot_confirm_one_audio_vote(self):
        data = self.target | {"tmdb_id": 8358, "imdb_id": "tt1235099"}
        self.registered(data)
        with self.db() as con:
            ids = auto.identity(con, self.target)
        self.assertFalse(ids["verified"])
        one = self.voted(12, "81")
        one['confidence'] = .91
        candidate = dict(kind="intro", start=48000, end=74530, identity_verified=False)
        self.assertIsNone(auto.consensus([one], [candidate], data["duration_ms"], "intro"))


class PublicationTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.registered(self.target)

    def test_single_high_score_with_confirmed_boundaries_is_approved(self):
        vote = self.voted(12, '81') | {'confidence': .937}
        decision = auto.consensus([vote], [], self.target['duration_ms'], 'intro')
        with self.db() as con:
            self.assertTrue(auto.publish(con, self.target, 'intro', decision))
            row = con.execute("SELECT * FROM skip_records WHERE source='auto_audio'").fetchone()
            self.assertEqual((row['status'], row['confidence']), ('approved', .937))

    def test_two_independent_reviewed_files_publish_exact_target_only(self):
        votes = [self.voted(12, "81"), self.voted(11, "83")]
        decision = auto.consensus(votes, [], self.target["duration_ms"], "intro")
        with self.db() as con:
            self.assertTrue(auto.publish(con, self.target, "intro", decision))
            row = con.execute("SELECT * FROM skip_records WHERE source='auto_audio'").fetchone()
            self.assertEqual((row["status"], row["asset_key"], row["start_ms"], row["end_ms"]), ("approved", self.target["asset_key"], 48000, 74530))
            self.assertEqual(len(auto.reference_rows(con, self.seed, "intro")), 1)  # Machine result excluded.

    def test_weak_unconfirmed_or_disagreeing_boundaries_cannot_autoapprove(self):
        first, second = self.voted(12, "81"), self.voted(11, "83")
        cases = [[first | {'confidence': .919}], [first | {'boundaries_confirmed': False}],
                 [first, second | {"start": 49000}],
                 [first, second | {"end": 75530}]]
        for votes in cases:
            self.assertIsNone(auto.consensus(votes, [], self.target["duration_ms"], "intro"))

    def test_optional_online_times_do_not_block_a_verified_audio_match(self):
        one = self.voted(12, "81")
        online = dict(kind="intro", start=48000, end=74530, identity_verified=True, source="theintrodb")
        decision = auto.consensus([one], [online], self.target["duration_ms"], "intro")
        with self.db() as con:
            self.assertTrue(auto.publish(con, self.target, "intro", decision))
            saved = con.execute("SELECT evidence_json FROM skip_auto_evidence").fetchone()
            self.assertEqual(json.loads(saved[0])['online'], [])

    def test_correction_rejection_disabled_or_changed_file_during_decode_wins(self):
        votes = [self.voted(12, "81"), self.voted(11, "83")]
        decision = auto.consensus(votes, [], self.target["duration_ms"], "intro")
        with self.db() as con:
            con.execute("UPDATE skip_records SET start_ms=start_ms+1000 WHERE id=?", (votes[0]["record_id"],))
            self.assertFalse(auto.publish(con, self.target, "intro", decision))
            con.execute("UPDATE skip_records SET start_ms=start_ms-1000 WHERE id=?", (votes[0]["record_id"],))
            con.execute("INSERT INTO skip_auto_blocks VALUES(?,?,?,?)", (self.target["asset_key"], 'intro', self.target["duration_ms"], now()))
            self.assertFalse(auto.publish(con, self.target, "intro", decision))
            con.execute("DELETE FROM skip_auto_blocks")
            con.execute("UPDATE skip_auto_settings SET enabled=0")
            self.assertFalse(auto.publish(con, self.target, "intro", decision))
            con.execute("UPDATE skip_auto_settings SET enabled=1")
            con.execute("UPDATE skip_assets SET episode=99 WHERE asset_key=?", (self.target["asset_key"],))
            self.assertFalse(auto.publish(con, self.target, "intro", decision))

    def test_user_pending_or_approved_marker_is_never_replaced(self):
        votes = [self.voted(12, "81"), self.voted(11, "83")]
        decision = auto.consensus(votes, [], self.target["duration_ms"], "intro")
        self.marker(self.target, status="pending")
        with self.db() as con:
            self.assertFalse(auto.publish(con, self.target, "intro", decision))

    def test_outro_music_cannot_skip_over_possible_post_credit_scene(self):
        duration = self.target["duration_ms"]
        first, second = self.voted(12, "81"), self.voted(11, "83")
        votes = [x | {"start": duration - 40_000, "end": duration - 10_000} for x in (first, second)]
        self.assertIsNone(auto.consensus(votes, [], duration, "outro"))


class WorkerTests(AutomationFixture, unittest.TestCase):
    def setup_audio(self, two=True):
        self.registered(self.target)
        self.voted(12, "81")
        if two:
            self.voted(11, "83")
        rng = random.Random(1901)
        reference = [rng.getrandbits(32) for _ in range(161)]
        prefix = [rng.getrandbits(32) for _ in range(400)] + reference + [rng.getrandbits(32) for _ in range(160)]
        tail = [rng.getrandbits(32) for _ in range(721)]
        def audio(_source, start, length, _busy, **options):
            result = (prefix if start == 0 else tail, 125.0, length) if options.get("with_coverage") else (reference, 125.0)
            return result
        return audio

    def analyze(self, audio, duration=None):
        with mock.patch.object(auto, "provider_proxy", side_effect=lambda *a: contextlib.nullcontext("fixture")), \
             mock.patch.object(auto, "probe", return_value=(duration or self.target["duration_ms"], [])), \
             mock.patch.object(auto, "fingerprint", side_effect=audio):
            return auto.analyze(self.db, self.job(), busy_check)

    def test_worker_publishes_one_strong_reviewed_reference_without_online_times(self):
        audio = self.setup_audio(two=False)
        self.assertEqual(self.analyze(audio)[0], "done")
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE asset_key=? AND status='approved'", (self.target["asset_key"],)).fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE asset_key=? AND status='pending'", (self.target["asset_key"],)).fetchone()[0], 0)

    def test_high_central_match_with_unconfirmed_boundary_stays_pending(self):
        audio = self.setup_audio(two=False)
        from skip_analysis import matching_offset as compare
        def matching(words, target, step):
            return compare(words, target, step) if len(words) > 100 else None
        with mock.patch.object(auto, 'matching_offset', side_effect=matching):
            self.assertEqual(self.analyze(audio)[0], 'review')
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records WHERE asset_key=? AND status='approved'", (self.target['asset_key'],)).fetchone()[0], 0)

    def test_short_repeated_motif_does_not_block_the_unique_complete_intro(self):
        audio=self.setup_audio(two=False)
        def repeated(source,start,length,busy,**options):
            result=audio(source,start,length,busy,**options)
            if start==0 and options.get('with_coverage'):
                words,step,coverage=result
                # Repeat only the opening motif elsewhere, while the complete
                # reviewed sequence still occurs exactly once.
                words=words+[0]*100+words[400:453]+[0]*100
                self.assertIsNone(auto.matching_offset(words[400:453],words,step))
                return words,step,coverage
            return result
        self.assertEqual(self.analyze(repeated)[0],'done')

    def test_reported_runtime_mismatch_never_decodes_or_publishes(self):
        audio = self.setup_audio()
        with mock.patch.object(auto, "provider_proxy", side_effect=lambda *a: contextlib.nullcontext("fixture")), mock.patch.object(auto, "probe", return_value=(10_000, [])), mock.patch.object(auto, "fingerprint") as decode:
            self.assertEqual(auto.analyze(self.db, self.job(), busy_check)[0], "unmatched")
            decode.assert_not_called()

    def test_measured_runtime_is_adopted_only_for_verified_catalogue_asset(self):
        self.registered(self.target)
        with self.db() as con:
            con.execute("UPDATE skip_assets SET duration_ms=0 WHERE asset_key=?", (self.target["asset_key"],))
        audio = self.setup_audio()
        self.assertEqual(self.analyze(audio, 10_000)[0], "unmatched")
        with self.db() as con:
            con.execute("UPDATE skip_assets SET duration_ms=0 WHERE asset_key=?", (self.target["asset_key"],))
            con.execute("INSERT INTO skip_auto_assets VALUES(?,?)", (self.target["asset_key"], now()))
        self.analyze(audio, 10_000)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT duration_ms FROM skip_assets WHERE asset_key=?", (self.target["asset_key"],)).fetchone()[0], 10_000)

    def test_partial_target_cannot_project_marker_beyond_decoded_audio(self):
        audio = self.setup_audio()
        def partial(*args, **kwargs):
            result = audio(*args, **kwargs)
            return (*result[:2], 60_000) if kwargs.get("with_coverage") else result
        self.assertEqual(self.analyze(partial)[0], "no_match")

    def test_requeued_jobs_cannot_reset_daily_budget(self):
        self.registered(self.target)
        with self.db() as con:
            con.execute("INSERT INTO skip_analysis_budget VALUES(?,23)", (now()[:10],))
        with mock.patch.object(auto, "discover_one", return_value="idle"), mock.patch("skip_analysis_worker.analyze", return_value=("no_match", "fixture")):
            self.assertEqual(process_one(self.db), "no_match")
            with self.db() as con:
                con.execute("UPDATE skip_jobs SET status='queued',attempts=0")
            self.assertEqual(process_one(self.db), "daily_limit")


class DiscoveryTests(AutomationFixture, unittest.TestCase):
    def test_three_distinct_episodes_create_pending_repetition_without_manual_times(self):
        rng = random.Random(2201)
        shared = [rng.getrandbits(32) for _ in range(200)]
        for stream, episode, position in (("81", 12, 300), ("82", 13, 400), ("83", 14, 500)):
            data = self.descriptor(stream, episode)
            self.registered(data)
            words = [rng.getrandbits(32) for _ in range(position)] + shared + [rng.getrandbits(32) for _ in range(100)]
            with self.db() as con:
                auto.save_window(con, data, "intro", words, 125, 0, 120_000)
                if episode == 14:
                    self.assertTrue(auto.bootstrap(con, data, "intro"))
                    row = con.execute("SELECT * FROM skip_records WHERE source='audio_repetition'").fetchone()
                    self.assertEqual(row["status"], "pending")

    def test_silence_unrelated_music_and_multiple_occurrences_do_not_seed(self):
        rng = random.Random(2301)
        self.assertIsNone(auto.common_span([0] * 700, [0] * 700, 125))
        a, b = [[rng.getrandbits(32) for _ in range(700)] for _ in range(2)]
        self.assertIsNone(auto.common_span(a, b, 125))
        shared = [rng.getrandbits(32) for _ in range(200)]
        target = a[:100] + shared + a[100:300] + shared + a[300:400]
        self.assertIsNone(auto.common_span(target, b[:100] + shared + b[100:200], 125))

    def test_complete_reference_decoder_rejects_shortened_audio_before_fingerprinting(self):
        with mock.patch("skip_analysis.run", return_value=b"\0" * (11025 * 2 * 10)):
            with self.assertRaisesRegex(ValueError, "fingerprint_incomplete"):
                fingerprint("fixture", 0, 20_000, require_complete=True)


class RealAutomationTests(AutomationFixture, unittest.TestCase):
    rate = boundary_tests.RealBoundaryTests.rate
    clip = boundary_tests.RealBoundaryTests.clip

    @classmethod
    def setUpClass(cls):
        boundary_tests.RealBoundaryTests.setUpClass()
        cls.music = boundary_tests.RealBoundaryTests.music

    def test_two_real_references_corroborate_gain_and_aac_target(self):
        paths = {"81": self.clip("first.wav", 18043), "83": self.clip("second.wav", 24113, .82)}
        raw = self.clip("target.wav", 29347, .63)
        encoded = Path(self.temp.name) / "target.m4a"
        run(["ffmpeg", "-nostdin", "-v", "error", "-threads", "1", "-i", str(raw), "-c:a", "aac", "-b:a", "96k", str(encoded)], timeout=20)
        paths["82"] = encoded
        for stream, episode, start in (("81", 12, 18043), ("83", 11, 24113)):
            data = self.descriptor(stream, episode, duration_ms=probe(str(paths[stream]))[0])
            self.registered(data)
            with self.db() as con:
                record = add_record(con, data, "intro", start, start + 28000, False, self.device)
                con.execute("UPDATE skip_records SET status='approved',reviewed_at=? WHERE id=?", (now(), record["id"]))
        self.target = self.descriptor("82", 13, duration_ms=probe(str(encoded))[0])
        self.registered(self.target)
        def local(url, busy):
            return contextlib.nullcontext(str(paths[url.rsplit('/', 1)[-1].split('.')[0]]))
        with mock.patch.object(auto, "provider_proxy", side_effect=local):
            status, detail = auto.analyze(self.db, self.job(), busy_check)
        self.assertEqual(status, "done", detail)
        with self.db() as con:
            row = con.execute("SELECT * FROM skip_records WHERE source='auto_audio'").fetchone()
        self.assertIsNotNone(row)
        self.assertLessEqual(abs(row["start_ms"] - 29347), 150)
        self.assertLessEqual(abs(row["end_ms"] - 57347), 150)
        self.assertEqual(row["status"], "approved")


@unittest.skipUnless(REAL_FLASK, "Flask required for automatic policy API")
class AutomationApiTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        site = REAL_FLASK("automatic-policy-fixture", template_folder=str(Path(__file__).resolve().parents[1] / 'templates'))
        site.secret_key = "fixture-session-only"
        with self.db() as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture customer'")
        @site.get("/dashboard", endpoint="dashboard")
        def dashboard():
            return "Fixture dashboard"
        @site.get("/health", endpoint="health")
        def health():
            return {"status": "ok", "api_version": "0.8.2"}
        backend = types.ModuleType("app")
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        with mock.patch.dict(sys.modules, {"app": backend}):
            install(site, self.db)
        self.client = site.test_client()
        with self.client.session_transaction() as session:
            session["skip_csrf"] = "fixture-csrf"

    def test_policy_toggle_requires_csrf_and_existing_audio_opt_in(self):
        self.assertEqual(self.client.post("/admin/skip/automatic/1", data={"enabled": "1"}).status_code, 403)
        self.assertEqual(self.client.post("/admin/skip/automatic/3", data={"enabled": "1", "csrf": "fixture-csrf"}).status_code, 302)
        with self.db() as con:
            self.assertFalse(auto.enabled(con, 3))

    def test_human_withdrawal_blocks_machine_recreation_and_corrected_review_restores_reference(self):
        data = self.target
        self.registered(data)
        record = self.marker(data)
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_evidence VALUES(?, '{}', 0)", (record,))
        response = self.client.post(f"/admin/skip/{record}/review", data={"csrf": "fixture-csrf", "decision": "reject"})
        self.assertEqual(response.status_code, 302)
        with self.db() as con:
            self.assertTrue(auto.protected(con, data, "intro"))
        response = self.client.post(f"/admin/skip/{record}/review", data={"csrf": "fixture-csrf", "decision": "approve", "start": "00:04:43.043", "end": "00:05:09.573"})
        self.assertEqual(response.status_code, 302)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_auto_blocks").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT human_review FROM skip_auto_evidence WHERE record_id=?", (record,)).fetchone()[0], 1)

    def test_human_review_archives_generated_alternatives_for_same_file_only(self):
        self.registered(self.target)
        with self.db() as con:
            chosen = add_record(con, self.target, 'intro', 48000, 74530, False, source='audio')['id']
            other = add_record(con, self.target, 'intro', 48200, 74730, False, source='audio')['id']
            manual = add_record(con, self.target, 'intro', 49000, 75530, False, self.device)['id']
        response = self.client.post(f'/admin/skip/{chosen}/review', data={'csrf':'fixture-csrf', 'decision':'approve'})
        self.assertEqual(response.status_code, 302)
        with self.db() as con:
            statuses = {row['id']:row['status'] for row in con.execute('SELECT id,status FROM skip_records')}
            self.assertEqual((statuses[chosen], statuses[other], statuses[manual]), ('approved','superseded','pending'))

    def test_automatic_approval_is_returned_to_existing_player_api(self):
        self.registered(self.target)
        votes = [self.voted(12, "81"), self.voted(11, "83")]
        with self.db() as con:
            auto.publish(con, self.target, "intro", auto.consensus(votes, [], self.target["duration_ms"], "intro"))
        result = self.client.post("/v1/device/skip/lookup", json=self.target, headers={"Authorization": "Bearer fixture-token"})
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json["segments"][0]["source"], "auto_audio")
        self.assertEqual(result.json["segments"][0]["status"], "approved")

    def test_tmdb_setup_requires_csrf_and_never_echoes_key(self):
        key = "a" * 32
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_online_cooldown VALUES('tmdb','provider_http_401',?)", (int(time.time())+86400,))
            con.execute("INSERT INTO skip_auto_online_cooldown VALUES('theintrodb','provider_http_429',?)", (int(time.time())+43200,))
        self.assertEqual(self.client.post("/admin/skip/tmdb", data={"api_key": key}).status_code, 403)
        response = self.client.post("/admin/skip/tmdb", data={"csrf": "fixture-csrf", "api_key": key})
        self.assertEqual(response.status_code, 302)
        self.assertNotIn(key, response.get_data(as_text=True))
        self.assertNotIn(key, response.headers["Location"])
        with self.db() as con:
            self.assertEqual(con.execute("SELECT value FROM skip_auto_metadata_config").fetchone()[0], key)
            self.assertIsNone(con.execute("SELECT 1 FROM skip_auto_online_cooldown WHERE service='tmdb'").fetchone())
            self.assertIsNotNone(con.execute("SELECT 1 FROM skip_auto_online_cooldown WHERE service='theintrodb'").fetchone())

    def test_dashboard_renders_automatic_settings_without_exposing_api_key(self):
        key = '0123456789abcdef' * 2
        with self.db() as con:
            con.execute("INSERT INTO skip_auto_metadata_config VALUES('tmdb_api_key',?,?)", (key, now()))
        response = self.client.get('/admin/skip')
        self.assertEqual(response.status_code,200)
        html=response.get_data(as_text=True)
        self.assertIn('Automatik speichern',html)
        self.assertIn('TMDB-Suche: eingerichtet',html)
        self.assertNotIn(key,html)


if __name__ == "__main__":
    unittest.main()
