#!/usr/bin/env python3
"""v1.0.50: keep weather visible, TV D-pad recovery, adaptive honest speedtest.
Apply AFTER patch_v149.py, never modify installed v1.0.49 artifacts.
"""
import os, shutil
from pathlib import Path
root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace(path, old, new, count=1):
    s=path.read_text()
    found=s.count(old)
    assert found == count, (str(path),found,count,old[:150])
    path.write_text(s.replace(old,new))

build=root/"app/build.gradle.kts"
replace(build,'versionCode = 1049','versionCode = 1050')
replace(build,'versionName = "1.0.49"','versionName = "1.0.50"')
shutil.copyfile(here/"V150AdaptiveSpeed.kt",java/"vpn/V150AdaptiveSpeed.kt")

home=java/"ui/V083Home.kt"
# Reserve a real horizontal row BELOW the 176dp TV header. The closed menu
# neither obscures the weather nor the centered clock; only the open panel
# temporarily overlays the tiles.
replace(home,
'''        Column(Modifier.fillMaxSize()) {
            V083Header(''',
'''        Column(Modifier.fillMaxSize()) {
            V083Header(''')
# Exactly one insertion after the header invocation, before the tile frame.
hs=home.read_text()
start=hs.index('    BoxWithConstraints(Modifier.fillMaxSize()) {')
end=hs.index('\n@Composable\nprivate fun V083Header(',start)
panel=hs[start:end]
p=panel.index('            Box(\n                Modifier.weight(1f).fillMaxWidth().padding(')
panel=panel[:p]+'''            if (isTv) Spacer(Modifier.height(36.dp))
'''+panel[p:]
assert panel.count('            if (isTv) Spacer(Modifier.height(36.dp))') == 1
panel=panel.replace(
    'Box(Modifier.align(Alignment.TopCenter).zIndex(10f)) {',
    'Box(Modifier.align(Alignment.TopCenter)\n' +
    '            .padding(top = headerHeight + if (isTv) 2.dp else 0.dp)\n' +
    '            .zIndex(10f)) {')
assert 'padding(top = headerHeight + if (isTv) 2.dp else 0.dp)' in panel
hs=hs[:start]+panel+hs[end:]
home.write_text(hs)

# Do not show the full weather string immediately above the centered clock:
# it was covered by the old top-center quick-menu trigger.
s=home.read_text()
start=s.index('private fun V083Header(')
end=s.index('\nprivate fun V083WeatherIcon(',start)
h=s[start:end]
weather_variants = (
    '                weather?.takeIf { !compact || isTv }?.let {',
    '                weather?.let {',
)
matches=[line for line in weather_variants if h.count(line)==1]
assert len(matches)==1, 'Expected exactly one weather block in built header'
h=h.replace(matches[0], matches[0].replace('weather?', 'if (!isTv) weather?', 1), 1)
assert h.count('                if (weather == null) {')==1
h=h.replace('                if (weather == null) {','                if (!isTv && weather == null) {',1)
anchor='''        Box(
            Modifier.align(Alignment.BottomCenter)
                .fillMaxWidth()'''
assert h.count(anchor)==1
weather_ui='''        // Fixed to the RIGHT of the centered clock and below playlist metadata.
        // Short text only; full details are in Wetter & Ort / Einstellungen.
        if (isTv) {
            val location = weather?.city?.takeIf { it.isNotBlank() } ?: "Standort wählen"
            val summary = weather?.let {
                "\${V083WeatherIcon(it.code, isNight)}  $location · \${it.temperatureC}°C"
            } ?: if (de.epimediahub.app.data.V070WeatherClient.postalCode(context).isBlank())
                "☁  Wetter & Ort einrichten" else "☁  Wetter nicht verfügbar"
            Text(
                summary,
                modifier = Modifier.align(Alignment.CenterEnd).width(245.dp)
                    .padding(top = 52.dp).testTag("home-weather-right"),
                color = Color.White.copy(alpha = .93f),
                fontSize = 13.sp,
                fontWeight = FontWeight.Bold,
                textAlign = androidx.compose.ui.text.style.TextAlign.End,
                maxLines = 1
            )
        }

'''
# JS String.raw above preserves \${...} as literal backslash—remove it for Kotlin.
weather_ui=weather_ui.replace("\\$", "$")
h=h.replace(anchor,weather_ui+anchor,1)
home.write_text(s[:start]+h+s[end:])

# Settings overlay was the last focusable widget; pressing D-pad Up was trapped.
vpn=java/"vpn/V141VpnSettings.kt"
replace(vpn,'import androidx.compose.ui.focus.onFocusChanged',
'''import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.focus.FocusDirection
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.key
import androidx.compose.ui.input.key.type
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.platform.testTag''')
replace(vpn,
'''    var open by remember { mutableStateOf(false) }
    if (open) {''',
'''    var open by remember { mutableStateOf(false) }
    val settingsFocusManager = LocalFocusManager.current
    if (open) {''')
replace(vpn,
'''                    accent = accent,
                    onClick = { open = true }
                )''',
'''                    accent = accent,
                    onClick = { open = true },
                    modifier = Modifier.testTag("vpn-settings-entry")
                        .onPreviewKeyEvent { event ->
                            if (event.type == KeyEventType.KeyDown &&
                                event.key == Key.DirectionUp) {
                                // Settings controls were composed BEFORE the overlay.
                                // Previous navigates back into those settings controls.
                                settingsFocusManager.moveFocus(FocusDirection.Previous)
                            } else false
                        }
                )''')
replace(vpn,
'''    BackHandler { onBack() }
    Column(''',
'''    BackHandler { onBack() }
    val vpnBackFocus = remember { FocusRequester() }
    Column(''')
replace(vpn,
'''        Text("EINSTELLUNGEN · VPN & NETZWERK",''',
'''        V141FocusButton("← Zurück zu Einstellungen", accent, onClick = onBack,
            modifier = Modifier.focusRequester(vpnBackFocus).testTag("vpn-top-back"))
        Text("EINSTELLUNGEN · VPN & NETZWERK",''')
replace(vpn,
'''        }, enabled = !busy)
        V141FocusButton("VPN trennen · Direktverbindung",''',
'''        }, modifier = Modifier.focusProperties { up = vpnBackFocus }
                .testTag("vpn-connect"), enabled = !busy)
        V141FocusButton("VPN trennen · Direktverbindung",''')

# Retain existing VPN route checks, server fallback, cancellation semantics.
speed=java/"vpn/V140SpeedTest.kt"
replace(speed,'''        val provider: String
    )''',
'''        val provider: String,
        val activeStreams: Int,
        val stability: V150AdaptiveSpeed.Report
    )''')
replace(speed,'''        val downloadProvider: String = "EpiMediaHub", val partial: Boolean = false)''',
'''        val downloadProvider: String = "EpiMediaHub", val partial: Boolean = false,
        val activeStreams: Int = 4, val stabilityPercent: Int? = null,
        val peakMbps: Double? = null)''')
replace(speed,
'''            val fourEach = if (fixedFile) 8 * 1024 * 1024
                else if (selfHosted) V144GigabitTransfer.downloadBytesPerStream(one.mbps)
                    .coerceAtMost(32 * 1024 * 1024)
                else V144GigabitTransfer.downloadBytesPerStream(one.mbps)
            val total = fourEach.toLong() * 4L''',
'''            val policy = V150AdaptiveSpeed.plan(one.mbps)
            val fourEach = policy.bytesPerStream
            val activeStreams = policy.streams
            val total = fourEach.toLong() * activeStreams
            val stability = V150AdaptiveSpeed.Stability()
            progress("Adaptive Messung: $activeStreams Streams, " +
                "\${fourEach / (1024 * 1024)} MiB/Stream" +
                " · ca. \${"%.1f".format(java.util.Locale.US, policy.estimatedSeconds)} s")'''.replace("\\$","$"))
replace(speed,
'''            progress("Download: 4 parallele HTTPS-Verbindungen ($provider) …")
            val four = V144GigabitTransfer.measureWithStreams(
                transfer, source, fourEach, false, verify, 4, { sample ->
                    live(Live(Phase.DOWNLOAD, sample.mbps,
                        (sample.bytes.toDouble() / total).toFloat().coerceIn(0f, 1f)))
                }, fixedFile, if (selfHosted) ownSession else null
            )
            return DownPlan(latency, one, two, four, provider)''',
'''            progress("Download: $activeStreams adaptive HTTPS-Verbindungen ($provider) …")
            val four = V144GigabitTransfer.measureWithStreams(
                transfer, source, fourEach, false, verify, activeStreams, { sample ->
                    stability.record(sample)
                    live(Live(Phase.DOWNLOAD, sample.mbps,
                        (sample.bytes.toDouble() / total).toFloat().coerceIn(0f, 1f)))
                }, fixedFile, if (selfHosted) ownSession else null
            )
            return DownPlan(latency, one, two, four, provider,
                activeStreams, stability.report())''')
replace(speed,
'''            download.one.mbps, download.two.mbps, download.provider,
            partial = up == null''',
'''            download.one.mbps, download.two.mbps, download.provider,
            partial = up == null,
            activeStreams = download.activeStreams,
            stabilityPercent = download.stability.variationPercent,
            peakMbps = download.stability.peakMbps''')
replace(speed,
'''                                 ?: "GIGABIT-MESSUNG • 4 Streams • dynamisches Datenvolumen",''',
'''                                 ?: "ADAPTIVER SPEEDTEST • automatische Leitungsanpassung",''')
replace(speed,
'''                            "  |  4 Streams: " +
                            String.format(Locale.GERMANY, "%.1f", it.downloadMbps)''',
'''                            "  |  \${it.activeStreams} Streams: " +
                            String.format(Locale.GERMANY, "%.1f", it.downloadMbps)'''.replace("\\$","$"))
replace(speed,
'''                     Text("AUSGANG  \${it.route}   •   IP  \${it.ip}",'''.replace("\\$","$"),
'''                     Text(
                         "STABILITÄT  " + (it.stabilityPercent?.let { variation ->
                             "Schwankung ca. $variation %" } ?: "zu wenig Messpunkte") +
                             (it.peakMbps?.let { peak ->
                                 "  •  Spitze \${String.format(Locale.GERMANY,"%.1f", peak)} Mbit/s"
                             } ?: ""),
                         color = Color(0xFFB3C4D9),
                         fontSize = if (isTv) 13.sp else 12.sp
                     )
                     Text("AUSGANG  \${it.route}   •   IP  \${it.ip}",'''.replace("\\$","$"))
replace(speed,
'''            "4 Streams plus 1-/2-Stream-Vergleich, begrenztes Testvolumen. " +''',
'''            "Automatisch angepasste Testmenge und 2–4 Streams, begrenztes Testvolumen. " +''')
# TV overscan: ensure focused action row can scroll fully onto screen.
replace(speed,
'''            .padding(horizontal = if (isTv) 48.dp else 18.dp,
                vertical = if (isTv) 20.dp else 14.dp)''',
'''            .padding(horizontal = if (isTv) 48.dp else 18.dp,
                vertical = if (isTv) 16.dp else 14.dp)
            .padding(bottom = if (isTv) 52.dp else 16.dp)''')

# One new deterministic CI suite for adaptive sizing and honest sample stability.
extra=tests/"vpn/V150AdaptiveSpeedTest.kt"
extra.write_text("""package de.epimediahub.app.vpn

import org.junit.Assert.*
import org.junit.Test

class V150AdaptiveSpeedTest {
    @Test fun slowLineUsesLessDataAndTwoConnections() {
        val p=V150AdaptiveSpeed.plan(10.0)
        assertEquals(2,p.streams)
        assertTrue(p.bytesPerStream <= 16*1024*1024)
    }
    @Test fun fastLineUsesFourConnectionsAndNeverExceedsServerCap() {
        val p=V150AdaptiveSpeed.plan(1000.0)
        assertEquals(4,p.streams)
        assertEquals(32*1024*1024,p.bytesPerStream)
        assertTrue(p.bytesPerStream.toLong()*p.streams <= 128L*1024*1024)
    }
    @Test fun greaterRealPilotRequiresAtLeastAsMuchTestData() {
        val slow=V150AdaptiveSpeed.plan(30.0)
        val fast=V150AdaptiveSpeed.plan(270.0)
        assertTrue(fast.bytesPerStream > slow.bytesPerStream)
    }
    @Test fun insufficientSamplesDoNotInventStability() {
        val s=V150AdaptiveSpeed.Stability()
        s.record(V140SpeedTransfer.Sample(1000,100000000))
        assertNull(s.report().variationPercent)
    }
    @Test fun stabilityUsesActualPostWarmupIntervals() {
        val s=V150AdaptiveSpeed.Stability()
        s.record(V140SpeedTransfer.Sample(1000,1000000000))
        s.record(V140SpeedTransfer.Sample(2001000,1400000000))
        s.record(V140SpeedTransfer.Sample(4001000,1800000000))
        s.record(V140SpeedTransfer.Sample(6001000,2200000000))
        assertNotNull(s.report().variationPercent)
        assertTrue(s.report().peakMbps!! > 0)
    }
}
""")
print("v1.0.50 applied: weather outside quickmenu, safe VPN focus/back, adaptive real Mbps.")
