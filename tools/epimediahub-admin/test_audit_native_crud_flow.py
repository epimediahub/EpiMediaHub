"""One audit invocation, no literal values, no production imports."""
from pathlib import Path
import tempfile
import unittest
from audit_native_crud_flow import _scan

class NativeCrudAuditTests(unittest.TestCase):
    def test_masked_credentials_and_safe_form_field_names(self):
        code='''
@app.post("/admin/v076/playlists/<int:playlist_id>/update")
def v076_update_customer_playlist(playlist_id):
    # NEVER_EXPORT_COMMENT_SECRET
    token="PRIVATE_ACCESS_TOKEN"
    name=request.form.get("name")
    url=request.form.get("m3u_url")
    password=request.form["password"]
    con.execute("UPDATE playlists SET config_json='SECRET_URL'")
    return redirect("/admin")
'''
        with tempfile.TemporaryDirectory() as folder:
            source=Path(folder)/"dashboard_v070.py"
            source.write_text(code,encoding="utf-8")
            entries=_scan(source,{"v076_update_customer_playlist"})
        self.assertEqual(len(entries),1)
        item=entries[0]
        self.assertEqual(item["form_field_names"],["m3u_url","name","password"])
        blob=str(item)
        for secret in ("PRIVATE_ACCESS_TOKEN","SECRET_URL",
                       "NEVER_EXPORT_COMMENT_SECRET","/admin"):
            self.assertNotIn(secret,blob)
        self.assertIn("<redacted-value>",blob)

if __name__=="__main__":
    unittest.main()
