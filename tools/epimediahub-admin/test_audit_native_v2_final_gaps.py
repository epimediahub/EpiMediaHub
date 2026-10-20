"""Offline fixture tests for the narrow final native Admin contract audit."""
from pathlib import Path
import tempfile
import unittest
import audit_native_v2_final_gaps as target


class AuditFinalGapsTests(unittest.TestCase):
    def test_form_field_names_and_finite_enum_only(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "dashboard_v070.py"
            p.write_text("""
def _playlist_config():
    pw = request.form.get("password", "dont-expose-default-secret")
    url = request.form["playlist_url"]
    stream_type = request.form.get("mode", "xtream")
    conn.execute("SELECT * FROM sensitive_table WHERE token='private'")
    if stream_type == "xtream":
        return {"uri": url, "password": pw}
    return {"uri": url}
""", encoding="utf-8")
            found, roles = target.inspect(p)
        self.assertEqual(roles, [])
        self.assertEqual(len(found), 1)
        entry = found[0]
        self.assertEqual(entry["function"], "_playlist_config")
        self.assertEqual(entry["field_name_only"],
                         ["mode", "password", "playlist_url"])
        display = entry["redacted_structure"]
        self.assertIn("playlist_url", display)
        self.assertIn("xtream", display)
        self.assertNotIn("dont-expose-default-secret", display)
        self.assertNotIn("private", display)
        self.assertNotIn("SELECT *", display)

    def test_skip_review_and_safe_intro_roles(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "skip_markers.py"
            p.write_text("""
def csrf():
    return request.form.get("_csrf_token", "sensitive-csrf-secret")

def v082_skip_review(record_id):
    decision = request.form.get("decision", "approve")
    if decision not in ("approve", "reject"):
        raise ValueError("PRIVATE_SECRET")
    return record_id
""", encoding="utf-8")
            found, _ = target.inspect(p)
            self.assertEqual({f["function"] for f in found},
                             {"csrf", "v082_skip_review"})
            self.assertIn("_csrf_token",
                          found[0]["field_name_only"])
            self.assertNotIn("PRIVATE_SECRET",
                             found[1]["redacted_structure"])
            p = Path(temp) / "skip_intro_sections.py"
            p.write_text('INTRO_ROLES={"intro":"x","outro":"y", "not a role!":"z"}\n',
                         encoding="utf-8")
            found, roles = target.inspect(p)
            self.assertEqual(found, [])
            self.assertEqual(roles, ["intro", "outro"])


    def test_nested_registered_handlers_are_found_without_exposing_confirm_string(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "dashboard_v080.py"
            p.write_text("""
def install(app):
    def nested_other():
        return "private-secret-password"

    @app.post("/admin/resellers/9/delete")
    def v080_delete_reseller(reseller_id):
        if request.form.get("confirm") != f"DELETE {reseller_id}":
            abort(400)
        db().execute("DELETE FROM resellers WHERE password='SECRET'")
        return redirect("/")
""", encoding="utf-8")
            found, roles = target.inspect(p)
        self.assertEqual(roles, [])
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["function"], "v080_delete_reseller")
        self.assertEqual(found[0]["field_name_only"], ["confirm"])
        flow = found[0]["redacted_structure"]
        self.assertIn("request.form.get('confirm')", flow)
        self.assertIn("<redacted-format>", flow)
        self.assertNotIn("private-secret-password", flow)
        self.assertNotIn("DELETE FROM resellers", flow)
        self.assertNotIn("admin/resellers/9/delete", flow)


if __name__ == "__main__":
    unittest.main()
