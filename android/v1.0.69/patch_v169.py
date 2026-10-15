#!/usr/bin/env python3
"""v1.0.69 private Cinema judder test: VOD-only non-seamless display matching.

Preserve Live TV, VPN, EPG, existing playback and public updater.
The OS may refuse a requested mode; diagnostics still read actual output Hz.
"""
import os
from pathlib import Path
import shutil

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
app = root / "app"
java = app / "src/main/java/de/epimediahub/app"
ui = java / "ui"

def replace_once(path, old, new):
    source = path.read_text()
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"v169 incompatible source {path}: {count} hits of {old[:85]}")
    path.write_text(source.replace(old, new, 1))

gradle = app / "build.gradle.kts"
replace_once(gradle, "versionCode = 1068", "versionCode = 1069")
replace_once(gradle, 'versionName = "1.0.68"', 'versionName = "1.0.69"')
shutil.copyfile(here / "V169CinemaModePolicy.kt", ui / "V169CinemaModePolicy.kt")
shutil.copyfile(here / "V169CinemaModePolicyTest.kt",
    app / "src/test/java/de/epimediahub/app/ui/V169CinemaModePolicyTest.kt")

vod = ui / "V116VodPlayer.kt"
replace_once(vod, "V121VodSurface(player, isTv, modifier)",
    "V121VodSurface(player, isTv, modifier, cinemaVod = true)")

surface = ui / "V121VodSurface.kt"
replace_once(surface, 'private const val FRAME_RATE_KEY = "match_vod_frame_rate"',
    'private const val FRAME_RATE_KEY = "match_vod_frame_rate"\n'
    'private const val CINEMA_1080_KEY = "cinema_allow_1080p_fallback"')
replace_once(surface, '    TextButton(onClick = {\n        enabled = !enabled',
    '    var allow1080p by remember { mutableStateOf(prefs.getBoolean(CINEMA_1080_KEY, true)) }\n'
    '    TextButton(onClick = {\n        enabled = !enabled')
replace_once(surface, '"Nahtlose Bildanpassung: "',
    '"Cinema-Bildtakt für Filme und Serien: "')
replace_once(surface,
    'Text("Nur nahtlose Anpassungen. Kein HDMI-Moduswechsel beim Zappen.", color = Color.LightGray, fontSize = 12.sp)',
    'Text("Nur bei Filmen/Serien: 24 Hz können einen kurzen schwarzen HDMI-Umschaltmoment verursachen. Live-TV bleibt unberührt.", color = Color.LightGray, fontSize = 12.sp)\n'
    '    TextButton(onClick = {\n'
    '        allow1080p = !allow1080p\n'
    '        prefs.edit().putBoolean(CINEMA_1080_KEY, allow1080p).apply()\n'
    '    }, modifier = Modifier.fillMaxWidth().v114FocusRing().testTag("cinema-1080p-fallback")) {\n'
    '        Text("1080p nur falls kein 4K-Kinomodus: " + if (allow1080p) "Ein" else "Aus",\n'
    '            color = Color.White, fontSize = 17.sp)\n'
    '    }\n'
    '    Text("Der Ausweichmodus ist optional und wird beim nächsten Videostart geprüft.", color = Color.LightGray, fontSize = 12.sp)')
replace_once(surface, 
    'internal fun V121VodSurface(player: Player, isTv: Boolean, modifier: Modifier = Modifier)',
    'internal fun V121VodSurface(player: Player, isTv: Boolean, modifier: Modifier = Modifier, cinemaVod: Boolean = false)')
replace_once(surface,
    'V121VideoView(context).apply { bind(player, isTv) }',
    'V121VideoView(context).apply { bind(player, isTv, cinemaVod) }')
replace_once(surface,
    'update = { it.bind(player, isTv) }',
    'update = { it.bind(player, isTv, cinemaVod) }')
replace_once(surface,
    '    private var television = false\n',
    '    private var television = false\n    private var cinema = false\n')
replace_once(surface,
    '    fun bind(next: Player, isTv: Boolean) {\n        if (boundPlayer === next && television == isTv) return',
    '    fun bind(next: Player, isTv: Boolean, cinemaVod: Boolean) {\n'
    '        if (boundPlayer === next && television == isTv && cinema == cinemaVod) return')
replace_once(surface,
    '        television = isTv\n        player = next',
    '        television = isTv\n        cinema = cinemaVod\n        player = next')
replace_once(surface,
    'V121FrameRateController(context, next, it, displayLease, isTv)',
    'V121FrameRateController(context, next, it, displayLease, isTv, cinemaVod)')
replace_once(surface,
    '    fun match(fps: Float, surface: SurfaceView): String {',
    '    fun match(fps: Float, surface: SurfaceView, allow1080p: Boolean): String {')
replace_once(surface,
    'val target = V121FrameRatePolicy.matchingMode(current, available, fps)',
    'val target = V169CinemaModePolicy.matchingMode(current, available, fps, allow1080p)')
start = surface.read_text().index("        // Older Fire OS cannot guarantee a seamless mode switch.")
end = surface.read_text().index("\n    }\n\n    fun restore()", start)
s = surface.read_text()
surface.write_text(s[:start] +
    '        // Only VOD calls this method. Request exactly one verified supported\n'
    '        // display mode; restoring the original preference is the lease owner.\n'
    '        val attrs = host.window.attributes\n'
    '        attrs.preferredDisplayModeId = target.id\n'
    '        host.window.attributes = attrs\n'
    '        requestedMode = target.id\n'
    '        Log.i("EpiMediaHubVideo", "Cinema display mode requested: " + target.id)\n'
    '        return "Cinema-Bildmodus angefordert: " + v122Number(target.hz) + " Hz (" +\n'
    '            target.width + " x " + target.height + "); tatsächliche TV-Ausgabe bitte prüfen"\n'
    + s[end:])
replace_once(surface,
    'private val displayLease: V121DisplayLease, private val television: Boolean',
    'private val displayLease: V121DisplayLease, private val television: Boolean,\n'
    '    private val cinemaVod: Boolean')
replace_once(surface,
    'if (key == FRAME_RATE_KEY) { enabled = prefs.getBoolean(FRAME_RATE_KEY, true); schedule() }',
    'if (key == FRAME_RATE_KEY || key == CINEMA_1080_KEY) {\n'
    '            enabled = prefs.getBoolean(FRAME_RATE_KEY, true)\n'
    '            schedule()\n'
    '        }')
replace_once(surface, 'if (!television || !enabled) {',
    'if (!television || !cinemaVod || !enabled) {')
replace_once(surface,
    'request = if (television) "Automatische Anpassung ausgeschaltet" else "Media3 steuert die Bildrate"',
    'request = if (!cinemaVod && television) "Live-TV: keine Cinema-Umschaltung" '
    'else if (television) "Cinema-Bildtakt ausgeschaltet" else "Media3 steuert die Bildrate"')
replace_once(surface,
    'surface.setFrameRate(fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE, Surface.CHANGE_FRAME_RATE_ONLY_IF_SEAMLESS)',
    'surface.setFrameRate(fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE, Surface.CHANGE_FRAME_RATE_ALWAYS)')
replace_once(surface,
    'request = "' + '$' + '{v122Number(fps)} fps nur nahtlos angefordert"',
    'request = "' + '$' + '{v122Number(fps)} fps Cinema-Wechsel angefordert (Ausgabe-Hz kontrollieren)"')
replace_once(surface,
    'request = displayLease.match(fps, view)',
    'request = displayLease.match(fps, view, prefs.getBoolean(CINEMA_1080_KEY, true))')
replace_once(surface, 'automatic = television && enabled',
    'automatic = television && cinemaVod && enabled')
assert 'V169CinemaModePolicy.matchingMode' in surface.read_text()
assert 'preferredDisplayModeId = target.id' in surface.read_text()
assert 'CHANGE_FRAME_RATE_ALWAYS)' in surface.read_text()
assert 'cinemaVod = true' in vod.read_text()
print("v169: VOD-only 24 Hz Cinema mode, optional 1080p fallback, restore on exit")
