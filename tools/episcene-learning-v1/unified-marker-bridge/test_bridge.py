"""Isolated EpiScene unified bridge tests; no server, customer streams or network."""
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from bridge import (Episode, evaluate, import_authenticated_feedback, parse_introdb,
                    parse_theintrodb, remote_candidates, windows)

CUT = "a" * 64
OTHER_CUT = "b" * 64

def episode(**kwargs):
    data = dict(playlist_id=8, asset_key="source-8-ep1", season=1, episode=1,
                duration_ms=2700000, imdb_id="tt0903747", tvdb_id=81189,
                fingerprint=CUT, title="Example")
    data.update(kwargs)
    return Episode.from_dict(data)

def databases(root):
    production = root / "production.sqlite3"
    feedback = root / "feedback.sqlite3"
    knowledge = root / "unified.sqlite3"
    with sqlite3.connect(production) as c:
        c.execute("""CREATE TABLE skip_assets(asset_key TEXT, playlist_id INT,
            title TEXT, season INT, episode INT, duration_ms INT,
            content_fingerprint TEXT)""")
        c.executemany("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)", [
            ("source-8-ep1", 8, "Example", 1, 1, 2700000, CUT),
            ("source-10-ep1", 10, "Example", 1, 1, 2700000, CUT),
            ("source-10-ep2", 10, "Example", 1, 2, 2660000, OTHER_CUT)])
    with sqlite3.connect(feedback) as c:
        c.execute("""CREATE TABLE feedback_versions(marker_id INT,asset_key TEXT,
            playlist_id INT,season INT,episode INT,kind TEXT,decision TEXT,
            active INT,start_ms INT,end_ms INT,provenance TEXT,reviewed_at TEXT)""")
        c.executemany("INSERT INTO feedback_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", [
            (5, "source-8-ep1", 8, 1, 1, "intro", "positive", 1, 10000, 60000,
             "device_authenticated_direct", "2026-10-21T00:00:00Z"),
            (6, "source-10-ep1", 10, 1, 1, "recap", "positive", 1, 0, 40000,
             "admin_reviewed_machine", "2026-10-21T00:00:00Z"),
            (7, "source-10-ep2", 10, 1, 2, "intro", "negative", 1, 10000, 60000,
             "device_authenticated_direct", "2026-10-21T00:00:00Z"),
            (8, "source-8-ep1", 8, 1, 1, "outro", "positive", 0, 2570000, 2690000,
             "device_authenticated_direct", "2026-10-21T00:00:00Z"),
            (9, "source-8-ep1", 8, 1, 1, "outro", "positive", 1, 2570000, 2690000,
             "unverified_source_status", "2026-10-21T00:00:00Z")])
    return production, feedback, knowledge

class EpisodeTests(unittest.TestCase):
    def test_proposed_search_windows_are_not_hard_limits(self):
        self.assertEqual(windows(2400000), {
            "recap": [0, 180000], "intro": [0, 600000], "outro": [2100000, 2400000]})
        self.assertEqual(windows(90000)["outro"], [0, 90000])

    def test_invalid_fingerprints_and_media_ids(self):
        with self.assertRaises(ValueError):
            episode(fingerprint="not-a-sha256")
        with self.assertRaises(ValueError):
            episode(imdb_id="ttbad")
        with self.assertRaises(ValueError):
            episode(duration_ms=-1)

    def test_introdb_uses_milliseconds_and_negative_markers(self):
        e = episode()
        got = parse_introdb({"intro": {"start_ms": 10500, "end_ms": 62000,
                                      "confidence": 0.92},
                             "recap": {"start_ms": 0, "end_ms": 25000},
                             "no_recap": True}, e)
        self.assertEqual(len(got), 1)
        self.assertEqual((got[0]["start_ms"], got[0]["end_ms"]), (10500, 62000))

    def test_theintrodb_v4_null_bounds_and_multiple_segments(self):
        e = episode()
        got = parse_theintrodb({
            "kind": "media", "intro": [{"start_ms": None, "end_ms": 78000}],
            "credits": [{"start_ms": 2590000, "end_ms": None}],
            "recap": [{"start_ms": 1000, "end_ms": 25000},
                      {"start_ms": 40000, "end_ms": 65000}]}, e)
        self.assertEqual(len(got), 4)
        self.assertEqual(got[0]["start_ms"], 1000)
        self.assertEqual(got[-1]["end_ms"], 2700000)
        self.assertEqual(parse_theintrodb({"kind": "versions"}, e), [])

    def test_dual_public_sources_are_only_advice(self):
        e = episode(playlist_id=10, asset_key="source-10-ep1")
        called = []
        def fetch(url):
            called.append(url)
            if "introdb.app" in url:
                return {"status": "ok", "data": {
                    "intro": {"start_ms": 10000, "end_ms": 60000, "confidence": .9}}}
            return {"status": "ok", "data": {
                "kind": "media", "credits": [{"start_ms": 2600000, "end_ms": None}]}}
        report = evaluate(e, external=True, fetch=fetch)
        self.assertEqual(len(called), 2)
        self.assertIn("/v4/media?", called[1])
        self.assertEqual(report["ready_verified"], [])
        self.assertEqual(len(report["review_candidates"]), 2)
        self.assertTrue(all(c["status"] == "needs_cut_verification"
                            for c in report["review_candidates"]))

    def test_no_external_id_has_no_requests(self):
        called = []
        def fetch(url):
            called.append(url)
            raise AssertionError("Should not call API")
        got, statuses = remote_candidates(episode(imdb_id="", tvdb_id=0), fetch)
        self.assertEqual(got, [])
        self.assertEqual(called, [])
        self.assertEqual(statuses["introdb"], "no_imdb_identity")

class KnowledgeTests(unittest.TestCase):
    def test_verified_truth_from_both_playlists_and_cut_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, f, k = databases(Path(tmp))
            before_p, before_f = p.read_bytes(), f.read_bytes()
            synced = import_authenticated_feedback(f, p, k)
            self.assertEqual(synced["imported_authenticated_markers"], 2)
            self.assertEqual(p.read_bytes(), before_p)
            self.assertEqual(f.read_bytes(), before_f)
            response = evaluate(episode(playlist_id=10, asset_key="future-provider"), k,
                                external=False)
            self.assertEqual({x["kind"] for x in response["ready_verified"]},
                             {"intro", "recap"})
            self.assertTrue(all(x["match"] == "same_cut" for x in
                                response["ready_verified"]))
            mismatch = evaluate(episode(playlist_id=10, asset_key="future-provider",
                                        fingerprint=OTHER_CUT), k, external=False)
            self.assertEqual(mismatch["ready_verified"], [])
            own = evaluate(episode(fingerprint=""), k, external=False)
            self.assertEqual([x["kind"] for x in own["ready_verified"]], ["intro"])

    def test_revoked_feedback_is_removed_on_sync(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, f, k = databases(Path(tmp))
            import_authenticated_feedback(f, p, k)
            with sqlite3.connect(f) as c:
                c.execute("UPDATE feedback_versions SET active=0 WHERE marker_id=5")
            import_authenticated_feedback(f, p, k)
            response = evaluate(episode(), k, external=False)
            self.assertEqual({r["kind"] for r in response["ready_verified"]}, {"recap"})

    def test_conflicts_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, f, k = databases(Path(tmp))
            with sqlite3.connect(f) as c:
                c.execute("""INSERT INTO feedback_versions VALUES (
                    19,'source-10-ep1',10,1,1,'intro','positive',1,22000,68000,
                    'admin_reviewed_machine','2026-10-21T00:00:00Z')""")
            import_authenticated_feedback(f, p, k)
            response = evaluate(episode(), k, external=False)
            self.assertIn("intro", response["conflicts"])
            self.assertNotIn("intro", [r["kind"] for r in response["ready_verified"]])

    def test_authenticated_customer_playlist_marker_imports_without_unsafe_reuse(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, f, k = databases(Path(tmp))
            with sqlite3.connect(p) as con:
                con.execute("INSERT INTO skip_assets VALUES(?,?,?,?,?,?,?)",
                            ("source-55-s4e1", 55, "The Lincoln Lawyer", 4, 1,
                             3000000, OTHER_CUT))
            with sqlite3.connect(f) as con:
                con.executemany("INSERT INTO feedback_versions VALUES(?,?,?,?,?,?,?,?,?,?,?,?)", [
                    (91, "source-55-s4e1", 55, 4, 1, "intro", "positive", 1,
                     9000, 57000, "device_authenticated_direct", "2026-10-23T18:00:00Z"),
                    (92, "source-55-s4e1", 55, 4, 1, "outro", "positive", 1,
                     2860000, 2990000, "unverified_source_status", "2026-10-23T18:00:00Z"),
                ])
            unchanged_p, unchanged_f = p.read_bytes(), f.read_bytes()
            result = import_authenticated_feedback(f, p, k)
            self.assertEqual(result["imported_authenticated_markers"], 3)
            self.assertEqual(result["from_playlists"], [8, 10, 55])
            self.assertEqual(p.read_bytes(), unchanged_p)
            self.assertEqual(f.read_bytes(), unchanged_f)

            own = evaluate(episode(
                playlist_id=55, asset_key="source-55-s4e1", season=4, episode=1,
                duration_ms=3000000, fingerprint="", title="The Lincoln Lawyer"), k,
                external=False)
            self.assertEqual([r["kind"] for r in own["ready_verified"]], ["intro"])
            self.assertEqual(own["ready_verified"][0]["match"], "same_asset")

            wrong_cut = evaluate(episode(
                playlist_id=8, asset_key="other-provider-s4e1", season=4, episode=1,
                duration_ms=3000000, fingerprint=CUT, title="The Lincoln Lawyer"), k,
                external=False)
            self.assertEqual(wrong_cut["ready_verified"], [])
            verified_cut = evaluate(episode(
                playlist_id=8, asset_key="other-provider-s4e1", season=4, episode=1,
                duration_ms=3000000, fingerprint=OTHER_CUT, title="The Lincoln Lawyer"),
                k, external=False)
            self.assertEqual([r["kind"] for r in verified_cut["ready_verified"]], ["intro"])
            self.assertEqual(verified_cut["ready_verified"][0]["match"], "same_cut")


if __name__ == "__main__":
    unittest.main()
