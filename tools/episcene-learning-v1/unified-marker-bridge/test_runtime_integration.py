"""Backend interface tests; no network, IPTV streams or real customer database."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from bridge import import_authenticated_feedback
from runtime_integration import (external_review_resolution, playback_resolution,
                                 planning_hints)
from test_bridge import databases, episode

class RuntimeIntegrationTests(unittest.TestCase):
    def test_existing_service_auth_required(self):
        with tempfile.TemporaryDirectory() as tmp:
            p, f, store = databases(Path(tmp))
            import_authenticated_feedback(f, p, store)
            ep = episode().__dict__
            with self.assertRaises(PermissionError):
                playback_resolution(ep, authorize=lambda _p, _a: False, store=store)
            result = playback_resolution(ep, authorize=lambda p, a:
                                         p == 8 and a == "source-8-ep1", store=store)
            self.assertEqual(result["schema"], "episcene_verified_skip_v1")
            self.assertEqual([x["type"] for x in result["markers"]], ["intro"])
            self.assertEqual(result["markers"][0]["end_ms"], 60000)

    def test_unverified_source_never_shown_to_player(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp) / "markers.sqlite3"
            with sqlite3.connect(store) as conn:
                conn.execute("""CREATE TABLE verified_markers(marker_id INT, asset_key TEXT,
                  playlist_id INT, title TEXT, season INT, episode INT, kind TEXT,
                  start_ms INT,end_ms INT,duration_ms INT,fingerprint TEXT,
                  provenance TEXT,reviewed_at TEXT)""")
                conn.execute("""INSERT INTO verified_markers VALUES
                    (1,'asset',8,'show',1,1,'intro',1000,2000,30000,'',
                     'device_authenticated_direct','2026-10-21')""")
            raw = {"playlist_id": 8, "asset_key": "different", "season": 1,
                   "episode": 1, "duration_ms": 30000}
            result = playback_resolution(raw, store=store, authorize=lambda *_: True)
            self.assertEqual(result["markers"], [])

    def test_external_candidates_use_cache_and_are_only_hints(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "advisory.sqlite3"
            called = []
            def fetch(url):
                called.append(url)
                if "introdb.app" in url:
                    return {"status": "ok", "data": {
                        "intro": {"start_ms": 11000, "end_ms": 59000, "confidence": .9}}}
                return {"status": "not_found", "data": None}
            ep = episode().__dict__
            first = external_review_resolution(ep, cache=cache, fetch=fetch, now=100)
            again = external_review_resolution(ep, cache=cache, fetch=fetch, now=101)
            self.assertEqual(len(called), 2)  # 2 external sources, 1 lookup each
            self.assertFalse(first["published"])
            self.assertEqual(first["review_candidates"][0]["status"],
                             "needs_cut_verification")
            self.assertTrue(again["cached"])
            self.assertEqual(len(again["review_candidates"]), 1)
            self.assertEqual(len(called), 2)

    def test_no_customer_analysis_or_external_lookup(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(PermissionError):
                external_review_resolution(
                    episode(playlist_id=44).__dict__, cache=Path(tmp) / "advisory.sqlite3",
                    fetch=lambda _: self.fail("No outgoing network"))
            self.assertFalse((Path(tmp) / "advisory.sqlite3").exists())

    def test_failure_ttl_and_expired_cache_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "advisory.sqlite3"
            called = []
            def fetch(url):
                called.append(url)
                return {"status": "network_error", "data": None}
            ep = episode().__dict__
            external_review_resolution(ep, cache=cache, fetch=fetch, now=100)
            external_review_resolution(ep, cache=cache, fetch=fetch, now=999)
            self.assertEqual(len(called), 2)
            external_review_resolution(ep, cache=cache, fetch=fetch, now=1000)
            self.assertEqual(len(called), 4)

    def test_no_second_same_provider_job(self):
        data = [episode(playlist_id=8, asset_key="first").__dict__,
                episode(playlist_id=8, asset_key="second").__dict__,
                episode(playlist_id=10, asset_key="italian").__dict__,
                episode(playlist_id=44, asset_key="customer").__dict__]
        jobs = planning_hints(data)
        self.assertEqual([(j["playlist_id"],j["asset_key"]) for j in jobs],
                         [(8, "first"), (10, "italian")])
        self.assertTrue(all(j["external_lookup_only"] and
                            j["stream_slots_reserved"] == 0 for j in jobs))
        with self.assertRaises(ValueError):
            planning_hints(data, max_per_playlist=2)

class TrustedCacheACLTests(unittest.TestCase):
    def test_exact_readonly_acl_allowed_without_relaxing_others(self):
        import struct
        from types import SimpleNamespace
        from unittest.mock import patch
        from runtime_integration import _cache_path

        api_uid = 123456
        def acl(owner_perm, reader_perm, *, extra=False, mask=None):
            entries = [(1, owner_perm, 0xffffffff),
                       (2, reader_perm, api_uid),
                       (4, 0, 0xffffffff),
                       (16, reader_perm if mask is None else mask, 0xffffffff),
                       (32, 0, 0xffffffff)]
            if extra:
                entries.insert(3, (8, 4, 12345))
            return struct.pack("<I", 2) + b"".join(
                struct.pack("<HHI", *entry) for entry in entries)

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            path = folder / "trusted-sources.sqlite3"
            path.touch()
            folder.chmod(0o710)
            path.chmod(0o640)
            def xattr(target, _key):
                return acl(7, 1) if Path(target) == folder else acl(6, 4)
            with (patch("runtime_integration.TRUSTED_SOURCE_CACHE", path),
                  patch("pwd.getpwnam", return_value=SimpleNamespace(pw_uid=api_uid)),
                  patch("runtime_integration.os.getxattr", side_effect=xattr)):
                self.assertEqual(_cache_path(path), path)
            def bad_acl(target, _key):
                return acl(7, 1) if Path(target) == folder else acl(6, 4, extra=True)
            with (patch("runtime_integration.TRUSTED_SOURCE_CACHE", path),
                  patch("pwd.getpwnam", return_value=SimpleNamespace(pw_uid=api_uid)),
                  patch("runtime_integration.os.getxattr", side_effect=bad_acl)):
                with self.assertRaises(ValueError):
                    _cache_path(path)
            other = folder / "different.sqlite3"
            other.touch()
            other.chmod(0o640)
            with self.assertRaises(ValueError):
                _cache_path(other)

if __name__ == "__main__":
    unittest.main()
