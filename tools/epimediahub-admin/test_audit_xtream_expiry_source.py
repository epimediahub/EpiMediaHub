"""Read-only audit validates that secrets and account-derived keys stay private."""
from pathlib import Path
import sqlite3
import tempfile
import unittest
import json
from audit_xtream_expiry_source import inspect_database,source_refs


class SourceAuditTests(unittest.TestCase):
    def test_only_aggregate_counts_and_known_safe_key_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"test.sqlite3"
            with sqlite3.connect(db) as con:
                con.execute("CREATE TABLE customer_playlists(id INTEGER PRIMARY KEY,enabled INTEGER,config_json TEXT)")
                con.execute("INSERT INTO customer_playlists VALUES(1,1,?)",(
                    json.dumps({"type":"XTREAM","name":"SECRET_CLIENT",
                        "xtream_username":"PRIVATE_USER","xtream_password":"SECRET_123",
                        "PRIVATE_ACCOUNT_KEY":"secret_value","exp_date":"1793000000"}),))
                con.execute("INSERT INTO customer_playlists VALUES(2,1,?)",(
                    json.dumps({"type":"M3U","url":"https://sensitive.example/list",
                        "password":"PRIVATE_PASS","PRIVATE_DYNAMIC_KEY":"no"}),))
            result=inspect_database(db)
            self.assertEqual(result["active_playlist_type_counts"],{"M3U":1,"XTREAM":1})
            self.assertEqual(result["total_active_playlists"],2)
            self.assertEqual(result["expiry_value_presence_counts"]["XTREAM"]["exp_date"],1)
            rendered=json.dumps(result)
            for blocked in ("SECRET_CLIENT","PRIVATE_USER","PRIVATE_PASS","SECRET_123",
                            "PRIVATE_ACCOUNT_KEY","PRIVATE_DYNAMIC_KEY",
                            "sensitive.example"):
                self.assertNotIn(blocked,rendered)

    def test_ast_returns_function_names_not_provider_url_or_literal(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"worker.py"
            p.write_text("""
def refresh_provider():
    api = "https://SECRET-host.example/player_api.php"
    key = "PRIVATE_PROVIDER_KEY"
    return {"user_info": {"exp_date": 1793000000}}
""")
            rows=source_refs(Path(tmp))
            self.assertEqual(rows,[{"module":"worker.py","functions":["refresh_provider"]}])
            self.assertNotIn("SECRET",json.dumps(rows))


if __name__=="__main__":
    unittest.main()
