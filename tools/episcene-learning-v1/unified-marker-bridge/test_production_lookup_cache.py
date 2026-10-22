"""Synthetic tests for the existing authenticated EpiScene device lookup bridge."""
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from production_lookup_cache import augment_authorized_segments

DESC = {
    "media_type": "episode", "asset_key": "provider-episode-1",
    "source_key": "source123", "season": 1, "episode": 1,
    "duration_ms": 2700000, "imdb_id": "CLIENT_UNTRUSTED",
}
IDENTITY = {"source_key": "source123", "imdb_id": "tt0903747",
            "tmdb_id": 1396}
SEGMENTS = [
    {"segment_type": "intro", "start_ms": 12000, "end_ms": 60000,
     "source": "introdb", "trusted": True},
    {"segment_type": "outro", "start_ms": 2600000, "end_ms": 2700000,
     "source": "theintrodb", "trusted": True},
]

def make_cache(path, segments=None, *, duration=2700000, imdb="tt0903747",
               tmdb=1396, season=1, episode=1, expires=None, conflicts=None):
    expires = int(time.time()) + 21600 if expires is None else expires
    key = json.dumps([imdb, 0, tmdb, "default", season, episode, duration],
                     separators=(",", ":"))
    value = {"trusted_segments": segments if segments is not None else SEGMENTS,
             "conflicts": conflicts or [], "sources": {"introdb": "ok"}}
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS trusted_external_cache("
                   "identity TEXT PRIMARY KEY, expires_at INT, created_at INT, "
                   "response TEXT)")
        db.execute("INSERT OR REPLACE INTO trusted_external_cache VALUES(?,?,?,?)",
                   (key, expires, int(time.time()), json.dumps(value)))

class ProductionCacheTests(unittest.TestCase):
    def test_external_segments_without_touching_original(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"trusted.sqlite3"
            make_cache(path)
            original = [{"segment_type": "recap", "start_ms": 0,
                         "end_ms": 9000, "status": "approved", "source": "episcene"}]
            before = path.read_bytes()
            result = augment_authorized_segments(original, descriptor=DESC,
                                                 persisted_identity=IDENTITY, cache=path)
            self.assertEqual(len(result), 3)
            self.assertEqual({m["segment_type"] for m in result},
                             {"recap", "intro", "outro"})
            self.assertEqual(original[0]["source"], "episcene")
            self.assertEqual(len(original), 1)
            self.assertEqual(before, path.read_bytes())
            self.assertTrue(all(m["status"] == "approved" for m in result))

    def test_first_party_marker_wins_and_overlaps_blocked(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"cache.sqlite3"
            make_cache(path)
            existing = [{"segment_type": "intro", "start_ms": 8000,
                         "end_ms": 65000}]
            result = augment_authorized_segments(existing, descriptor=DESC,
                                                 persisted_identity=IDENTITY, cache=path)
            self.assertEqual(len(result), 2)
            self.assertEqual(result[0]["start_ms"], 8000)
            self.assertEqual(result[1]["segment_type"], "outro")

    def test_wrong_edition_and_episode_return_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"cache.sqlite3"
            make_cache(path)
            for altered in (dict(DESC, duration_ms=2600000),
                            dict(DESC, episode=2),
                            dict(DESC, media_type="movie")):
                self.assertEqual(augment_authorized_segments(
                    [], descriptor=altered, persisted_identity=IDENTITY, cache=path), [])

    def test_conflicts_and_expiry_are_not_served(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/"cache.sqlite3"
            make_cache(path, conflicts=["intro"])
            got = augment_authorized_segments([],descriptor=DESC,
                                              persisted_identity=IDENTITY,cache=path)
            self.assertEqual([x["segment_type"] for x in got],["outro"])
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"cache.sqlite3"
            make_cache(path,expires=int(time.time())-60)
            self.assertEqual(augment_authorized_segments(
                [],descriptor=DESC,persisted_identity=IDENTITY,cache=path),[])

    def test_absent_persisted_id_or_mismatch_blocks(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"cache.sqlite3"
            make_cache(path)
            for identity in ({},None,dict(IDENTITY,source_key="another"),
                             dict(IDENTITY,imdb_id="tt0000001")):
                self.assertEqual(augment_authorized_segments(
                    [],descriptor=DESC,persisted_identity=identity,cache=path),[])

    def test_client_id_is_not_used(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"cache.sqlite3"
            make_cache(path)
            evil = dict(DESC,imdb_id="tt0000001",tmdb_id=999)
            result = augment_authorized_segments(
                [],descriptor=evil,persisted_identity=IDENTITY,cache=path)
            self.assertEqual(len(result),2)

    def test_multiple_cached_editions_disagree_and_suppress_skip(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"cache.sqlite3"
            make_cache(path)
            modified=[{"segment_type":"intro","start_ms":90000,
                       "end_ms":120000,"source":"introdb","trusted":True}]
            make_cache(path, modified, duration=2700001, tmdb=0)
            result=augment_authorized_segments(
                [],descriptor=DESC,persisted_identity=IDENTITY,cache=path)
            self.assertEqual([x["segment_type"] for x in result],["outro"])

    def test_cache_missing_return_unchanged(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(augment_authorized_segments(
                [],descriptor=DESC,persisted_identity=IDENTITY,
                cache=Path(temp)/"missing.db"),[])

if __name__ == "__main__":
    unittest.main()
