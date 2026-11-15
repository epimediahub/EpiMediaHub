#!/usr/bin/env python3
"""Non-release v184 diagnostic patch. Run after patch_v184.py in reconstructed PROJECT_ROOT."""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
source = root / "app/src/main/java/de/epimediahub/app/ui/V121VodSurface.kt"
text = source.read_text(encoding="utf-8")
anchor = "    private val analytics = object : AnalyticsListener {"
assert text.count(anchor) == 1, "Unexpected frame-rate controller; abort rather than patch wrong player"
insertion = """    private var lastCadenceLogAtMs = 0L
    private var droppedSinceLog = 0

"""
text = text.replace(anchor, insertion + anchor, 1)
anchor2 = "    private val analytics = object : AnalyticsListener {\n"
addition = """        override fun onDroppedVideoFrames(
            eventTime: AnalyticsListener.EventTime,
            droppedFrames: Int,
            elapsedMs: Long
        ) {
            if (closed || droppedFrames <= 0) return
            // Analytics callbacks are dispatched on the player application looper.
            // Aggregate bursts instead of logging once per frame.
            droppedSinceLog += droppedFrames
            val now = android.os.SystemClock.elapsedRealtime()
            if (now - lastCadenceLogAtMs < 10_000L) return
            val mode = view.display?.mode
            Log.w("EpiMediaHubCadence",
                "drops10s=$droppedSinceLog sourceFps=$reportedFps measuredFps=$measuredFps " +
                "displayHz=${mode?.refreshRate} requested=$request decoder=$decoder")
            droppedSinceLog = 0
            lastCadenceLogAtMs = now
        }
"""
assert text.count(anchor2) == 1
text = text.replace(anchor2, anchor2 + addition, 1)
source.write_text(text, encoding="utf-8")
print("v184 cadence diagnostics installed: drop bursts, FPS, actual Hz, request, decoder")
