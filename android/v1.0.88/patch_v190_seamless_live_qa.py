#!/usr/bin/env python3
"""v190 QA: conservative live refresh-rate matching with full v188 sport features.

Never use preferredDisplayModeId for Live TV. On Android 11+ only request
seamless Surface frame-rate changes. On older Fire OS use the window's soft
preferredRefreshRate hint at the same resolution. Never force a nonseamless
HDMI mode transition during active playback. Restore all owned hints on close.
"""
import os
from pathlib import Path
root = Path(os.environ["PROJECT_ROOT"])
ui = root / "app/src/main/java/de/epimediahub/app/ui"
surface = ui / "V121VodSurface.kt"
gradle = root / "app/build.gradle.kts"
player = ui / "PlayerScreen.kt"
vm = root / "app/src/main/java/de/epimediahub/app/MainViewModel.kt"

def once(path, old, new):
    src = path.read_text(encoding="utf-8")
    assert src.count(old) == 1, "STOP_V190_DRIFT: " + str(path) + ": " + str(src.count(old))
    path.write_text(src.replace(old, new, 1), encoding="utf-8")

once(gradle, "versionCode = 1089", "versionCode = 1090")
once(gradle, 'versionName = "1.0.89-qa"', 'versionName = "1.0.90"')
# Non-seamless forced mode switching is the suspected crash trigger.
# This helper is a request, not a forced HDMI mode transition.
once(surface,
    '    fun match(fps: Float, surface: SurfaceView, allow1080p: Boolean, liveTv: Boolean = false): String {',
    '''    private val originalRefreshRate = activity?.window?.attributes?.preferredRefreshRate ?: 0f
    private var liveRequestedRefreshRate: Float? = null

    fun matchLiveConservatively(fps: Float, surface: SurfaceView): String {
        val host = activity ?: return "Live: TV-Fenster nicht verfügbar"
        if (host.isFinishing || host.isDestroyed || host.isInMultiWindowMode)
            return "Live: Anzeige wird nicht geändert"
        val display = surface.display ?: return "Live: Anzeige nicht bereit"
        val current = display.mode
        val available = display.supportedModes.map {
            V121DisplayMode(it.modeId, it.physicalWidth, it.physicalHeight, it.refreshRate)
        }
        val target = V170LiveCadencePolicy.matchingMode(
            V121DisplayMode(current.modeId, current.physicalWidth, current.physicalHeight, current.refreshRate),
            available, fps
        ) ?: return "Live: keine sichere Bildratenkombination"
        if (kotlin.math.abs(current.refreshRate - target.hz) < .012f)
            return "Live: ${target.hz} Hz bereits aktiv"
        if (liveRequestedRefreshRate != null &&
            kotlin.math.abs(liveRequestedRefreshRate!! - target.hz) < .012f)
            return "Live: ${target.hz} Hz nahtlos angefragt"
        // Soft refresh-only preference: unlike preferredDisplayModeId this
        // does not request a hard resolution/mode reset while decoding.
        val params = host.window.attributes
        if (params.preferredDisplayModeId != 0) return "Live: bestehende Anzeigevorgabe hat Vorrang"
        params.preferredRefreshRate = target.hz
        host.window.attributes = params
        liveRequestedRefreshRate = target.hz
        return "Live: ${target.hz} Hz bevorzugt (kein erzwungener HDMI-Wechsel)"
    }

    fun match(fps: Float, surface: SurfaceView, allow1080p: Boolean, liveTv: Boolean = false): String {''')
once(surface,
    '''    fun restore() {
        val ownMode = requestedMode ?: return''',
    '''    fun restore() {
        if (liveRequestedRefreshRate != null) {
            liveRequestedRefreshRate = null
            val host = activity
            if (host != null && !host.isDestroyed) {
                val p = host.window.attributes
                p.preferredRefreshRate = originalRefreshRate
                host.window.attributes = p
            }
        }
        val ownMode = requestedMode ?: return''')

once(surface,
    '''    private var ownsHint = false
''',
    '''    private var ownsHint = false
    private var liveSeamlessHint = false
''')
once(surface,
    '''                request = "Live-TV: stabiler Ausgabemodus (automatischer HDMI-Wechsel im QA-Test gesperrt)"''',
    '''                if (Build.VERSION.SDK_INT >= 30) {
                    val videoSurface = view.holder.surface
                    if (!videoSurface.isValid) {
                        request = "Live: Videofläche noch nicht bereit"
                    } else if (!liveSeamlessHint || kotlin.math.abs(lastApplied - fps) > .002f) {
                        videoSurface.setFrameRate(
                            fps, Surface.FRAME_RATE_COMPATIBILITY_FIXED_SOURCE,
                            Surface.CHANGE_FRAME_RATE_ONLY_IF_SEAMLESS
                        )
                        liveSeamlessHint = true
                        lastApplied = fps
                        request = "Live: nahtlose Bildrate beim System angefragt"
                    }
                } else {
                    request = displayLease.matchLiveConservatively(fps, view)
                }''')
once(surface,
    '''    private fun clearHint() {
        if (!ownsHint) return''',
    '''    private fun clearHint() {
        if (liveSeamlessHint) {
            liveSeamlessHint = false
            lastApplied = 0f
            if (Build.VERSION.SDK_INT >= 30) runCatching {
                val videoSurface = view.holder.surface
                if (videoSurface.isValid) videoSurface.setFrameRate(
                    0f, Surface.FRAME_RATE_COMPATIBILITY_DEFAULT,
                    Surface.CHANGE_FRAME_RATE_ONLY_IF_SEAMLESS
                )
            }.onFailure { Log.w("EpiMediaHubVideo", "Clear live rate hint failed", it) }
        }
        if (!ownsHint) return''')
code=surface.read_text()
assert 'displayLease.match(fps, view, allow1080p = false, liveTv = true)' not in code
assert 'Surface.CHANGE_FRAME_RATE_ONLY_IF_SEAMLESS' in code
assert 'V188VerifiedFps.verifiedCandidate(' in player.read_text()
assert 'V188SportContext.automaticOfferAllowed(' in player.read_text()
assert 'V188SportMode.verifiedAlternatives(' in vm.read_text()
print("V190_CONSERVATIVE_LIVE_FRAME_RATE_MATCHING_V188_SPORT_FEATURES_PRESERVED")
