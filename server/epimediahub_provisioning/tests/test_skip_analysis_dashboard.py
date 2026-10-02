"""Series/season/episode navigation, bounded pages and preserved edit context."""
import hashlib
import json
from pathlib import Path
import sys
import types
import unittest
from unittest import mock
from urllib.parse import urlsplit, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import test_skip_analysis_automation as automation_tests
from skip_markers import marker_browser, media_groups, add_record, install, now


class DashboardFixture(automation_tests.AutomationFixture):
    def mark(self, stream, episode, season=2, kind="intro", **fields):
        data = self.descriptor(str(stream), episode, season=season, **fields)
        with self.db() as con:
            row = add_record(con, data, kind, 10000, 40000, False, self.device)
        return row["id"]


class NavigationTests(DashboardFixture, unittest.TestCase):
    def test_more_than_one_hundred_markers_are_accessible_through_series_pages(self):
        for series in range(23):
            key = hashlib.sha256(str(series).encode()).hexdigest()
            for episode in range(1, 7):
                self.mark(1000 + series * 10 + episode, episode, source_key=key, title=f"Serie {series:02d}")
        with self.db() as con:
            first = marker_browser(con, "pending")
            second = marker_browser(con, "pending", page=2)
            self.assertEqual((first["total"], first["pages"], len(first["groups"])), (23, 2, 20))
            self.assertEqual([g["title"] for g in second["groups"]], ["Serie 20", "Serie 21", "Serie 22"])
            last = second["groups"][-1]
            selected = marker_browser(con, "pending", last["source_key"], season=2, page=2)
            self.assertEqual(len(selected["groups"][-1]["seasons"][0]["episodes"]), 6)

    def test_numeric_season_episode_order_and_whole_episode_pages(self):
        for episode in reversed(range(1, 31)):
            self.mark(1000 + episode, episode, kind="intro")
            self.mark(1000 + episode, episode, kind="outro")
        self.mark(1110, 1, season=10)
        with self.db() as con:
            page = marker_browser(con, "pending", self.seed["source_key"], season=2)
            group = page["groups"][0]
            self.assertEqual([s["season"] for s in group["seasons"]], [2, 10])
            episodes = group["seasons"][0]["episodes"]
            self.assertEqual([e["episode"] for e in episodes], list(range(1, 26)))
            self.assertTrue(all(len(e["rows"]) == 2 for e in episodes))
            following = marker_browser(con, "pending", self.seed["source_key"], season=2, episode_page=2)
            self.assertEqual([e["episode"] for e in following["groups"][0]["seasons"][0]["episodes"]], list(range(26, 31)))

    def test_same_title_different_source_is_separate_and_filters_still_apply(self):
        first = self.mark(1001, 1)
        self.mark(1002, 1, source_key="c" * 64)
        with self.db() as con:
            self.assertEqual(marker_browser(con, "pending")["total"], 2)
            con.execute("UPDATE skip_records SET status='approved' WHERE id=?", (first,))
            self.assertEqual(marker_browser(con, "pending")["total"], 1)
            self.assertEqual(marker_browser(con, "approved")["groups"][0]["source_key"], self.seed["source_key"])

    def test_unselected_season_does_not_load_marker_forms_and_invalid_pages_are_bounded(self):
        self.mark(1001, 1)
        with self.db() as con:
            root = marker_browser(con, "pending", self.seed["source_key"], page="9999999")
            self.assertEqual(root["page"], 1)
            self.assertEqual(root["groups"][0]["seasons"][0]["episodes"], [])
            self.assertEqual(marker_browser(con, "pending", "invalid", page="-1")["source_key"], "")


@unittest.skipUnless(automation_tests.REAL_FLASK, "Flask required for HTML/API navigation")
class DashboardApiTests(DashboardFixture, unittest.TestCase):
    def setUp(self):
        super().setUp()
        site = automation_tests.REAL_FLASK("series-dashboard-fixture", template_folder=str(Path(__file__).resolve().parents[1] / "templates"))
        site.secret_key = "fixture-session-only"
        with self.db() as con:
            con.execute("ALTER TABLE customers ADD COLUMN name TEXT NOT NULL DEFAULT 'Fixture customer'")
        @site.get("/dashboard", endpoint="dashboard")
        def dashboard():
            return "Dashboard"
        @site.get("/health", endpoint="health")
        def health():
            return site.response_class(json.dumps({"status": "ok"}), mimetype="application/json")
        backend = types.ModuleType("app")
        backend.digest = lambda value: value
        backend.web_auth = lambda: None
        with mock.patch.dict(sys.modules, {"app": backend}):
            install(site, self.db)
        self.client = site.test_client()
        with self.client.session_transaction() as session:
            session["skip_csrf"] = "fixture-csrf"

    def view(self, **params):
        response = self.client.get("/admin/skip", query_string=params)
        self.assertEqual(response.status_code, 200)
        return response.get_data(as_text=True)

    def test_series_then_season_then_episode_reveals_edit_controls(self):
        record = self.mark(1001, 13)
        root = self.view()
        self.assertIn("Lie to Me", root)
        self.assertNotIn(f'data-record-id="{record}"', root)
        selected = self.view(series=self.seed["source_key"])
        self.assertIn("Staffel 2", selected)
        self.assertNotIn(f'data-record-id="{record}"', selected)
        episode = self.view(series=self.seed["source_key"], season=2, episode=13)
        self.assertLess(episode.index('id="series-'), episode.index('id="season-2"'))
        self.assertLess(episode.index('id="season-2"'), episode.index('id="episode-13"'))
        self.assertIn(f'data-record-id="{record}"', episode)
        self.assertIn("Geprüfte Zeiten freigeben", episode)

    def test_review_and_identity_return_to_exact_series_episode_and_filter(self):
        record = self.mark(1001, 13)
        with self.db() as con:
            con.execute("UPDATE skip_records SET status='approved' WHERE id=?", (record,))
        data = dict(csrf="fixture-csrf", decision="approve", return_state="approved", return_page="1", return_episode_page="1")
        response = self.client.post(f"/admin/skip/{record}/review", data=data)
        query = parse_qs(urlsplit(response.headers["Location"]).query)
        self.assertEqual((query["series"], query["season"], query["episode"], query["state"]), ([self.seed["source_key"]], ["2"], ["13"], ["approved"]))
        body = self.client.get(response.headers["Location"]).get_data(as_text=True)
        self.assertIn('id="episode-13" open', body)
        response = self.client.post(f"/admin/skip/{record}/identity", data=dict(csrf="fixture-csrf", imdb_id="tt1235099", tmdb_id="8358", return_state="approved"))
        self.assertEqual(parse_qs(urlsplit(response.headers["Location"]).query)["episode"], ["13"])

    def test_recent_analysis_and_online_status_are_grouped_without_losing_details(self):
        self.registered(self.target)
        with self.db() as con:
            con.execute("UPDATE skip_jobs SET detail='Wartet auf die Analyse'")
            con.execute("INSERT INTO skip_auto_online VALUES(?,?, '[]','Keine passenden Online-Zeiten',?)", (self.target["asset_key"], self.target["duration_ms"], 1))
        body = self.view()
        self.assertIn("Letzte Analysen", body)
        self.assertIn("Folge 13", body)
        self.assertIn("Wartet auf die Analyse", body)
        self.assertIn("Keine passenden Online-Zeiten", body)

    def test_same_episode_in_different_files_is_labelled_as_separate_versions(self):
        self.mark(1001,13)
        self.mark(1002,13)
        body=self.view(series=self.seed['source_key'],season=2,episode=13)
        self.assertIn('2 Videofassungen',body)
        self.assertIn('Videofassung 1',body)
        self.assertIn('Videofassung 2',body)

    def test_titles_are_escaped_and_films_do_not_show_fictitious_seasons(self):
        self.mark(1001, 0, season=0, media_type="movie", title="<script>alert(1)</script>")
        body = self.view(series=self.seed["source_key"])
        self.assertIn("&lt;script&gt;", body)
        self.assertNotIn("<script>alert(1)</script>", body)
        self.assertNotIn("Staffel 0", body)
        self.assertIn("Geprüfte Zeiten freigeben", body)


if __name__ == "__main__":
    unittest.main()
