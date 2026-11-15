#!/usr/bin/env python3
"""v1.0.52: longer calibrated multi-stream sample and explicit sustained vs full average.
Apply AFTER patch_v151.py. All source anchors are intentionally strict.
"""
import os,shutil
from pathlib import Path
root=Path(os.environ["PROJECT_ROOT"])
java=root/"app/src/main/java/de/epimediahub/app"
tests=root/"app/src/test/java/de/epimediahub/app"
here=Path(__file__).resolve().parent

def replace(path, old, new, count=1):
    source=path.read_text()
    matches=source.count(old)
    assert matches == count, (str(path),matches,count,old[:120])
    path.write_text(source.replace(old,new,count))

build=root/"app/build.gradle.kts"
replace(build,'versionCode = 1051','versionCode = 1052')
replace(build,'versionName = "1.0.51"','versionName = "1.0.52"')
shutil.copyfile(here/"V152SustainedSpeed.kt",java/"vpn/V152SustainedSpeed.kt")

speed=java/"vpn/V140SpeedTest.kt"
replace(speed,
    '        val peakMbps: Double? = null)',
    '        val peakMbps: Double? = null,\n'
    '        val sustainedMbps: Double? = null,\n'
    '        val sustainedSeconds: Double? = null)')
replace(speed,
    '        val stability: V150AdaptiveSpeed.Report\n    )',
    '        val stability: V150AdaptiveSpeed.Report,\n'
    '        val sustained: V152SustainedSpeed.Report\n    )')
# The single-connection pilot frequently underestimates a customer's
# 4-stream link and makes the final test too short to reach steady throughput.
# The 2-stream pilot is measured data; the factor only sizes test traffic.
# It is NEVER used to calculate or display throughput.
replace(speed,
    '            val policy = V150AdaptiveSpeed.plan(one.mbps)',
    '            val sizingEstimate = maxOf(one.mbps, two.mbps * 1.8)\n'
    '            val policy = V150AdaptiveSpeed.plan(sizingEstimate)')
replace(speed,
    '            val downloadRate = V151RollingSpeed()\n',
    '            val downloadRate = V151RollingSpeed()\n'
    '            val sustained = V152SustainedSpeed()\n')
replace(speed,
    '                    stability.record(sample)\n',
    '                    stability.record(sample)\n'
    '                    sustained.record(sample)\n')
replace(speed,
    '                activeStreams, stability.report())',
    '                activeStreams, stability.report(), sustained.report(four))')
replace(speed,
    '            peakMbps = download.stability.peakMbps',
    '            peakMbps = download.stability.peakMbps,\n'
    '            sustainedMbps = download.sustained.mbps,\n'
    '            sustainedSeconds = download.sustained.seconds')
replace(speed,
    'else if (stage == V140SpeedTest.Phase.DONE) "Ø DOWNLOAD"',
    'else if (stage == V140SpeedTest.Phase.DONE) "DOWNLOAD NACH ANLAUFPHASE"')
replace(speed,
    '''                                downloadResult = measured.downloadMbps''',
    '''                                downloadResult = measured.sustainedMbps ?: measured.downloadMbps''')
replace(speed,
    '''                                speed = measured.downloadMbps''',
    '''                                speed = measured.sustainedMbps ?: measured.downloadMbps''')
# The primary speed displayed in the gauge is the sustained value when
# measured for >=1sec after warm-up. The full unaltered average remains
# explicitly visible, along with peak and the test-server identity.
needle='''                    Text("Ø = gesamte Nutzdaten / Messzeit; LIVE = gleitendes 1,2-s-Fenster. " +'''
assert speed.read_text().count(needle)==1, "v151 speed diagnostic text not found"
replace(speed,needle,
'''                    Text("DOWNLOAD-ERGEBNIS: Gesamt-Ø " +
                        String.format(Locale.GERMANY, "%.1f", it.downloadMbps) + " Mbit/s" +
                        (it.sustainedMbps?.let { sustained ->
                            "  ·  Nach Anlaufphase " +
                            String.format(Locale.GERMANY, "%.1f", sustained) + " Mbit/s"
                        } ?: "  ·  Test zu kurz für einen belastbaren Dauerwert"),
                        color = Color(0xFFD5E7FC), fontWeight = FontWeight.Bold,
                        fontSize = if (isTv) 14.sp else 12.sp)
                    Text("Ø = gesamte Nutzdaten / Messzeit; LIVE = gleitendes 1,2-s-Fenster. " +''')
# Output label must remain honest when a very fast link has too few samples.
replace(speed,
    'else if (stage == V140SpeedTest.Phase.DONE) "DOWNLOAD NACH ANLAUFPHASE"',
    'else if (stage == V140SpeedTest.Phase.DONE) "DOWNLOAD-ERGEBNIS"')
# Retain the original TV header and VPN routing safety untouched.
home=(java/"ui/V083Home.kt").read_text()
assert 'weather?.takeIf { !compact || isTv }?.let {' in home
assert '.padding(top = headerHeight + if (isTv) 2.dp else 0.dp)' in home
shutil.copyfile(here/"V152SustainedSpeedTest.kt",tests/"vpn/V152SustainedSpeedTest.kt")
print("v1.0.52 installed: 2-stream sizing pilot, sustained goodput vs honest total mean.")
