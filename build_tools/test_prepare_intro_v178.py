#!/usr/bin/env python3
"""Static/storyboard regression tests for the 20-second EpiMediaHub cinematic."""
from pathlib import Path
import importlib.util
import unittest

module_path=Path(__file__).with_name("prepare_intro_v178.py")
spec=importlib.util.spec_from_file_location("prepare_intro_v178",module_path)
intro=importlib.util.module_from_spec(spec)
spec.loader.exec_module(intro)

class Intro20SecondTests(unittest.TestCase):
    def test_exact_length_and_segment_order(self):
        scenes=intro.SCENES
        self.assertEqual(intro.DURATION,20)
        self.assertEqual(intro.ORIGINAL_DURATION,17.5)
        self.assertEqual(len(scenes),7)
        self.assertAlmostEqual(scenes[0][0],2.0)
        for i,scene in enumerate(scenes):
            self.assertGreater(scene[1],scene[0])
            self.assertLessEqual(scene[1],20.0)
            if i:
                self.assertAlmostEqual(scene[0],scenes[i-1][1])
        self.assertGreaterEqual(scenes[-1][1],19.9)

    def test_episcene_explains_subfeatures_not_just_name(self):
        items=intro.SCENES
        self.assertEqual(sum("EPISCENE" in s[2] for s in items),3)
        intro_text=" ".join(" ".join(s[2:]) for s in items).lower()
        for capability in ("rückblicke","intros","abspann","nächste folge",
                           "markierungen","bestätigte marker"):
            self.assertIn(capability,intro_text)

    def test_vpn_is_explicit_and_not_false_protection_guarantee(self):
        vpn=" ".join(" ".join(s[2:]) for s in intro.SCENES if "VPN" in s[2]).lower()
        self.assertIn("playlist",vpn)
        self.assertIn("standort",vpn)
        self.assertNotIn("100 %",vpn)
        self.assertNotIn("anonym",vpn)

    def test_smarttube_adaptive_quality_only(self):
        text=" ".join(" ".join(s[2:]) for s in intro.SCENES).lower()
        self.assertIn("adaptive qualität",text)
        self.assertIn("speedtest",text)

    def test_original_timeline_intact_with_branded_logo_hold(self):
        self.assertAlmostEqual(intro.DURATION-intro.ORIGINAL_DURATION,2.5)
        self.assertIn("EPIMEDIAHUB",intro.SCENES[-1][2])
        self.assertFalse(any("VPN" in s[2] for s in intro.SCENES[:3]))

if __name__=="__main__":
    unittest.main()
