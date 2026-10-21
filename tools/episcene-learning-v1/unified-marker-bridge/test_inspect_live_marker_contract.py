"""Read-only route inventory regression tests on synthetic backend files."""
import json
import tempfile
import unittest
from pathlib import Path
from inspect_live_marker_contract import inspect, route_inventory, safe_route

SAMPLE = '''
from flask import Flask
app=Flask(__name__)
@app.get("/api/skip/markers")
def get_skip_markers(): pass
@app.route("/skip/review/<int:record_id>", methods=["POST"])
def review_marker(): pass
@app.get("/account/token/secret_value")
def password_handler(): pass
@app.post("https://credentials.invalid/skip")
def weird_handler(): pass
app.add_url_rule("/episcene/summary", "summary", lambda: None)
def irrelevant(): pass
'''

class RouteSafetyTests(unittest.TestCase):
    def test_only_literal_safe_marker_routes(self):
        routes, functions = route_inventory(SAMPLE)
        self.assertEqual({x[0] for x in routes},
                         {"/api/skip/markers", "/skip/review/<int:record_id>",
                          "/episcene/summary"})
        self.assertIn("get_skip_markers", functions)
        self.assertFalse(safe_route("/token/skip/secret"))
        self.assertFalse(safe_route("https://abc.test/skip?password=hidden"))

    def test_does_not_read_or_print_secrets(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "api.py").write_text(SAMPLE)
            (root / "password.py").write_text('PRIVATE_KEY="SECRET_NEVER_REPORT_ME"\n')
            (root / "subdir").mkdir()
            (root / "subdir" / "routes.py").write_text(
                '@bp.route("/episode/info", methods=["GET"])\ndef episode_metadata(): pass\n')
            report = inspect(root, state=lambda _name: "not_active")
            out = json.dumps(report)
            self.assertIn("/episode/info", out)
            self.assertNotIn("SECRET_NEVER_REPORT_ME", out)
            self.assertNotIn("PRIVATE_KEY", out)
            self.assertTrue(report["no_service_database_or_file_modified"])
            self.assertEqual(report["production_service"], "not_active")

    def test_missing_backend_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            report = inspect(Path(folder) / "missing")
            self.assertEqual(report["status"], "BLOCKED")
            self.assertEqual(report["backend_route_inventory"], [])

if __name__ == "__main__":
    unittest.main()
