"""Synthetic redaction-only tests. No real credentials or live sources."""
import unittest
from inspect_lookup_redacted import build_review

SAMPLE = '''
@app.post("/v1/device/skip/lookup")
def v082_skip_lookup():
    """A private docstring with PASSWORD_NEVER_VISIBLE."""
    secret_token = "ghp_FAKE_PRIVATE_TOKEN_NEVER_VISIBLE"
    provider_url = "https://provider.example/private/username/password"
    sql = "SELECT token, password FROM customers WHERE id=72"
    count = 9123456789
    payload = request.get_json(silent=True) or {}
    key = payload.get("asset_key")
    if not verify_device(key, secret_token):
        return jsonify({"error": "PRIVATE_AUTH_ERROR"})
    return jsonify({"asset_key": key, "segments": [
        {"segment_type": "intro", "start_ms": 1000, "end_ms": 65000}
    ]})
def verify_device(asset, token):
    return asset == "REAL_SECRET_UID_DO_NOT_EXPOSE"
'''
class RedactionTests(unittest.TestCase):
    def test_strips_credential_literals_and_preserves_flow(self):
        out = build_review(SAMPLE)
        for private in ("PASSWORD_NEVER_VISIBLE", "ghp_FAKE_PRIVATE",
                        "provider.example", "customers WHERE", "9123456789",
                        "REAL_SECRET_UID", "PRIVATE_AUTH_ERROR"):
            self.assertNotIn(private, out)
        self.assertIn("def v082_skip_lookup()", out)
        self.assertIn("def verify_device(", out)
        self.assertIn("if not verify_device(", out)
        self.assertIn("segments", out)
        self.assertIn("start_ms", out)
        self.assertIn("REDACTED_STRING", out)

    def test_no_active_function_fails(self):
        with self.assertRaises(ValueError):
            build_review("def unrelated(): pass")

    def test_simple_function_still_emits_review(self):
        out = build_review("def v082_skip_lookup():\\n    return {'segments': []}\\n".replace(
            "\\n", "\n"))
        self.assertIn("segments", out)
        self.assertIn("END REDACTED CONTROL FLOW", out)

if __name__ == "__main__":
    unittest.main()
