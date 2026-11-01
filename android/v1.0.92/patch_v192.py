#!/usr/bin/env python3
"""v1.0.92 Fire TV QA: stable cadence matching without zapping-triggered HDMI thrash.

Applied strictly after patch_v191.py. Keeps v188 verified Sportmodus and does
not alter EpiScene, playlist sessions, VOD, VPN or the public in-app updater.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
app = root / "app"
ui = app / "src/main/java/de/epimediahub/app/ui"
surface = ui / "V121VodSurface.kt"
gradle = app / "build.gradle.kts"
tests = app / "src/test/java/de/epimediahub/app/ui"

def once(path, before, after):
    source = path.read_text(encoding="utf-8")
    count = source.count(before)
    if count != 1:
        raise SystemExit("STOP_V192_SOURCE_DRIFT " + path.name +
                         " count=" + str(count) + " anchor=" + repr(before[:95]))
    path.write_text(source.replace(before, after, 1), encoding="utf-8")

once(gradle, "versionCode = 1091", "versionCode = 1092")
once(gradle, 'versionName = "1.0.91"', 'versionName = "1.0.92"')

shutil.copy2(here / "V192LiveModeHold.kt", ui / "V192LiveModeHold.kt")
tests.mkdir(parents=True, exist_ok=True)
shutil.copy2(here / "V192LiveCadencePolicyTest.kt", tests / "V192LiveCadencePolicyTest.kt")

# The local VOD display lease must remember the original pre-Live preference:
# a VOD view can be constructed before it binds and restores the live session.
once(surface,
    '    private val originalMode = activity?.window?.attributes?.preferredDisplayModeId ?: 0',
    '''    private val originalMode = V192LiveModeHold.originalPreference(activity)
        ?: (activity?.window?.attributes?.preferredDisplayModeId ?: 0)''')

# Keep the 50/60Hz HDMI preference throughout fast channel/player replacement.
# Independent VOD handoff restores the live preference before cinema applies.
once(surface,
    '    private var cinema = false\n',
    '    private var cinema = false\n    private var v192LiveAttached = false\n')
once(surface,
    '''        frameRate?.close()
        boundPlayer = next
        television = isTv
        cinema = cinemaVod''',
    '''        frameRate?.close()
        val liveHost = context.activity()
        if (v192LiveAttached && (!isTv || cinemaVod)) {
            V192LiveModeHold.detach(liveHost)
            v192LiveAttached = false
        }
        if (isTv && !cinemaVod) {
            if (!v192LiveAttached) {
                V192LiveModeHold.attach(liveHost)
                v192LiveAttached = true
            } else {
                V192LiveModeHold.invalidate(liveHost)
            }
        } else if (isTv && cinemaVod) {
            V192LiveModeHold.handoffForCinema(liveHost)
        }
        boundPlayer = next
        television = isTv
        cinema = cinemaVod''')
# Scope this insertion to V121VideoView.close(), without assuming there are
# no other lifecycle statements between frameRate reset and display restore.
source = surface.read_text(encoding="utf-8")
view_start = source.index("internal class V121VideoView(")
close_start = source.index("    fun close() {", view_start)
close_end = source.index(chr(10) + "    }", close_start)
close_body = source[close_start:close_end]
anchor = "        displayLease.restore()"
if close_body.count(anchor) != 1 or "frameRate?.close()" not in close_body:
    raise SystemExit("STOP_V192_UNEXPECTED_VIDEO_VIEW_CLOSE")
close_body = close_body.replace(anchor, '''        if (v192LiveAttached) {
            V192LiveModeHold.detach(context.activity())
            v192LiveAttached = false
        }
        displayLease.restore()''', 1)
surface.write_text(source[:close_start] + close_body + source[close_end:], encoding="utf-8")

# No unconditional HDMI request inside the format callback. Schedule one
# stable mode after 3s, cancel on zap, keep prior mode for >=7s across views,
# allow another real mode change only after an 18s cooldown.
once(surface,
    'request = "Live: stabile TV-Ausgabe ohne automatischen HDMI-Moduswechsel"',
    'request = V192LiveModeHold.request(view.context.activity(), view, fps)')

# Switching Live frame-rate matching off should restore only a mode we own.
once(surface,
    '''        if (!television || (cinemaVod && !enabled) || (!cinemaVod && !liveEnabled)) {''',
    '''        if (!television || (cinemaVod && !enabled) || (!cinemaVod && !liveEnabled)) {
            if (television && !cinemaVod && !liveEnabled)
                V192LiveModeHold.disabled(view.context.activity())''')

current = surface.read_text(encoding="utf-8")
assert 'V192LiveModeHold.request(view.context.activity(), view, fps)' in current
assert 'V192LiveModeHold.invalidate(liveHost)' in current
assert 'V192LiveModeHold.handoffForCinema(liveHost)' in current
assert 'V170LiveCadencePolicy.matchingMode' in current
assert 'V188SportMode.verifiedAlternatives(' in (
    app / "src/main/java/de/epimediahub/app/MainViewModel.kt"
).read_text(encoding="utf-8")
assert 'V188VerifiedFps.verifiedCandidate(' in (
    ui / "PlayerScreen.kt"
).read_text(encoding="utf-8")
print("V192_LIVE_HDMI_DEBOUNCE_AND_STICKY_50HZ_INSTALLED")
print("V192_V191_STABLE_LIVE_BROWSER_AND_V188_VERIFIED_SPORTMODE_PRESERVED")
print("V192_NO_CUSTOMER_UPDATER_OR_EXTRA_IPTV_CONNECTIONS")
