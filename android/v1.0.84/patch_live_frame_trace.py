#!/usr/bin/env python3
"""Read-only, non-release trace of the real Media3 video frame release metadata.

Run only after the v184 cadence snapshot patches. Does not alter player clocks,
stream URLs, display switches, codecs, buffers, or customer release settings.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
ui = root / "app/src/main/java/de/epimediahub/app/ui"
surface = ui / "V121VodSurface.kt"
player = ui / "PlayerScreen.kt"

def once(path, old, new):
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit("STOP_LIVE_TRACE_SOURCE_DRIFT " + str(path) + " anchorCount=" + str(text.count(old)))
    path.write_text(text.replace(old, new, 1), encoding="utf-8")

once(player,
'''    var compatibilityUrl by remember(item.resumeKey, item.streamUrl) { mutableStateOf("") }
    if (useVlc) {''',
'''    var compatibilityUrl by remember(item.resumeKey, item.streamUrl) { mutableStateOf("") }
    // Engine route only. Never include user playlists, credentials or stream URLs in logs.
    LaunchedEffect(item.resumeKey, useVlc) {
        if (item.kind == MediaKind.LIVE) android.util.Log.i(
            "EpiMediaHubLive", "LIVE_ENGINE=" + (if (useVlc) "VLC" else "MEDIA3_EXOPLAYER"))
    }
    if (useVlc) {''')

once(surface,
'''    private val metadata = object : VideoFrameMetadataListener {''',
'''    // Frame release diagnostics are renderer-thread-owned and do not change scheduling.
    private var traceGeneration = -1
    private var traceWindowAtMs = 0L
    private var tracePrevReleaseNs = 0L
    private var tracePrevPtsUs = Long.MIN_VALUE
    private var traceCallbacks = 0
    private var traceReleasePairs = 0
    private var traceReleaseSumMs = 0.0
    private var traceReleaseMaxMs = 0.0
    private var traceReleaseGaps60 = 0
    private var traceReleaseGaps100 = 0
    private var tracePtsPairs = 0
    private var tracePtsSumMs = 0.0
    private var tracePtsMaxMs = 0.0
    private var tracePtsGaps60 = 0
    private var traceNonMonotonic = 0

    private fun resetTrace(now: Long, generation: Int) {
        traceGeneration = generation
        traceWindowAtMs = now
        tracePrevReleaseNs = 0L
        tracePrevPtsUs = Long.MIN_VALUE
        traceCallbacks = 0
        traceReleasePairs = 0
        traceReleaseSumMs = 0.0
        traceReleaseMaxMs = 0.0
        traceReleaseGaps60 = 0
        traceReleaseGaps100 = 0
        tracePtsPairs = 0
        tracePtsSumMs = 0.0
        tracePtsMaxMs = 0.0
        tracePtsGaps60 = 0
        traceNonMonotonic = 0
    }

    private val metadata = object : VideoFrameMetadataListener {''')

once(surface,
'''            if (closed) return
            val generation = sampleGeneration
            if (estimatorGeneration != generation) { estimator.reset(); estimatorGeneration = generation }
            val candidate = estimator.sample(presentationTimeUs) ?: return''',
'''            if (closed) return
            val generation = sampleGeneration
            val now = android.os.SystemClock.elapsedRealtime()
            if (traceGeneration != generation || traceWindowAtMs == 0L) {
                resetTrace(now, generation)
            }
            traceCallbacks++
            if (releaseTimeNs > 0L && tracePrevReleaseNs > 0L) {
                val gapMs = (releaseTimeNs - tracePrevReleaseNs) / 1_000_000.0
                if (gapMs <= 0.0) traceNonMonotonic++
                else if (gapMs < 1000.0) {
                    traceReleasePairs++
                    traceReleaseSumMs += gapMs
                    traceReleaseMaxMs = kotlin.math.max(traceReleaseMaxMs, gapMs)
                    if (gapMs > 60.0) traceReleaseGaps60++
                    if (gapMs > 100.0) traceReleaseGaps100++
                }
            }
            tracePrevReleaseNs = if (releaseTimeNs > 0L) releaseTimeNs else 0L
            if (tracePrevPtsUs != Long.MIN_VALUE) {
                val gapMs = (presentationTimeUs - tracePrevPtsUs) / 1000.0
                if (gapMs > 0.0 && gapMs < 1000.0) {
                    tracePtsPairs++
                    tracePtsSumMs += gapMs
                    tracePtsMaxMs = kotlin.math.max(tracePtsMaxMs, gapMs)
                    if (gapMs > 60.0) tracePtsGaps60++
                }
            }
            tracePrevPtsUs = presentationTimeUs
            if (now - traceWindowAtMs >= 10_000L) {
                val releaseAvg = if (traceReleasePairs > 0) traceReleaseSumMs / traceReleasePairs else -1.0
                val ptsAvg = if (tracePtsPairs > 0) tracePtsSumMs / tracePtsPairs else -1.0
                Log.i("EpiMediaHubCadence",
                    "FRAME_INTERVAL type=" + (if (cinemaVod) "VOD" else "LIVE") +
                    " frames=" + traceCallbacks +
                    " releaseSamples=" + traceReleasePairs +
                    " releaseAvgMs=" + releaseAvg +
                    " releaseMaxMs=" + traceReleaseMaxMs +
                    " releaseOver60=" + traceReleaseGaps60 +
                    " releaseOver100=" + traceReleaseGaps100 +
                    " ptsSamples=" + tracePtsPairs +
                    " ptsAvgMs=" + ptsAvg +
                    " ptsMaxMs=" + tracePtsMaxMs +
                    " ptsOver60=" + tracePtsGaps60 +
                    " nonMonotonic=" + traceNonMonotonic)
                resetTrace(now, generation)
            }
            if (estimatorGeneration != generation) { estimator.reset(); estimatorGeneration = generation }
            val candidate = estimator.sample(presentationTimeUs) ?: return''')

print("QA_LIVE_FRAME_RELEASE_TRACE_INSTALLED")