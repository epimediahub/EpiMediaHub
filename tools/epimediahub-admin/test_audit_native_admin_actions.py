"""Confirm read-only action inventory never exports source or secret values."""
import unittest
from audit_native_admin_actions import analyze

class ActionAuditTests(unittest.TestCase):
    def test_only_field_names_and_calls(self):
        src = '''
@app.post("/admin/devices/<int:row_id>/grant-year")
def admin_grant_year(row_id):
    credential="SUPER_SENSITIVE_REAL_SECRET_EXAMPLE"
    password=request.form.get("password")
    nonce=request.form.get("request_id")
    if not _require_admin():
        return "NOT_AUTHORIZED"
    grant_license(row_id)
    return "PRIVATE_SUCCESS"
'''
        output=analyze(src,{"admin_grant_year"})
        self.assertEqual(len(output),1)
        blob=str(output)
        self.assertNotIn("SUPER_SENSITIVE_REAL_SECRET_EXAMPLE",blob)
        self.assertNotIn("PRIVATE_SUCCESS",blob)
        self.assertNotIn("NOT_AUTHORIZED",blob)
        self.assertNotIn("password",blob.lower())
        self.assertIn("[SENSITIVE_FIELD]",blob)
        self.assertIn("request_id",blob)
        self.assertIn("grant_license",blob)

    def test_not_selected_functions_omitted(self):
        self.assertEqual(analyze("def unrelated():\n    return 'SECRET'\n",{"login"}),[])

if __name__ == "__main__":
    unittest.main()
