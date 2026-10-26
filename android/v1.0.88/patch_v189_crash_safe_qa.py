#!/usr/bin/env python3
"""v189 isolated QA: retain full v188 Sportmodus, remove unsafe LIVE HDMI mode switching.

The v188 PTS/FPS learning, verified cross-category alternate lookup, sports aliases,
EPG-based context, and Sportmodus dialog remain untouched. On Fire TV, switching
window preferredDisplayModeId mid-stream can recreate the output surface/decoder.
This QA variant keeps the current output mode while the player is active.

This containment is not proof of root cause or a completed judder fix.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
source = root / "app/src/main/java/de/epimediahub/app/ui/V121VodSurface.kt"
gradle = root / "app/build.gradle.kts"
player = root / "app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
vm = root / "app/src/main/java/de/epimediahub/app/MainViewModel.kt"

def replace_once(path: Path, old: str, new: str):
    content = path.read_text(encoding="utf-8")
    assert content.count(old) == 1, f"Source drift: {path.name}: {old!r}"
    path.write_text(content.replace(old, new, 1), encoding="utf-8")

replace_once(source,
    'request = displayLease.match(fps, view, allow1080p = false, liveTv = true)',
    'request = "Live-TV: stabiler Ausgabemodus (automatischer HDMI-Wechsel im QA-Test gesperrt)"')
replace_once(gradle, "versionCode = 1088", "versionCode = 1089")
replace_once(gradle, 'versionName = "1.0.88"', 'versionName = "1.0.89-qa"')

# Ensure the sport functionality has not been removed by the safety patch.
assert "V188VerifiedFps.verifiedCandidate(" in player.read_text()
assert "V188SportContext.automaticOfferAllowed(" in player.read_text()
assert "V188SportMode.verifiedAlternatives(" in vm.read_text()
assert "v188AllLiveCandidates(" in vm.read_text()
assert 'displayLease.match(fps, view, allow1080p = false, liveTv = true)' not in source.read_text()
print("V189_QA_LIVE_HDMI_SWITCH_DISABLED_V188_SPORT_FEATURES_PRESERVED")
