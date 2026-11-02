"""Synthetic privacy and dedup regression tests for the live read-only funnel."""
import json
import sqlite3
import unittest

import auto_release_funnel_readonly as report


def fixture():
    con = sqlite3.connect(":memory:")
    con.executescript("""
    CREATE TABLE skip_records(
      id INTEGER PRIMARY KEY,asset_key TEXT,status TEXT,source TEXT,
      segment_type TEXT,duration_ms INTEGER);
    CREATE TABLE skip_assets(asset_key TEXT PRIMARY KEY,playlist_id INTEGER);
    CREATE TABLE skip_auto_evidence(record_id INTEGER,evidence_json TEXT,
                                     human_review INTEGER);
    CREATE TABLE skip_auto_blocks(asset_key TEXT,kind TEXT,duration_ms INTEGER);
    CREATE TABLE skip_auto_settings(playlist_id INTEGER,enabled INTEGER);
    CREATE TABLE skip_analysis_sources(playlist_id INTEGER,enabled INTEGER);
    CREATE TABLE skip_release_settings(playlist_id INTEGER,enabled INTEGER);
    INSERT INTO skip_auto_settings VALUES(8,1),(10,1);
    INSERT INTO skip_analysis_sources VALUES(8,1),(10,1);
    INSERT INTO skip_release_settings VALUES(8,1),(10,1);
    INSERT INTO skip_assets VALUES('secret-provider-key-A',8);
    INSERT INTO skip_assets VALUES('secret-provider-key-B',8);
    INSERT INTO skip_assets VALUES('secret-provider-key-C',10);
    INSERT INTO skip_assets VALUES('secret-provider-key-D',10);
    INSERT INTO skip_assets VALUES('secret-provider-key-E',8);
    INSERT INTO skip_assets VALUES('secret-provider-key-F',10);
    INSERT INTO skip_records VALUES
      (1,'secret-provider-key-A','pending','episcene','intro',3500000),
      (2,'secret-provider-key-B','pending','episcene','outro',3500000),
      (3,'secret-provider-key-C','pending','audio','intro',3500000),
      (4,'secret-provider-key-D','pending','episcene','outro',3500000),
      (5,'secret-provider-key-E','approved','episcene','intro',3500000),
      (6,'secret-provider-key-F','pending','episcene','recap',3500000);
    """)
    def evidence(id, body, human=0):
        con.execute("INSERT INTO skip_auto_evidence VALUES(?,?,?)",
                    (id, json.dumps(body), human))
    evidence(1, {"episcene_required":True,
                 "decision":{"status":"AUTO_CONFIRMED"}})
    evidence(2, {"episcene_required":True,
                 "decision":{"status":"REVIEW"}})
    evidence(3, {"audio_visual_disagreement":True,
                 "decision":{"status":"AUTO_CONFIRMED"}})
    evidence(4, {"decision":{"status":"NO_MATCH"}})
    evidence(5, {"decision":{"status":"AUTO_CONFIRMED"}})
    evidence(6, {"decision":{"status":"AUTO_CONFIRMED"}}, human=1)
    con.execute("INSERT INTO skip_auto_blocks VALUES(?,?,?)",
                ("secret-provider-key-D","outro",3500000))
    con.commit()
    return con


class ReadOnlyFunnelTests(unittest.TestCase):
    def test_one_unique_record_even_with_duplicate_evidence_row(self):
        con=fixture()
        with con:
            evidence=con.execute(
                "SELECT evidence_json FROM skip_auto_evidence WHERE record_id=1"
            ).fetchone()[0]
            con.execute("INSERT INTO skip_auto_evidence VALUES(?,?,?)",
                        (1,evidence,0))
        data=report.analyze(con)["analysis_playlists"]
        self.assertEqual(data["8"]["unique_pending_machine_markers"],2)
        self.assertEqual(data["8"]["unique_pending_assets"],2)
        self.assertEqual(data["8"]["unique_visually_confirmed_pending_assets"],1)
        self.assertEqual(data["8"]["marker_blocker_categories"][
            "VISUALLY_CONFIRMED_BUT_STILL_PENDING"],1)

    def test_disagreement_explicit_blocks_and_manual_hold_take_precedence(self):
        con=fixture()
        data=report.analyze(con)["analysis_playlists"]["10"]
        self.assertEqual(data["marker_blocker_categories"][
            "AUDIO_VISUAL_DISAGREEMENT"],1)
        self.assertEqual(data["marker_blocker_categories"][
            "EXPLICIT_BLOCK"],1)
        self.assertEqual(data["marker_blocker_categories"][
            "AWAITING_HUMAN_REVIEW"],1)
        self.assertEqual(data["unique_visually_confirmed_pending_assets"],0)

    def test_conflicting_duplicate_evidence_never_counts_confirmed(self):
        con=fixture()
        con.execute("INSERT INTO skip_auto_evidence VALUES(?,?,?)",
                    (1,json.dumps({"decision":{"status":"NO_MATCH"}}),0))
        data=report.analyze(con)["analysis_playlists"]["8"]
        self.assertEqual(data["marker_blocker_categories"][
            "INCONSISTENT_EVIDENCE_ROWS"],1)
        self.assertEqual(data["unique_visually_confirmed_pending_assets"],0)

    def test_never_approves_a_record_or_leaks_identifiers(self):
        con=fixture()
        before=[tuple(x) for x in con.execute("SELECT id,status FROM skip_records ORDER BY id")]
        data=report.analyze(con)
        after=[tuple(x) for x in con.execute("SELECT id,status FROM skip_records ORDER BY id")]
        self.assertEqual(before,after)
        self.assertFalse(data["production_db_modified"])
        self.assertEqual(data["marker_approvals_triggered"],0)
        self.assertTrue(data["no_real_gate_simulated"])
        out=json.dumps(data)
        self.assertNotIn("secret-provider-key",out)
        self.assertNotIn("customer",out.replace("customer_identifiers_exported",""))

    def test_missing_release_settings_is_unknown_not_implicitly_enabled(self):
        con=fixture()
        con.execute("DROP TABLE skip_release_settings")
        data=report.analyze(con)["analysis_playlists"]["8"]
        self.assertIn("automatic_release:UNKNOWN",data["settings"])

    def test_fails_on_unknown_schema(self):
        con=fixture()
        con.execute("DROP TABLE skip_auto_blocks")
        with self.assertRaisesRegex(RuntimeError,"EXPECTED_SCHEMA_UNAVAILABLE"):
            report.analyze(con)


if __name__ == "__main__":
    unittest.main(verbosity=2)
