"""Trusted external resolver tests; every provider response and DB is synthetic."""
import tempfile
import unittest
from pathlib import Path

from bridge import import_authenticated_feedback
from test_bridge import databases, episode
from trusted_external import (_identity_ok, _get_candidates, _promote,
                              resolve_external, trusted_playback_resolution)

def fake_fetch(url):
    if "introdb.app" in url:
        return {"status": "ok", "data": {
            "imdb_id": "tt0903747", "season": 1, "episode": 1,
            "intro": {"start_ms": 11000, "end_ms": 62000, "confidence": .98},
            "recap": {"start_ms": 1000, "end_ms": 9000},
            "outro": None}}
    return {"status": "ok", "data": {
        "kind": "media", "tvdb_id": 81189, "season": 1, "episode": 1,
        "group_duration_ms": 2700000,
        "intro": [{"start_ms": 11500, "end_ms": 61000}],
        "credits": [{"start_ms": 2500000, "end_ms": None}]}}

class TrustedSourcesTests(unittest.TestCase):
    def test_both_sources_promoted_without_manual_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            x = resolve_external(episode(), Path(tmp) / "trusted.sqlite3",
                                 fetch=fake_fetch, now=100)
            self.assertEqual(x["conflicts"], [])
            self.assertEqual({m["segment_type"] for m in x["trusted_segments"]},
                             {"intro", "recap", "outro"})
            self.assertTrue(all(m["trusted"] for m in x["trusted_segments"]))
            self.assertTrue(all(m["auto_seek"] is False for m in x["trusted_segments"]))
            self.assertEqual(x["sources"]["introdb"], "ok")
            self.assertEqual(x["sources"]["theintrodb"], "ok")

    def test_conflicting_sources_not_auto_promoted(self):
        def conflict(url):
            if "introdb.app" in url:
                return {"status": "ok", "data": {
                    "intro": {"start_ms": 10000, "end_ms": 55000}}}
            return {"status": "ok", "data": {
                "kind": "media", "intro": [{"start_ms": 80000, "end_ms": 110000}]}}
        with tempfile.TemporaryDirectory() as tmp:
            v = resolve_external(episode(), Path(tmp) / "trusted.sqlite3",
                                 fetch=conflict, now=100)
            self.assertEqual(v["trusted_segments"], [])
            self.assertEqual(v["conflicts"], ["intro"])

    def test_negative_introdb_prevents_theintrodb_auto_skip(self):
        def negatives(url):
            return ({"status": "ok", "data": {"no_intro": True}}
                    if "introdb.app" in url else
                    {"status": "ok", "data":
                     {"intro": [{"start_ms": 2000, "end_ms": 65000}]}})
        with tempfile.TemporaryDirectory() as tmp:
            v = resolve_external(episode(), Path(tmp) / "trust.sqlite3",
                                 fetch=negatives, now=100)
            self.assertIn("intro", v["conflicts"])
            self.assertEqual(v["trusted_segments"], [])

    def test_episode_identity_and_cut_mismatch_rejected(self):
        self.assertFalse(_identity_ok({"season": 2}, episode(), "introdb"))
        self.assertFalse(_identity_ok({"imdb_id": "tt0000001"}, episode(), "introdb"))
        self.assertFalse(_identity_ok({"group_duration_ms": 2800000},
                                      episode(), "theintrodb"))
        def bad(url):
            return ({"status": "ok", "data": {
                "imdb_id": "tt0000001",
                "intro": {"start_ms": 10000, "end_ms": 60000}}}
                if "introdb.app" in url else
                {"status": "ok", "data": {
                    "group_duration_ms": 2800000, "kind": "media",
                    "credits": [{"start_ms": 2500000, "end_ms": None}]}})
        with tempfile.TemporaryDirectory() as tmp:
            x = resolve_external(episode(), Path(tmp) / "trusted.sqlite3",
                                 fetch=bad)
            self.assertEqual(x["trusted_segments"], [])
            self.assertEqual(x["sources"]["introdb"], "identity_or_cut_mismatch")
            self.assertEqual(x["sources"]["theintrodb"], "identity_or_cut_mismatch")

    def test_cached_by_episode_cut_not_playlist(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            def fetch(url):
                calls.append(url)
                return fake_fetch(url)
            cache = Path(tmp) / "trusted.sqlite3"
            resolve_external(episode(playlist_id=8), cache, fetch=fetch, now=100)
            reused = resolve_external(episode(playlist_id=10), cache,
                                      fetch=lambda _: self.fail("Must cache"), now=101)
            self.assertTrue(reused["cached"])
            self.assertEqual(len(calls), 2)
            diff = resolve_external(episode(duration_ms=2600000), cache,
                                    fetch=fetch, now=101)
            self.assertFalse(diff["cached"])
            self.assertEqual(len(calls), 4)

    def test_failure_preserves_cached_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "cache.sqlite3"
            a = resolve_external(episode(), path, fetch=fake_fetch, now=100)
            result = resolve_external(
                episode(), path, fetch=lambda _:
                {"status": "network_error", "data": None}, now=100000)
            self.assertTrue(result["source_refresh_failed"])
            self.assertTrue(result["cached"])
            self.assertEqual(result["trusted_segments"], a["trusted_segments"])

    def test_server_authorization_metadata_and_local_precedence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prod, feedback, knowledge = databases(root)
            import_authenticated_feedback(feedback, prod, knowledge)
            canonical = episode().__dict__
            trusted = lambda _pid, _asset: canonical
            incoming = {"playlist_id": 8, "asset_key": "source-8-ep1",
                        "imdb_id": "tt0000001", "season": 99}
            with self.assertRaises(PermissionError):
                trusted_playback_resolution(incoming,
                    authorize=lambda _p, _a: False,
                    trusted_identity=trusted, store=knowledge,
                    cache=root / "external.sqlite3", fetch=fake_fetch)
            output = trusted_playback_resolution(
                incoming, authorize=lambda p,a: p==8 and a=="source-8-ep1",
                trusted_identity=trusted, store=knowledge,
                cache=root/"external.sqlite3", fetch=fake_fetch)
            self.assertEqual(output["asset_key"], "source-8-ep1")
            self.assertEqual(sum(x["segment_type"]=="intro" for x in output["segments"]), 1)
            self.assertEqual(next(x for x in output["segments"]
                                  if x["segment_type"]=="intro")["source"],
                             "authenticated_feedback")
            self.assertFalse(output["automatic_skip_disabled"] is False)
            self.assertEqual({x["segment_type"] for x in output["segments"]},
                             {"intro", "recap", "outro"})

    def test_no_metadata_no_external_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            e = episode(imdb_id="", tvdb_id=0)
            r = resolve_external(e, Path(tmp)/"source.sqlite3",
                                 fetch=lambda _:
                                 self.fail("No identity must not call API"))
            self.assertEqual(r["trusted_segments"], [])
            self.assertFalse((Path(tmp)/"source.sqlite3").exists())

if __name__ == "__main__":
    unittest.main()
