"""Synthetic read-only release gate verification; no IPTV or real customer data."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from check_lookup_release_gate import inspect_lookup, inspect_overlap, report

ACTIVE = '''
@app.post("/v1/device/skip/lookup")
def v082_skip_lookup():
    password = "FAKE_SECRET_MUST_NOT_PRINT"
    payload = request.get_json()
    return jsonify({"markers": [], "status": "ok"})
'''
DUPLICATE = ACTIVE + '\ndef v082_skip_lookup(): return None\n'

class GateTests(unittest.TestCase):
    def test_safe_handler_response_key_introspection(self):
        checked = inspect_lookup(ACTIVE)
        self.assertTrue(checked["single_active_handler"])
        self.assertTrue(checked["expected_lookup_route_present"])
        self.assertTrue(any("markers" in x["visible_response_keys"]
                            for x in checked["return_shapes"]))
        self.assertFalse(checked["authorization_verified"])
        self.assertNotIn("FAKE_SECRET", json.dumps(checked))
        self.assertFalse(inspect_lookup(DUPLICATE)["single_active_handler"])

    def test_marker_overlap_distinguishes_approved_from_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod = root / "provisioning.sqlite3"
            unified = root / "unified.sqlite3"
            with sqlite3.connect(prod) as db:
                db.execute("""CREATE TABLE skip_records(
                    id INT,asset_key TEXT,segment_type TEXT,start_ms INT,
                    end_ms INT,status TEXT)""")
                db.executemany("INSERT INTO skip_records VALUES(?,?,?,?,?,?)",[
                    (1,"source-8","intro",1000,2000,"approved"),
                    (2,"source-10","recap",0,1000,"pending"),
                    (3,"different","outro",3000,4000,"approved")])
            with sqlite3.connect(unified) as db:
                db.execute("""CREATE TABLE verified_markers(
                    marker_id INT, asset_key TEXT,playlist_id INT,kind TEXT,
                    start_ms INT,end_ms INT)""")
                db.executemany("INSERT INTO verified_markers VALUES(?,?,?,?,?,?)",[
                    (1,"source-8",8,"intro",1000,2000),
                    (2,"source-10",10,"recap",0,1000),
                    (3,"source-8",8,"outro",3000,4000),
                    (4,"source-10",10,"intro",3000,4000)])
            before=(prod.read_bytes(),unified.read_bytes())
            result=inspect_overlap(prod,unified)
            self.assertEqual(result["unified_total"],4)
            self.assertEqual(result["already_identical_and_approved_in_original"],1)
            self.assertEqual(result["identical_but_not_approved_in_original"],1)
            self.assertEqual(result["different_identity_or_time_bounds"],1)
            self.assertEqual(result["not_in_original_records_by_id"],1)
            self.assertEqual(before,(prod.read_bytes(),unified.read_bytes()))
            source=root / "skip_markers.py"
            source.write_text(ACTIVE)
            emitted=json.dumps(report(source,prod,unified))
            self.assertNotIn("FAKE_SECRET_MUST_NOT_PRINT",emitted)
            self.assertIn("INSPECTED_READ_ONLY",emitted)

    def test_missing_files_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            self.assertEqual(report(root/"missing.py",root/"prod",root/"kb")
                             ["status"],"STOP_SOURCE_UNAVAILABLE")

if __name__=="__main__":
    unittest.main()
