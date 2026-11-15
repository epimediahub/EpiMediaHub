#!/usr/bin/env python3
"""Extend the non-release v184 cadence diagnostic to VOD and all Media3 sessions.

Run AFTER patch_cadence_diagnostics.py. Diagnostic-only: no changes to timing or display modes.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
source = root / "app/src/main/java/de/epimediahub/app/ui/V121VodSurface.kt"
code = source.read_text(encoding="utf-8")
old = """    private var lastCadenceLogAtMs = 0L
    private var droppedSinceLog = 0

"""
new = """    private var lastCadenceLogAtMs = 0L
    private var droppedSinceLog = 0
    private var cadenceLogGeneration = 0
    private val cadenceLog = object : Runnable {
        override fun run() {
            if (closed) return
            val mode = view.display?.mode
            val format = player.videoFormat
            val counters = player.videoDecoderCounters
            counters?.ensureUpdated()
            val type = if (cinemaVod) "VOD" else "LIVE"
            Log.i("EpiMediaHubCadence",
                "type=$type metadataFps=${format?.frameRate} measuredFps=$measuredFps " +
                "displayHz=${mode?.refreshRate} modeId=${mode?.modeId} " +
                "drops=${counters?.droppedBufferCount} rendered=${counters?.renderedOutputBufferCount} " +
                "bufferMs=${player.totalBufferedDuration} decoder=$decoder request=$request")
            handler.postDelayed(this, 10_000L)
        }
    }

"""
assert code.count(old) == 1, "Expected baseline diagnostics missing"
code = code.replace(old, new, 1)
old = """        view.holder.addCallback(this)
        schedule()
"""
new = """        view.holder.addCallback(this)
        handler.postDelayed(cadenceLog, 10_000L)
        schedule()
"""
assert code.count(old) == 1, "Expected initialization anchor missing"
code = code.replace(old, new, 1)
# Ensure periodic diagnostics stop when the surface/player is disposed.
old = """    private fun clearHint() {
"""
new = """    private fun clearHint() {
"""
assert code.count(old) == 1
# The controller close() already removes all handler callbacks via
# handler.removeCallbacksAndMessages(null). Do not remove the periodic
# diagnostic from schedule(): doing so would silence it on every format update.
assert "handler.removeCallbacksAndMessages(null)" in code
source.write_text(code, encoding="utf-8")
print("Cadence snapshots enabled for Media3 live and VOD every 10s")
