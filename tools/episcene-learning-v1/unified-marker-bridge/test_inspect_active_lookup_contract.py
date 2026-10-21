"""No-network, synthetic regression tests for focused active handler inventory."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from inspect_active_lookup_contract import inspect_source, inspect_knowledge, report

SOURCE = '''
from flask import request, jsonify
@app.post("/v1/device/skip/lookup")
def v082_skip_lookup():
    secret = "PASSWORD_VALUE_MUST_NOT_LEAK"
    url = "https://provider.example/user/SECRET"
    payload = request.get_json()
    playlist_id = payload.get("playlist_id")
    asset = payload.get("asset_key")
    row = db.execute("SELECT start_ms,end_ms FROM skip_records WHERE asset_key=?", (asset,))
    return jsonify({"markers": [], "status": "ok"})
@app.post("/v1/device/skip/fingerprint")
def v126_skip_fingerprint():
    raw = request.get_json()
    return jsonify({"status": raw.get("status"), "fingerprint": "mock"})
@app.post("/v1/device/skip/submit")
def v082_skip_submit():
    return jsonify({"status": "ok"})
'''

class ActiveContractTests(unittest.TestCase):
    def test_handler_shapes_do_not_leak_literals(self):
        found = inspect_source(SOURCE)
        self.assertTrue(found["v082_skip_lookup"]["present"])
        self.assertEqual(found["v082_skip_lookup"]["route_declarations"],
                         [{"method": "POST", "path": "/v1/device/skip/lookup"}])
        self.assertIn("playlist_id", found["v082_skip_lookup"]["possible_field_names"])
        self.assertIn("markers", found["v082_skip_lookup"]["possible_response_dict_keys"])
        self.assertIn("skip_records", found["v082_skip_lookup"]["known_database_table_mentions"])
        self.assertFalse(found["v082_skip_lookup"]["endpoint_authorization_verified"])
        for secret in ("PASSWORD_VALUE_MUST_NOT_LEAK", "provider.example",
                       "SELECT start_ms", "SECRET"):
            self.assertNotIn(secret, json.dumps(found))

    def test_source_and_knowledge_read_only(self):
        with tempfile.TemporaryDirectory() as td:
            folder = Path(td)
            source = folder / "skip_markers.py"
            store = folder / "unified.sqlite3"
            source.write_text(SOURCE)
            with sqlite3.connect(store) as db:
                db.execute("CREATE TABLE verified_markers(marker_id INT,playlist_id INT)")
                db.executemany("INSERT INTO verified_markers VALUES(?,?)",
                               [(1, 8), (2, 10), (3, 10)])
            before = (source.read_bytes(), store.read_bytes())
            result = report(source, store)
            self.assertEqual(result["separate_verified_knowledge"]["verified_marker_count"], 3)
            self.assertEqual(result["separate_verified_knowledge"]["by_analysis_source"],
                             {"4K_ANALYSE": 1, "THE_BEST": 2})
            self.assertEqual((source.read_bytes(), store.read_bytes()), before)
            self.assertTrue(result["handler_semantics_not_yet_proven"])

    def test_missing_file_and_duplicate_definition_block(self):
        with tempfile.TemporaryDirectory() as td:
            self.assertEqual(report(Path(td) / "none.py")["status"], "BLOCKED")
        two = SOURCE + '\ndef v082_skip_lookup(): pass\n'
        self.assertFalse(inspect_source(two)["v082_skip_lookup"]["present"])

if __name__ == "__main__":
    unittest.main()
