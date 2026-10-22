"""Private external marker endpoints: session gate, filters and HTML escaping."""
import unittest
from unittest import mock
from flask import Flask

import mobile_flask


SAMPLE = {
    "scope":"analysis_playlists_only","read_only":True,
    "total":1,"page":1,"page_size":50,"has_more":False,
    "source_counts":{"introdb":1,"theintrodb":0},
    "cached_episode_count":1,"cache_entry_count":3,"generated_at_epoch":100,
    "markers":[{
        "playlist_id":"8","playlist":"4K ANALYSE","title":"<script>alert(1)</script>",
        "season":1,"episode":2,"source":"introdb","kind":"intro",
        "start_ms":1000,"end_ms":59000,"cache_status":"active"
    }]
}


class ExternalMarkerRoutes(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.app.secret_key="synthetic-testing-secret"
        mobile_flask.install(self.app)
        self.client=self.app.test_client()

    def auth(self):
        with self.client.session_transaction() as session:
            session["admin"]=True

    def test_only_admin_may_access_json_and_html(self):
        self.assertEqual(self.client.get("/admin/mobile/episcene/markers").status_code,401)
        self.assertEqual(self.client.get("/admin/mobile/episcene/markers/view").status_code,401)

    def test_private_json_filters_are_forwarded(self):
        self.auth()
        with mock.patch.object(mobile_flask,"list_external_markers",return_value=SAMPLE) as read:
            response=self.client.get("/admin/mobile/episcene/markers?playlist=8&source=introdb&state=active&q=Berlin")
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers["Cache-Control"],"private, no-store")
        self.assertEqual(response.json["total"],1)
        self.assertEqual(read.call_args.kwargs["playlist"],"8")
        self.assertEqual(read.call_args.kwargs["source"],"introdb")
        self.assertEqual(read.call_args.kwargs["state"],"active")

    def test_html_does_not_inject_series_titles(self):
        self.auth()
        with mock.patch.object(mobile_flask,"list_external_markers",return_value=SAMPLE):
            response=self.client.get("/admin/mobile/episcene/markers/view")
        self.assertEqual(response.status_code,200)
        text=response.get_data(as_text=True)
        self.assertIn("&lt;script&gt;",text)
        self.assertNotIn("<script>alert(1)</script>",text)
        self.assertEqual(response.headers["X-Frame-Options"],"DENY")

    def test_missing_cache_returns_service_unavailable(self):
        self.auth()
        with mock.patch.object(mobile_flask,"list_external_markers",
               side_effect=mobile_flask.ExternalMarkerUnavailable("not_found")):
            result=self.client.get("/admin/mobile/episcene/markers")
        self.assertEqual(result.status_code,503)
        self.assertNotIn("not_found",result.get_data(as_text=True))

    def test_invalid_params_block_before_read(self):
        self.auth()
        with mock.patch.object(mobile_flask,"list_external_markers",side_effect=ValueError):
            self.assertEqual(self.client.get("/admin/mobile/episcene/markers").status_code,400)
            self.assertEqual(self.client.get("/admin/mobile/episcene/markers/view").status_code,400)


if __name__=="__main__":
    unittest.main()
