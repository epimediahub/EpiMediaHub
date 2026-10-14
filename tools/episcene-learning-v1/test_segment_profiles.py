#!/usr/bin/env python3
"""Unit tests: series/season/segment isolation and no fake supervised labels."""
import unittest
from segment_profiles import verified_profiles


def row(title, kind, duration_s, asset, *, playlist=8, season=1,
        verified=1, active=1, start=90000):
    return {
        "series_title": title, "series_normalized": title.casefold(),
        "playlist_id": playlist, "season": season,
        "asset_key": asset, "segment_type": kind,
        "start_ms": start, "end_ms": start + round(duration_s * 1000),
        "verified": verified, "active": active,
    }


class SegmentProfilesTest(unittest.TestCase):
    def test_credits_not_mixed_across_shows(self):
        samples = [
            row("Lie to Me", "outro", 39, "lie1"),
            row("Lie to Me", "outro", 40, "lie2"),
            row("Lie to Me", "outro", 41, "lie3"),
            row("MobLand", "outro", 95, "mob1"),
            row("MobLand", "outro", 102, "mob2"),
            row("MobLand", "outro", 98, "mob3"),
        ]
        profiles = verified_profiles(samples)
        self.assertEqual(len(profiles), 2)
        by_show = {x["series"]: x for x in profiles}
        self.assertEqual(by_show["lie to me"]["median_duration_sec"], 40)
        self.assertEqual(by_show["mobland"]["median_duration_sec"], 98)
        self.assertTrue(all(x["reference_ready"] for x in profiles))
        self.assertTrue(all(not x["release_automatically"] for x in profiles))

    def test_recap_can_vary_and_does_not_contaminate_intro(self):
        samples = [
            row("Example", "recap", 20, "a"),
            row("Example", "recap", 45, "b"),
            row("Example", "recap", 30, "c"),
            row("Example", "recap", 110, "d"),
            row("Example", "intro", 12, "e"),
        ]
        profiles = verified_profiles(samples)
        self.assertEqual({x["segment_type"] for x in profiles}, {"recap", "intro"})
        by_type = {x["segment_type"]: x for x in profiles}
        self.assertTrue(by_type["recap"]["reference_ready"])
        self.assertFalse(by_type["intro"]["reference_ready"])
        self.assertEqual(by_type["recap"]["max_duration_sec"], 110)

    def test_unverified_and_old_labels_ignored(self):
        samples = [
            row("MobLand", "outro", 33, "auto", verified=0),
            row("MobLand", "outro", 55, "old", active=0),
            row("MobLand", "outro", 100, "verified1"),
        ]
        p = verified_profiles(samples)
        self.assertEqual(len(p), 1)
        self.assertEqual(p[0]["verified_episodes"], 1)
        self.assertEqual(p[0]["median_duration_sec"], 100)
        self.assertFalse(p[0]["reference_ready"])

    def test_conflicting_human_labels_excluded(self):
        samples = [row("Example", "intro", 15, "a"),
                   row("Example", "intro", 26, "a"),
                   row("Example", "intro", 16, "b")]
        profile = verified_profiles(samples)[0]
        self.assertEqual(profile["verified_episodes"], 1)
        self.assertEqual(profile["conflicted_episodes_excluded"], 1)

    def test_playlist_and_season_are_separate(self):
        p = verified_profiles([
            row("Example", "outro", 40, "a", playlist=8, season=1),
            row("Example", "outro", 70, "b", playlist=10, season=1),
            row("Example", "outro", 90, "c", playlist=8, season=2),
        ])
        self.assertEqual(len(p), 3)


if __name__ == "__main__":
    unittest.main()
