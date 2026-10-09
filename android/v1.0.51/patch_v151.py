#!/usr/bin/env python3
"""v1.0.51: restore TV weather/location and correct speedtest gauge/timing.
Apply after v1.0.50; abort on any unknown source layout.
"""
import os
import shutil
from pathlib import Path
root = Path(os.environ["PROJECT_ROOT"])
java = root/"app/src/main/java/de/epimediahub/app"
tests = root/"app/src/test/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace(path, old, new, count=1):
    source = path.read_text()
    found = source.count(old)
    assert found == count, (str(path),found,count,old[:100])
    path.write_text(source.replace(old,new))

build = root/"app/build.gradle.kts"
replace(build,'versionCode = 1050','versionCode = 1051')
replace(build,'versionName = "1.0.50"','versionName = "1.0.51"')

home = java/"ui/V083Home.kt"
s = home.read_text()
start = s.index("\n@Composable\nprivate fun V083Header(")
end = s.index("\nprivate fun V083WeatherIcon(",start)
header = s[start:end]
old_weather = '                if (!isTv) weather?.takeIf { !compact || isTv }?.let {'
old_missing = '                if (!isTv && weather == null) {'
assert header.count(old_weather)==1
assert header.count(old_missing)==1
header = header.replace(old_weather,
    '                weather?.takeIf { !compact || isTv }?.let {',1)
header = header.replace(old_missing,'                if (weather == null) {',1)
anchor1 = '        // Fixed to the RIGHT of the centered clock and below playlist metadata.'
anchor2 = '        Box(\n            Modifier.align(Alignment.BottomCenter)\n                .fillMaxWidth()'
assert header.count(anchor1)==1 and header.count(anchor2)==1
a = header.index(anchor1)
b = header.index(anchor2,a)
header = header[:a]+header[b:]
header = header.replace('"Wetterstandort in Einstellungen auswählen"',
    '"Wetter & Ort einrichten"')
assert 'V083WeatherIcon(' in header
assert 'if (weather == null)' in header
s = s[:start]+header+s[end:]
assert '.padding(top = headerHeight + if (isTv) 2.dp else 0.dp)' in s
home.write_text(s)

shutil.copyfile(here/"V151RollingSpeed.kt", java/"vpn/V151RollingSpeed.kt")
speed=java/"vpn/V140SpeedTest.kt"
replace(speed,
    '            val stability = V150AdaptiveSpeed.Stability()\n',
    '            val stability = V150AdaptiveSpeed.Stability()\n'
    '            val downloadRate = V151RollingSpeed()\n')
replace(speed,
    '                    live(Live(Phase.DOWNLOAD, sample.mbps,\n',
    '                    live(Live(Phase.DOWNLOAD, downloadRate.rate(sample) ?: sample.mbps,\n')
replace(speed,
    '        val up: V140SpeedTransfer.Sample? = try {\n',
    '        val uploadRate = V151RollingSpeed()\n'
    '        val up: V140SpeedTransfer.Sample? = try {\n')
replace(speed,
    '                    live(Live(Phase.UPLOAD, sample.mbps,\n',
    '                    live(Live(Phase.UPLOAD, uploadRate.rate(sample) ?: sample.mbps,\n')
replace(speed,
    'else if (stage == V140SpeedTest.Phase.DONE) "LETZTE MESSUNG"',
    'else if (stage == V140SpeedTest.Phase.DONE) "Ø DOWNLOAD"')
replace(speed,
    '                    Text("AUSGANG  ${it.route}   •   IP  ${it.ip}",',
    '''                    Text("Ø = gesamte Nutzdaten / Messzeit; LIVE = gleitendes 1,2-s-Fenster. " +
                        "Die Spitze ist nicht die durchschnittliche Bandbreite.",
                        color = Color(0xFFB3C4D9), fontSize = if (isTv) 13.sp else 12.sp)
                    Text("AUSGANG  ${it.route}   •   IP  ${it.ip}",''')

gigabit=java/"vpn/V144GigabitTransfer.kt"
replace(gigabit,
    '        val started = System.nanoTime()\n',
    '        val started = AtomicLong(0L)\n'
    '        val finishedBytesAt = AtomicLong(0L)\n')
replace(gigabit,
    '                        totals.set(index, snapshot.bytes)\n'
    '                        val now = System.nanoTime()\n',
    '                        totals.set(index, snapshot.bytes)\n'
    '                        val now = System.nanoTime()\n'
    '                        if ((0 until streams).sumOf { totals.get(it) } ==\n'
    '                            bytesPerStream.toLong() * streams) {\n'
    '                            finishedBytesAt.compareAndSet(0L, now)\n'
    '                        }\n')
replace(gigabit,
    'onSample(V140SpeedTransfer.Sample(count, now - started))',
    'onSample(V140SpeedTransfer.Sample(count, now - started.get()))')
replace(gigabit,
    '            go.countDown()\n            val deadline = System.nanoTime()',
    '            started.set(System.nanoTime())\n            go.countDown()\n            val deadline = System.nanoTime()')
replace(gigabit,
    '            val elapsed = (System.nanoTime() - started).coerceAtLeast(1L)',
    '            val completedAt = finishedBytesAt.get()\n'
    '            check(completedAt > started.get()) { "Transferabschluss nicht erfasst" }\n'
    '            val elapsed = (completedAt - started.get()).coerceAtLeast(1L)')
assert 'val final = V140SpeedTransfer.Sample(received, elapsed)' in gigabit.read_text()

# Measure upload bytes before HTTP response overhead; a non-2xx response
# still invalidates the result in uploadLive and must not be reported.
transfer = java/"vpn/V140SpeedTransfer.kt"
replace(transfer,
    '            }\n            routeGuard.force()\n            val responseCode = conn.responseCode\n',
    '            }\n            onSample(Sample(bytes.toLong(), System.nanoTime() - started))\n'
    '            routeGuard.force()\n            val responseCode = conn.responseCode\n')
replace(transfer,
    '            onSample(Sample(bytes.toLong(), System.nanoTime() - started))\n'
    '            bytes.toLong()\n        }\n}',
    '            bytes.toLong()\n        }\n}')

shutil.copyfile(here/"V151RollingSpeedTest.kt",
                tests/"vpn/V151RollingSpeedTest.kt")
print("v1.0.51: weather/location restored and speedtest timer, rolling gauge corrected.")
