#!/usr/bin/env python3
"""Private v170 test: retain v169 Cinema VOD and add native 25/50-Hz Live matching.

Live uses its OWN policy: prefer 50 Hz for 25/50-fps streams, 59.94/60 for
29.97/30 and keep the same resolution. Never force modes when FPS is unknown.
No public customer updater modifications.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
app = root / "app"
ui = app / "src/main/java/de/epimediahub/app/ui"
tests = app / "src/test/java/de/epimediahub/app/ui"

def replace(path, old, new):
    source = path.read_text()
    if source.count(old) != 1:
        raise SystemExit("v170 incompatible anchor in " + str(path) + ": " + old[:85])
    path.write_text(source.replace(old, new, 1))

gradle = app / "build.gradle.kts"
replace(gradle, "versionCode = 1069", "versionCode = 1070")
replace(gradle, 'versionName = "1.0.69"', 'versionName = "1.0.70"')
shutil.copyfile(here / "V170LiveCadencePolicy.kt", ui / "V170LiveCadencePolicy.kt")
shutil.copyfile(here / "V170LiveCadencePolicyTest.kt", tests / "V170LiveCadencePolicyTest.kt")

surface = ui / "V121VodSurface.kt"
replace(surface, 'private const val CINEMA_1080_KEY = "cinema_allow_1080p_fallback"',
    'private const val CINEMA_1080_KEY = "cinema_allow_1080p_fallback"\n'
    'private const val LIVE_FRAME_RATE_KEY = "match_live_frame_rate"')

replace(surface, 'fun match(fps: Float, surface: SurfaceView, allow1080p: Boolean): String {',
    'fun match(fps: Float, surface: SurfaceView, allow1080p: Boolean, liveTv: Boolean = false): String {')
replace(surface, 'val target = V169CinemaModePolicy.matchingMode(current, available, fps, allow1080p)',
    'val target = if (liveTv) V170LiveCadencePolicy.matchingMode(current, available, fps)\n'
    '            else V169CinemaModePolicy.matchingMode(current, available, fps, allow1080p)')
replace(surface, 'if (target == null) { restore(); return "Kein passender TV-Modus bei dieser Auflösung gemeldet" }',
    'if (target == null) {\n'
    '            restore()\n'
    '            return if (liveTv) "Live-TV: kein passender Bildmodus für diesen Sender"\n'
    '            else "Kein passender TV-Modus bei dieser Auflösung gemeldet"\n'
    '        }')
replace(surface, '    private var enabled = prefs.getBoolean(FRAME_RATE_KEY, true)',
    '    private var enabled = prefs.getBoolean(FRAME_RATE_KEY, true)\n'
    '    private var liveEnabled = prefs.getBoolean(LIVE_FRAME_RATE_KEY, true)')
replace(surface, 'if (key == FRAME_RATE_KEY || key == CINEMA_1080_KEY) {',
    'if (key == FRAME_RATE_KEY || key == CINEMA_1080_KEY || key == LIVE_FRAME_RATE_KEY) {')
replace(surface, 'enabled = prefs.getBoolean(FRAME_RATE_KEY, true)\n            schedule()',
    'enabled = prefs.getBoolean(FRAME_RATE_KEY, true)\n'
    '            liveEnabled = prefs.getBoolean(LIVE_FRAME_RATE_KEY, true)\n'
    '            schedule()')
replace(surface, 'if (!television || !cinemaVod || !enabled) {',
    'if (!television || (cinemaVod && !enabled) || (!cinemaVod && !liveEnabled)) {')
replace(surface,
    'request = if (!cinemaVod && television) "Live-TV: keine Cinema-Umschaltung" else if (television) "Cinema-Bildtakt ausgeschaltet" else "Media3 steuert die Bildrate"',
    'request = if (!television) "Media3 steuert die Bildrate" else if (cinemaVod)\n'
    '                "Cinema-Bildtakt ausgeschaltet" else "Live-TV Bildanpassung ausgeschaltet"')
replace(surface,
    '        if (Build.VERSION.SDK_INT >= 31) {',
    '''        if (!cinemaVod) {
            // Live and VOD must select modes differently: 25 fps TV needs 50 Hz,
            // whereas cinema should output 23.976 fps at exactly 23.976 Hz.
            // Explicit mode selection also works on older Fire OS revisions.
            runCatching {
                request = displayLease.match(fps, view, allow1080p = false, liveTv = true)
            }.onFailure {
                request = "Live-TV-Bildmodus konnte nicht angefordert werden"
                Log.w("EpiMediaHubVideo", "Live mode unchanged", it)
            }
            return
        }
        if (Build.VERSION.SDK_INT >= 31) {''')
replace(surface, 'automatic = television && cinemaVod && enabled',
    'automatic = television && (if (cinemaVod) enabled else liveEnabled)')
assert 'V170LiveCadencePolicy.matchingMode' in surface.read_text()
assert 'if (!cinemaVod) {' in surface.read_text()
assert 'cinemaVod = true' in (ui / 'V116VodPlayer.kt').read_text()
print('v170: Live 25/50 -> 50Hz and VOD Cinema 23.976 -> 23.976Hz, separated')
