#!/usr/bin/env python3
"""v1.0.52: correct short single-pilot bias, retain v151 speed/weather improvements.
Apply after patch_v151.py in pinned, isolated Android source checkout.
"""
import os,shutil
from pathlib import Path
root=Path(os.environ["PROJECT_ROOT"])
java=root/"app/src/main/java/de/epimediahub/app"
tests=root/"app/src/test/java/de/epimediahub/app"
here=Path(__file__).resolve().parent
def replace(path,old,new,count=1):
    s=path.read_text()
    assert s.count(old)==count,(str(path),s.count(old),count,old[:120])
    path.write_text(s.replace(old,new))
build=root/"app/build.gradle.kts"
replace(build,'versionCode = 1051','versionCode = 1052')
replace(build,'versionName = "1.0.51"','versionName = "1.0.52"')
shutil.copyfile(here/"V152BenchmarkPolicy.kt",java/"vpn/V152BenchmarkPolicy.kt")
shutil.copyfile(here/"V152BenchmarkPolicyTest.kt",tests/"vpn/V152BenchmarkPolicyTest.kt")
speed=java/"vpn/V140SpeedTest.kt"
# A 4MiB single-stream pilot is almost entirely connection startup on fast links.
# 8MiB + 2x8MiB + 4x32MiB <= 176MiB self-hosted download quota.
replace(speed,
    'val singleBytes = if (fixedFile || selfHosted) 4 * 1024 * 1024 else WARMUP_BYTES',
    'val singleBytes = 8 * 1024 * 1024')
replace(speed,
    'val policy = V150AdaptiveSpeed.plan(one.mbps)',
    'val policy = V152BenchmarkPolicy.plan(one.mbps, two.mbps, fixedFile)')
replace(speed,
    'policy.estimatedSeconds','policy.expectedSeconds')
# Surface actual measurement sample duration for debugging instead of promising
# the observed Mbit/s equals the subscriber's plan throughput.
replace(speed,
    'val peakMbps: Double? = null)',
    'val peakMbps: Double? = null, val sampleSeconds: Double = 0.0)')
replace(speed,
    'peakMbps = download.stability.peakMbps',
    'peakMbps = download.stability.peakMbps,\n'
    '            sampleSeconds = download.four.nanos / 1_000_000_000.0')
replace(speed,
    'Text("Ø = gesamte Nutzdaten / Messzeit; LIVE = gleitendes 1,2-s-Fenster. " +',
    'Text("Messdauer " + String.format(Locale.GERMANY, "%.1f", it.sampleSeconds) +\n'
    '                        " s • HTTPS-Ende-zu-Ende-Wert. " +\n'
    '                        "Ø = gesamte Nutzdaten / Messzeit; LIVE = gleitendes 1,2-s-Fenster. " +')
# Adjacent fixed-file ranges, not four overlapping 32MiB slices at 8MiB offsets.
gigabit=java/"vpn/V144GigabitTransfer.kt"
replace(gigabit,'url, index.toLong() * 8 * MIB, bytesPerStream,',
                'url, index.toLong() * bytesPerStream, bytesPerStream,')
# Protect unchanged VPN route checks, native player and weather header.
assert 'V134VpnSession.routeReady(context, playlistId, checkExit = false)' in speed.read_text()
assert 'V151RollingSpeed' in speed.read_text()
home=(java/"ui/V083Home.kt").read_text()
assert 'weather?.takeIf { !compact || isTv }?.let {' in home
assert 'V149QuickMenu(' in home
print("v1.0.52: real 2-stream pilot, 4-stream benchmark on home links, bounded data, measured duration; TV weather preserved.")
