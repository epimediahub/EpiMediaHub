#!/usr/bin/env python3
"""v1.0.61: conservative Smart EPG reuse + provider-aware player fallback.
Run after v1.0.60. No change to playlist credentials, VPN route or Live stream URLs.
The approved 17.5-second V5 media is a separate mandatory release prerequisite.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str):
    text = path.read_text()
    occurrences = text.count(old)
    if occurrences != 1:
        raise SystemExit(str(path) + " expected one anchor; got " + str(occurrences) + ": " + old[:120])
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, "versionCode = 1060", "versionCode = 1061")
replace_once(gradle, 'versionName = "1.0.60"', 'versionName = "1.0.61"')

shutil.copyfile(here / "V161SmartEpg.kt", java / "data/V161SmartEpg.kt")
shutil.copyfile(here / "V161PlaybackRetryPolicy.kt", java / "ui/V161PlaybackRetryPolicy.kt")
shutil.copyfile(here / "V161PoliciesTest.kt", tests / "ui/V161PoliciesTest.kt")

# Enrich only on EPG or channel list changes; no extra network calls.
vm = java / "MainViewModel.kt"
replace_once(vm,
    '    private fun set(block: (UiState) -> UiState) { _ui.value = block(_ui.value) }',
    '''    private fun set(block: (UiState) -> UiState) {
        val old = _ui.value
        val state = block(old)
        val profile = state.active
        val refresh = state.epg !== old.epg ||
            state.items !== old.items || state.catalogRows !== old.catalogRows
        _ui.value = if (refresh && profile != null &&
                profile.id == old.active?.id && state.epg.isNotEmpty()) {
            val cached = libraryCatalogCache[catalogueKey(profile, MediaKind.LIVE)]
            val channels = state.items + state.catalogRows.values.flatten() +
                cached?.rows?.values?.flatten().orEmpty()
            state.copy(epg = V161SmartEpg.enrich(channels, state.epg))
        } else state
    }''')
src = vm.read_text()
if "import de.epimediahub.app.data.V161SmartEpg" not in src:
    anchor = "package de.epimediahub.app\n"
    if src.count(anchor) != 1: raise SystemExit("Unexpected MainViewModel package")
    vm.write_text(src.replace(anchor, anchor + "\nimport de.epimediahub.app.data.V161SmartEpg\n", 1))

# The same Media3 player handles Live, Movies and Episodes.
# Stop on 429/401/403 and allow a maximum of two VOD candidates.
player = java / "ui/PlayerScreen.kt"
replace_once(player,
'''                val next = activeUrl + 1
                if (next < playbackUrls.size) {''',
'''                val next = activeUrl + 1
                if (V161PlaybackRetryPolicy.shouldTryNext(item.kind, httpCode, next, playbackUrls.size)) {''')
replace_once(player,
'''                } else if (item.kind == MediaKind.LIVE && !manualPlayerChoice) {
                    compatibilityUrl = playbackUrls.getOrNull(activeUrl).orEmpty()''',
'''                } else if (item.kind == MediaKind.LIVE && !manualPlayerChoice &&
                    !V161PlaybackRetryPolicy.providerBlocked(httpCode)) {
                    compatibilityUrl = playbackUrls.getOrNull(activeUrl).orEmpty()''')
source = player.read_text()
candidate_lines = [line for line in source.splitlines() if "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt" in line]
if len(candidate_lines) != 1: raise SystemExit("Expected one provider-candidates error message")
replace_once(player, candidate_lines[0],
    '                    playbackError = V161PlaybackRetryPolicy.message(item.kind, httpCode, detail)')

assert "V161SmartEpg.enrich(" in vm.read_text()
assert "V161PlaybackRetryPolicy.shouldTryNext(" in player.read_text()
assert "V153DirectPolicy.canPlay" in (java / "vpn/V134VpnSession.kt").read_text()
print("v1.0.61 source ready: safer MOVIE/SERIES/EPISODE fallback and shared EPG cache.")
import subprocess
import sys
subprocess.run([sys.executable, str(here / "integrate_v161_intro.py")], check=True)
print("v1.0.61 candidate complete: V5 video, Smart EPG, VOD fallback and verified Finland VPN banner.")
