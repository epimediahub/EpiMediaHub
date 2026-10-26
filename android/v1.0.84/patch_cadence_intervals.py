#!/usr/bin/env python3
"""Add precise rendered-frame interval histogram to the Media3 cadence diagnostics.

No player timing, surface frame rate, or customer updater changes.\nThis patch is restricted to the isolated signed QA workflow.
"""
import os
from pathlib import Path
p=Path(os.environ["PROJECT_ROOT"])/"app/src/main/java/de/epimediahub/app/ui/V121VodSurface.kt"
s=p.read_text(encoding="utf-8")
anchor="    private var cadenceLogGeneration = 0"
assert s.count(anchor)==1
s=s.replace(anchor,'''    private var lastFrameNs = 0L
    private var frameSamples = 0
    private var frameMinMs = Double.POSITIVE_INFINITY
    private var frameMaxMs = 0.0
    private var frameTotalMs = 0.0
    private var frameOver50Ms = 0
    private var frameOver100Ms = 0
    private var frameBackwards = 0
    private var cadenceLogGeneration = 0''',1)
anchor='''            val type = if (cinemaVod) "VOD" else "LIVE"'''
assert s.count(anchor)==1
s=s.replace(anchor,'''            val type = if (cinemaVod) "CINEMA_POLICY" else "LIVE_POLICY"
            val avgMs = if (frameSamples > 0) frameTotalMs / frameSamples else 0.0
            Log.i("EpiMediaHubCadence",
                "intervalSamples=$frameSamples minMs=$frameMinMs avgMs=$avgMs " +
                "maxMs=$frameMaxMs gapsOver50Ms=$frameOver50Ms gapsOver100Ms=$frameOver100Ms " +
                "nonMonotonic=$frameBackwards policy=$type")
            frameSamples = 0
            frameMinMs = Double.POSITIVE_INFINITY
            frameMaxMs = 0.0
            frameTotalMs = 0.0
            frameOver50Ms = 0
            frameOver100Ms = 0
            frameBackwards = 0''',1)
# Find the actual Media3 video frame metadata callback and attach measurement there.
# Guard on expected exact anchor to prevent silently modifying a different player.
anchor='''            reportedFps = format.frameRate'''
if anchor not in s:
    raise SystemExit("Frame metadata callback anchor absent; abort")
# Instead of assuming callback shape, inject at the first assignment in metadata listener,
# where releaseTimeNs is available in onVideoFrameAboutToBeRendered.
idx=s.index(anchor)
start=s.rfind('override fun onVideoFrameAboutToBeRendered',0,idx)
if start<0: raise SystemExit("Cannot locate frame metadata callback")
brace=s.index('{',start)
snippet='''
            if (lastFrameNs > 0L) {
                val diff = (releaseTimeNs - lastFrameNs) / 1_000_000.0
                if (diff <= 0.0) frameBackwards++
                else if (diff < 1000.0) {
                    frameSamples++
                    frameMinMs = kotlin.math.min(frameMinMs, diff)
                    frameMaxMs = kotlin.math.max(frameMaxMs, diff)
                    frameTotalMs += diff
                    if (diff > 50.0) frameOver50Ms++
                    if (diff > 100.0) frameOver100Ms++
                }
            }
            lastFrameNs = releaseTimeNs
'''
s=s[:brace+1]+snippet+s[brace+1:]
p.write_text(s,encoding="utf-8")
print("Frame release cadence histogram instrumentation installed")
