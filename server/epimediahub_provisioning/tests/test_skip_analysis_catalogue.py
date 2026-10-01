"""Full/nightly inventory against real SQLite, without live provider accounts."""
from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import types
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_skip_analysis_automation as automation_tests
AutomationFixture = automation_tests.AutomationFixture
REAL_FLASK = automation_tests.REAL_FLASK
import skip_automation as auto
import skip_catalogue as catalogue
from skip_analysis_worker import busy_check, process_one
from skip_markers import now, migrate, install

START = int(datetime.fromisoformat("2026-10-01T22:50:00+02:00").timestamp())


class CatalogueFixture(AutomationFixture):
    def setUp(self):
        super().setUp()
        self.listing = [dict(series_id=501, name="[DE] Lie to Me (2009) [4K]", year="2009", last_modified=123),
                        dict(series_id=502, name="Other Show", year="2015", last_modified=124)]
        self.infos = {
            "501": dict(info=dict(name="[DE] Lie to Me (2009) [4K]", year="2009"), episodes={
                "1": [dict(id=101 + i, episode_num=1 + i, container_extension="mkv", info={"duration_secs": 2640}) for i in range(3)],
                "2": [dict(id=110, episode_num=1, container_extension="mp4")]}),
            "502": dict(info=dict(name="Other Show", year="2015"), episodes={
                "1": [dict(id=201, episode_num=1, container_extension="mp4")]})}
        with self.db() as con:
            self.assertTrue(catalogue.start(con, 1))

    def provider(self, _playlist, action, _busy, **params):
        return self.listing if action == "get_series" else self.infos[params["series_id"]]

    def advance(self, timestamp=START, **params):
        with mock.patch.object(auto, "provider_api", side_effect=self.provider) as fetch:
            result = catalogue.advance(self.db, busy_check, timestamp, **params)
        return result, fetch

    def finish_jobs(self):
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET status='no_match',attempts=1,detail='already checked'")
            return [tuple(r) for r in con.execute("SELECT * FROM skip_jobs ORDER BY id")]

    def add_episode(self, stream=104):
        self.infos["501"]["episodes"]["1"].append(dict(id=stream, episode_num=4, container_extension="mkv"))


class FullCatalogueTests(CatalogueFixture, unittest.TestCase):
    def test_full_catalogue_registers_unwatched_series_and_all_seasons(self):
        result, fetch = self.advance()
        self.assertEqual(result, "finished")
        self.assertEqual(fetch.call_count, 3)
        with self.db() as con:
            assets = con.execute("SELECT * FROM skip_assets ORDER BY stream_id").fetchall()
            self.assertEqual(len(assets), 5)
            self.assertEqual([r["duration_ms"] for r in assets], [0] * 5)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_auto_assets").fetchone()[0], 5)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs WHERE status='queued'").fetchone()[0], 5)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_records").fetchone()[0], 0)
            state = con.execute("SELECT * FROM skip_catalogue_runs").fetchone()
            self.assertEqual((state["full_done"], state["phase"], state["checked"], state["total"], state["queued"]), (1, "idle", 2, 2, 5))
            expected = hashlib.sha256(b"provider.example:-1|true|501|Lie to Me|2009").hexdigest()
            self.assertEqual(assets[0]["source_key"], expected)
            self.assertEqual((assets[0]["title"], assets[0]["year"]), ("Lie to Me", "2009"))

    def test_cursor_survives_migration_and_restart_without_duplicate_jobs(self):
        self.advance(max_steps=2)
        with self.db() as con:
            before = con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0]
            self.assertEqual(con.execute("SELECT phase FROM skip_catalogue_runs").fetchone()[0], "full")
            migrate(con)
        self.advance()
        with self.db() as con:
            self.assertGreater(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], before)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs").fetchone()[0], 5)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs GROUP BY asset_key HAVING COUNT(*)>1").fetchall(), [])

    def test_repeated_start_does_not_reset_incomplete_or_completed_work(self):
        self.advance(max_steps=2)
        with self.db() as con:
            before = tuple(con.execute("SELECT * FROM skip_catalogue_runs").fetchone())
            catalogue.start(con, 1)
            self.assertEqual(tuple(con.execute("SELECT * FROM skip_catalogue_runs").fetchone()), before)
        self.advance()
        jobs = self.finish_jobs()
        with self.db() as con:
            catalogue.start(con, 1)
        self.advance(timestamp=START + 60)
        with self.db() as con:
            self.assertEqual([tuple(r) for r in con.execute("SELECT * FROM skip_jobs ORDER BY id")], jobs)

    def test_catalogue_uses_client_name_normalization_and_year_precedence(self):
        self.infos["501"]["info"] = dict(name="(GER) | Lie to Me (2009) - FULL HD", releaseDate="2009-01-21")
        # The literal separator after a language prefix is intentionally retained,
        # exactly as in the Android hash (fuzzy normalization is only for TMDB).
        self.assertEqual(catalogue.player_title("GER: Lie to Me [2009] [HD]"), "Lie to Me")
        self.assertEqual(catalogue.player_title("(GER) Lie to Me (2009) - FULL HD"), "Lie to Me")
        self.advance()
        with self.db() as con:
            row = con.execute("SELECT title,year FROM skip_assets WHERE stream_id='101'").fetchone()
            self.assertEqual(tuple(row), ("| Lie to Me", "2009"))

    def test_list_storage_whitelists_metadata_and_strips_credentials_urls(self):
        self.listing[0].update(stream_url="https://provider.example/TEST_PROVIDER_SECRET", password="TEST_PROVIDER_SECRET", username="account")
        self.advance()
        with self.db() as con:
            payload = con.execute("SELECT payload_json FROM skip_catalogue_series WHERE series_id='501'").fetchone()[0]
        self.assertNotIn("TEST_PROVIDER_SECRET", payload)
        self.assertNotIn("https://", payload)
        self.assertEqual(set(json.loads(payload)), {"series_id", "name", "year", "release"})

    def test_duplicate_series_metadata_is_ambiguous_and_never_fetched(self):
        self.listing += [self.listing[0] | {"name": "Different Title"}]
        self.advance()
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 1)

    def test_duplicate_files_numbers_or_unsafe_extensions_reject_series_atomically(self):
        cases = [dict(id=101, episode_num=4, container_extension="mkv"),
                 dict(id=104, episode_num=1, container_extension="mkv"),
                 dict(id=104, episode_num=4, container_extension="m3u8"),
                 dict(id=104, episode_num=4, season=2, container_extension="mkv")]
        for extra in cases:
            with self.subTest(extra=extra):
                self.infos["501"]["episodes"]["1"] = [dict(id=101, episode_num=1, container_extension="mkv"), extra]
                with self.db() as con:
                    con.execute("DELETE FROM skip_catalogue_series")
                    con.execute("UPDATE skip_catalogue_runs SET full_done=0,phase='idle',next_due=0")
                self.advance()
                with self.db() as con:
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets WHERE stream_id IN ('101','104')").fetchone()[0], 0)
                    self.assertEqual(con.execute("SELECT status FROM skip_catalogue_series WHERE series_id='501'").fetchone()[0], "failed")

    def test_cross_season_duplicate_file_is_rejected(self):
        self.infos["501"]["episodes"]["2"][0]["id"] = 101
        self.advance()
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 1)

    def test_existing_client_identity_and_human_markers_are_preserved(self):
        observed = self.descriptor("101", 1, season=1, source_key="c" * 64)
        self.registered(observed)
        record = self.marker(observed)
        self.advance()
        with self.db() as con:
            row = con.execute("SELECT * FROM skip_assets WHERE asset_key=?", (observed["asset_key"],)).fetchone()
            self.assertEqual((row["source_key"], row["duration_ms"]), ("c" * 64, observed["duration_ms"]))
            self.assertEqual(con.execute("SELECT status,start_ms,end_ms FROM skip_records WHERE id=?", (record,)).fetchone()[:], ("approved", 283043, 309573))

    def test_same_provider_file_with_conflicting_numbering_is_never_relabelled(self):
        observed = self.descriptor("101", 99, season=4)
        self.registered(observed)
        self.advance()
        with self.db() as con:
            self.assertEqual(con.execute("SELECT season,episode FROM skip_assets WHERE stream_id='101'").fetchone()[:], (4, 99))
            self.assertFalse(con.execute("SELECT 1 FROM skip_catalogue_episodes WHERE asset_key=?", (observed["asset_key"],)).fetchone())


class NightlyCatalogueTests(CatalogueFixture, unittest.TestCase):
    def test_before_three_am_does_not_refetch_or_reset_jobs(self):
        self.advance()
        jobs = self.finish_jobs()
        result, fetch = self.advance(START + 3 * 3600)
        self.assertEqual(result, "idle")
        fetch.assert_not_called()
        with self.db() as con:
            self.assertEqual([tuple(r) for r in con.execute("SELECT * FROM skip_jobs ORDER BY id")], jobs)

    def test_unchanged_nightly_listing_never_downloads_existing_episode_audio(self):
        self.advance()
        jobs = self.finish_jobs()
        result, fetch = self.advance(catalogue.next_night(START))
        self.assertEqual(result, "listed")
        self.assertEqual(fetch.call_count, 1)
        with self.db() as con:
            self.assertEqual([tuple(r) for r in con.execute("SELECT * FROM skip_jobs ORDER BY id")], jobs)

    def test_changed_existing_series_queues_only_new_episode_with_priority(self):
        self.advance()
        old = self.finish_jobs()
        self.listing[0]["last_modified"] += 1
        self.add_episode()
        self.advance(catalogue.next_night(START))
        with self.db() as con:
            jobs = [tuple(r) for r in con.execute("SELECT * FROM skip_jobs ORDER BY id")]
            self.assertEqual(jobs[:-1], old)
            row = con.execute("SELECT j.status,p.priority FROM skip_jobs j JOIN skip_assets a USING(asset_key) JOIN skip_catalogue_priority p USING(asset_key) WHERE a.stream_id='104'").fetchone()
            self.assertEqual(tuple(row), ("queued", 0))

    def test_new_series_is_discovered_without_opening_the_app(self):
        self.advance()
        self.finish_jobs()
        self.listing.append(dict(series_id=503, name="New Show", year="2026", last_modified=999))
        self.infos["503"] = dict(info=dict(name="New Show", year="2026"), episodes={"1": [dict(id=301, episode_num=1)]})
        self.advance(catalogue.next_night(START))
        with self.db() as con:
            row = con.execute("SELECT a.title,j.status FROM skip_assets a JOIN skip_jobs j USING(asset_key) WHERE stream_id='301'").fetchone()
            self.assertEqual(tuple(row), ("New Show", "queued"))

    def test_missing_provider_timestamp_checks_episode_lists_each_night(self):
        self.listing[0].pop("last_modified")
        self.advance()
        old = self.finish_jobs()
        self.add_episode()
        self.advance(catalogue.next_night(START))
        with self.db() as con:
            self.assertEqual([tuple(r) for r in con.execute("SELECT * FROM skip_jobs ORDER BY id")][:-1], old)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs").fetchone()[0], 6)

    def test_weekly_control_finds_updates_when_provider_timestamp_is_stale(self):
        self.advance()
        self.finish_jobs()
        self.add_episode()
        self.advance(START + 8 * 86400)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs").fetchone()[0], 6)

    def test_changed_catalogue_file_reprobes_runtime_but_preserves_approved_markers(self):
        self.advance()
        self.finish_jobs()
        with self.db() as con:
            con.execute("UPDATE skip_assets SET duration_ms=2640325 WHERE stream_id='101'")
            data = dict(con.execute("SELECT * FROM skip_assets WHERE stream_id='101'").fetchone())
        marker = self.marker(data | dict(imdb_id="", tmdb_id=0))
        self.listing[0]["last_modified"] += 1
        self.infos["501"]["episodes"]["1"][0]["info"]["duration_secs"] = 2500
        self.advance(catalogue.next_night(START))
        with self.db() as con:
            self.assertEqual(con.execute("SELECT duration_ms FROM skip_assets WHERE stream_id='101'").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT status FROM skip_records WHERE id=?", (marker,)).fetchone()[0], "approved")

    def test_changed_player_observed_file_keeps_reported_runtime(self):
        observed = self.descriptor("101", 1, season=1)
        self.registered(observed)
        self.advance()
        self.finish_jobs()
        self.listing[0]["last_modified"] += 1
        self.infos["501"]["episodes"]["1"][0]["info"]["duration_secs"] = 2500
        self.advance(catalogue.next_night(START))
        with self.db() as con:
            self.assertEqual(con.execute("SELECT duration_ms FROM skip_assets WHERE stream_id='101'").fetchone()[0], observed["duration_ms"])

    def test_failed_series_is_retried_next_night_without_repeating_completed_files(self):
        self.infos["501"] = {"invalid": "TEST_PROVIDER_SECRET"}
        self.advance()
        self.assertFalse(self.job(self.target))
        self.advance(START + 60)  # Complete the initial inventory after the failed series.
        self.infos["501"] = dict(info=dict(name="Lie to Me", year="2009"), episodes={"1": [dict(id=101, episode_num=1)]})
        _, fetch = self.advance(catalogue.next_night(START))
        self.assertEqual(fetch.call_count, 2)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs").fetchone()[0], 2)
            self.assertNotIn("TEST_PROVIDER_SECRET", str([tuple(x) for x in con.execute("SELECT * FROM skip_catalogue_runs")]))

    def test_removed_series_retains_existing_markers_and_is_not_refetched(self):
        self.advance()
        self.listing = self.listing[1:]
        _, fetch = self.advance(catalogue.next_night(START))
        self.assertEqual(fetch.call_count, 1)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 5)

    def test_next_night_is_berlin_three_am_across_daylight_saving_changes(self):
        for current, expected in (("2026-10-01T22:50:00+02:00", "2026-10-02T03:00:00+02:00"),
                                  ("2026-10-24T22:50:00+02:00", "2026-10-25T03:00:00+01:00"),
                                  ("2027-03-27T22:50:00+01:00", "2027-03-28T03:00:00+02:00"),
                                  ("2026-10-02T03:00:00+02:00", "2026-10-03T03:00:00+02:00")):
            with self.subTest(current=current):
                self.assertEqual(catalogue.next_night(datetime.fromisoformat(current).timestamp()), int(datetime.fromisoformat(expected).timestamp()))


class GuardAndBudgetTests(CatalogueFixture, unittest.TestCase):
    def test_busy_account_and_disabled_automatic_never_open_provider(self):
        with self.db() as con:
            con.execute("INSERT INTO skip_presence VALUES(1,1,?)", (int(time.time()) + 70,))
        result, fetch = self.advance()
        self.assertEqual(result, "queued")
        fetch.assert_not_called()
        with self.db() as con:
            con.execute("UPDATE skip_auto_settings SET enabled=0")
        result, fetch = self.advance()
        self.assertEqual(result, "idle")
        fetch.assert_not_called()

    def test_busy_playlist_does_not_block_independent_provider_account(self):
        with self.db() as con:
            config = self.config | {"xtream_username": "independent"}
            con.execute("UPDATE customer_playlists SET config_json=? WHERE id=2", (json.dumps(config),))
            con.execute("INSERT INTO skip_auto_settings VALUES(2,1,0,?)", (now(),))
            catalogue.start(con, 2)
            con.execute("INSERT INTO skip_presence VALUES(1,1,?)", (int(time.time()) + 70,))
        self.advance(max_steps=2)
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets WHERE playlist_id=1").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets WHERE playlist_id=2").fetchone()[0], 1)

    def test_disabling_during_metadata_fetch_prevents_registration(self):
        def fetch(*args, **kwargs):
            with self.db() as con:
                con.execute("UPDATE skip_catalogue_settings SET enabled=0")
            return self.provider(*args, **kwargs)
        with mock.patch.object(auto, "provider_api", side_effect=fetch):
            self.assertEqual(catalogue.advance(self.db, busy_check, START), "disabled")
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 0)

    def test_failed_listing_backs_off_without_credentials_in_status(self):
        with mock.patch.object(auto, "provider_api", side_effect=OSError("https://TEST_PROVIDER_SECRET")) as fetch:
            self.assertEqual(catalogue.advance(self.db, busy_check, START), "failed")
            self.assertEqual(catalogue.advance(self.db, busy_check, START + 60), "idle")
            self.assertEqual(fetch.call_count, 1)
        with self.db() as con:
            self.assertNotIn("TEST_PROVIDER_SECRET", con.execute("SELECT detail FROM skip_catalogue_runs").fetchone()[0])

    def test_inventory_continues_when_audio_daily_budget_is_exhausted(self):
        with self.db() as con:
            con.execute("INSERT INTO skip_analysis_budget VALUES(?,96)", (now()[:10],))
        with mock.patch.object(auto, "provider_api", side_effect=self.provider), mock.patch("skip_analysis_worker.analyze") as analyze:
            self.assertEqual(process_one(self.db), "daily_limit")
            analyze.assert_not_called()
        with self.db() as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_assets").fetchone()[0], 5)

    def test_persistent_bulk_budget_survives_requeue(self):
        self.advance()
        with self.db() as con:
            con.execute("INSERT INTO skip_analysis_budget VALUES(?,95)", (now()[:10],))
        with mock.patch.object(catalogue, "advance", return_value="idle"), mock.patch.object(auto, "discover_one", return_value="idle"), mock.patch("skip_analysis_worker.analyze", return_value=("no_match", "checked")):
            self.assertEqual(process_one(self.db), "no_match")
            with self.db() as con:
                con.execute("UPDATE skip_jobs SET status='queued',attempts=0")
            self.assertEqual(process_one(self.db), "daily_limit")

    def test_new_nightly_episodes_take_priority_over_bulk_backlog(self):
        self.advance()
        self.listing[0]["last_modified"] += 1
        self.add_episode()
        self.advance(catalogue.next_night(START))
        with mock.patch.object(catalogue, "advance", return_value="idle"), mock.patch.object(auto, "discover_one", return_value="idle"), mock.patch("skip_analysis_worker.analyze", return_value=("no_match", "checked")) as analyze:
            self.assertEqual(process_one(self.db), "no_match")
        with self.db() as con:
            asset = con.execute("SELECT stream_id FROM skip_assets WHERE asset_key=?", (analyze.call_args.args[1]["asset_key"],)).fetchone()
            self.assertEqual(asset[0], "104")


@unittest.skipUnless(REAL_FLASK, "Full Flask API dependencies required")
class CatalogueApiTests(AutomationFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        site = REAL_FLASK("catalogue-policy-fixture", template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
        site.secret_key = "fixture-session-only"
        with self.db() as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture customer'")
        @site.get("/dashboard", endpoint="dashboard")
        def dashboard():
            return "Fixture dashboard"
        @site.get("/health", endpoint="health")
        def health():
            return site.response_class(json.dumps({"status": "ok", "api_version": "0.8.2"}), mimetype="application/json")
        backend = types.ModuleType("app")
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        with mock.patch.dict(sys.modules, {"app": backend}):
            install(site, self.db)
        self.client = site.test_client()
        with self.client.session_transaction() as session:
            session["skip_csrf"] = "fixture-csrf"

    def test_full_start_requires_csrf_and_only_activates_existing_audio_automatic_sources(self):
        self.assertEqual(self.client.post("/admin/skip/catalogue", data={"daily_limit": "96"}).status_code, 403)
        result = self.client.post("/admin/skip/catalogue", data={"csrf": "fixture-csrf", "daily_limit": "96"})
        self.assertEqual(result.status_code, 302)
        with self.db() as con:
            self.assertEqual([r[0] for r in con.execute("SELECT playlist_id FROM skip_catalogue_settings WHERE enabled=1")], [1])
            self.assertEqual(catalogue.daily_limit(con), 96)

    def test_invalid_budget_and_disabled_source_are_rejected(self):
        for value in ("0", "501", "-1", "1.5", "96x"):
            self.assertEqual(self.client.post("/admin/skip/catalogue", data={"csrf": "fixture-csrf", "daily_limit": value}).status_code, 400)
        self.client.post("/admin/skip/catalogue/3", data={"csrf": "fixture-csrf", "enabled": "1"})
        with self.db() as con:
            self.assertFalse(con.execute("SELECT 1 FROM skip_catalogue_settings WHERE playlist_id=3").fetchone())

    def test_dashboard_renders_inventory_and_budget_without_echoing_key(self):
        with self.db() as con:
            catalogue.start(con, 1)
            key = "0123456789abcdef" * 2
            con.execute("INSERT INTO skip_auto_metadata_config VALUES('tmdb_api_key',?,?)", (key, now()))
        body = self.client.get("/admin/skip").get_data(as_text=True)
        for text in ("Gesamtkatalog", "03:00", "Erfasste Folgen", "Noch zu analysieren", "Weitere Katalogprüfungen ausschalten"):
            self.assertIn(text, body)
        self.assertNotIn(key, body)
        self.assertTrue(self.client.get("/health").json["features"]["skip_nightly_catalogue"])

    def test_stop_preserves_enqueued_jobs_and_completed_records(self):
        with self.db() as con:
            catalogue.start(con, 1)
        self.registered(self.seed)
        marker = self.marker()
        self.client.post("/admin/skip/catalogue/1", data={"csrf": "fixture-csrf", "enabled": "0"})
        with self.db() as con:
            self.assertFalse(catalogue.active(con, 1))
            self.assertEqual(con.execute("SELECT COUNT(*) FROM skip_jobs").fetchone()[0], 1)
            self.assertEqual(con.execute("SELECT status FROM skip_records WHERE id=?", (marker,)).fetchone()[0], "approved")


if __name__ == "__main__":
    unittest.main()
