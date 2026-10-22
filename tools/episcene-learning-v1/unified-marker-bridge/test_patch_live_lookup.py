"""Synthetic exact-shape integration tests for guarded EpiScene Flask patch."""
import ast
import hashlib
import unittest

from patch_live_lookup import _function, patch_source, INJECTION_LABEL

FIXTURE = '''
def install_skip_routes(app):
    @app.post("/v1/device/skip/lookup")
    def v082_skip_lookup():
        raw = body()
        try:
            data = descriptor(raw)
        except (ValueError, TypeError):
            return jsonify(error="invalid"), 400
        with db() as con:
            row = device(con)
            if not rate(con, row, "lookup", 100):
                return jsonify(error="rate"), 429
            records = con.execute("SELECT * FROM skip_records").fetchall()
            identity = con.execute("SELECT * FROM skip_identities").fetchone()
            seen = set()
            segments = []
            for record in records:
                segments.append(dict(record))
            segments.sort(key=lambda i: (i["start_ms"], i["end_ms"]))
            return jsonify(asset_key=data["asset_key"],
                           source_key=data["source_key"],
                           duration_ms=data["duration_ms"],
                           segments=segments,
                           identity=dict(identity) if identity else {},
                           fingerprint_capture=False)
'''

class ControlledLookupPatchTests(unittest.TestCase):
    def _hash(self, code):
        return hashlib.sha256(ast.dump(
            _function(code), include_attributes=False).encode()).hexdigest()[:16]

    def test_inserted_only_at_existing_success_return(self):
        patched = patch_source(FIXTURE, expected_hash=self._hash(FIXTURE))
        compile(patched, "<synthetic patched lookup>", "exec")
        self.assertIn(INJECTION_LABEL, patched)
        self.assertEqual(patched.count(INJECTION_LABEL), 1)
        self.assertEqual(patched.count("device(con)"), 1)
        self.assertEqual(patched.count("rate(con, row"), 1)
        self.assertEqual(patched.count("segments=segments"), 1)
        self.assertLess(patched.index("rate(con, row"),
                        patched.index("segments = _epi_augment("))
        self.assertLess(patched.index("segments = _epi_augment("),
                        patched.index("fingerprint_capture=False"))
        self.assertIn("persisted_identity=(dict(identity) if identity is not None else None)", patched)

    def test_hash_mismatch_fails_closed(self):
        with self.assertRaisesRegex(ValueError, "differs from reviewed"):
            patch_source(FIXTURE, expected_hash="0000000000000000")

    def test_second_patch_refused(self):
        patched = patch_source(FIXTURE, expected_hash=self._hash(FIXTURE))
        with self.assertRaisesRegex(ValueError, "existing trusted external"):
            patch_source(patched, expected_hash=self._hash(FIXTURE))

    def test_unexpected_success_shape_fails_closed(self):
        modified = FIXTURE.replace("segments=segments,", "items=segments,")
        with self.assertRaisesRegex(ValueError, "exactly one successful"):
            patch_source(modified, expected_hash=self._hash(modified))

    def test_duplicate_live_route_refused(self):
        source = FIXTURE + FIXTURE.replace("install_skip_routes", "duplicate_skip_routes")
        with self.assertRaisesRegex(ValueError, "exactly one decorated"):
            patch_source(source, expected_hash=self._hash(FIXTURE))

if __name__ == "__main__":
    unittest.main()
