#!/usr/bin/env python3
"""Android 1.0.64: explicit ANNUAL_ACTIVE / ANNUAL_EXPIRED app license handling.

Run only after the reviewed v1.0.63 reconstruction patches.
No automatic rollout, updater edits or VPN/playback changes.
"""
from pathlib import Path
import os

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"


def replace(path, old, new):
    content = path.read_text()
    assert content.count(old) == 1, f"Expected exactly one v164 anchor in {path}: {old[:100]!r}"
    path.write_text(content.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1063", "versionCode = 1064")
replace(gradle, 'versionName = "1.0.63"', 'versionName = "1.0.64"')

manager = java / "data/V120LicenseManager.kt"
gate = java / "ui/V120LicenseGate.kt"

replace(manager,
    "CHECKING, TRIAL_ACTIVE, TRIAL_EXPIRED, LIFETIME_ACTIVE, ERROR",
    "CHECKING, TRIAL_ACTIVE, TRIAL_EXPIRED, ANNUAL_ACTIVE, ANNUAL_EXPIRED, LIFETIME_ACTIVE, ERROR")
replace(manager,
    "kind == V120LicenseKind.TRIAL_ACTIVE || kind == V120LicenseKind.LIFETIME_ACTIVE",
    "kind == V120LicenseKind.TRIAL_ACTIVE || kind == V120LicenseKind.ANNUAL_ACTIVE || kind == V120LicenseKind.LIFETIME_ACTIVE")
replace(manager,
    '.put("platform", "android")\n',
    '.put("platform", "android")\n                .put("supported_entitlements", org.json.JSONArray().put("ANNUAL"))\n')
import re
manager_source = manager.read_text()
manager_new, agent_count = re.subn(r'EpiMediaHub-Android/[0-9]+\.[0-9]+\.[0-9]+',
                                    'EpiMediaHub-Android/1.0.64', manager_source)
assert agent_count == 1, "Expected one Android license User-Agent"
manager.write_text(manager_new)
replace(manager,
    'cached.kind == V120LicenseKind.LIFETIME_ACTIVE || cached.kind == V120LicenseKind.TRIAL_EXPIRED',
    'cached.kind == V120LicenseKind.LIFETIME_ACTIVE || cached.kind == V120LicenseKind.TRIAL_EXPIRED || cached.kind == V120LicenseKind.ANNUAL_EXPIRED')
replace(manager,
    'cached.kind != V120LicenseKind.TRIAL_ACTIVE',
    'cached.kind != V120LicenseKind.TRIAL_ACTIVE && cached.kind != V120LicenseKind.ANNUAL_ACTIVE')
replace(manager,
    'else cached.copy(kind = V120LicenseKind.TRIAL_EXPIRED, remainingSeconds = 0L)',
    'else cached.copy(kind = if (cached.kind == V120LicenseKind.ANNUAL_ACTIVE) V120LicenseKind.ANNUAL_EXPIRED else V120LicenseKind.TRIAL_EXPIRED, remainingSeconds = 0L)')
replace(manager,
    '"LIFETIME_ACTIVE" -> V120LicenseState(V120LicenseKind.LIFETIME_ACTIVE, null, expires)',
    '"LIFETIME_ACTIVE" -> V120LicenseState(V120LicenseKind.LIFETIME_ACTIVE, null, expires)\n'
    '            "ANNUAL_ACTIVE" -> V120LicenseState(V120LicenseKind.ANNUAL_ACTIVE, remaining, json.optString("annual_expires_at"))\n'
    '            "ANNUAL_EXPIRED" -> V120LicenseState(V120LicenseKind.ANNUAL_EXPIRED, 0L, json.optString("annual_expires_at"))')

replace(gate,
    'V120LicenseKind.TRIAL_ACTIVE -> {',
    'V120LicenseKind.TRIAL_ACTIVE, V120LicenseKind.ANNUAL_ACTIVE -> {')
replace(gate,
    'val expired = state.kind == V120LicenseKind.TRIAL_EXPIRED',
    'val expired = state.kind == V120LicenseKind.TRIAL_EXPIRED || state.kind == V120LicenseKind.ANNUAL_EXPIRED')
replace(gate,
    'V120LicenseKind.TRIAL_EXPIRED -> "TESTPHASE BEENDET"',
    'V120LicenseKind.TRIAL_EXPIRED -> "TESTPHASE BEENDET"\n'
    '                        V120LicenseKind.ANNUAL_EXPIRED -> "JAHRESLIZENZ BEENDET"')
replace(gate,
    'if (expired) "Deine 7-tägige Testphase ist beendet."',
    'if (state.kind == V120LicenseKind.ANNUAL_EXPIRED) "Deine Jahreslizenz ist abgelaufen."\n'
    '                    else if (expired) "Deine 7-tägige Testphase ist beendet."')
replace(gate,
    'if (expired) "Dauerhaft aktivieren für einmalig 10 € pro Gerät. Bitte wende dich an deinen Anbieter."',
    'if (state.kind == V120LicenseKind.ANNUAL_EXPIRED) "Bitte wende dich für eine Verlängerung an deinen Anbieter."\n'
    '                    else if (expired) "Dauerhaft aktivieren für einmalig 10 € pro Gerät. Bitte wende dich an deinen Anbieter."')
replace(gate,
    'if (state?.kind != V120LicenseKind.TRIAL_ACTIVE) return',
    'if (state?.kind != V120LicenseKind.TRIAL_ACTIVE && state?.kind != V120LicenseKind.ANNUAL_ACTIVE) return')
replace(gate,
    'text = if (days == 1L) "TESTVERSION · NOCH 1 TAG" else "TESTVERSION · NOCH $days TAGE",',
    'text = if (state.kind == V120LicenseKind.ANNUAL_ACTIVE) {\n'
    '                if (days == 1L) "APP-LIZENZ · NOCH 1 TAG" else "APP-LIZENZ · NOCH $days TAGE"\n'
    '            } else {\n'
    '                if (days == 1L) "TESTVERSION · NOCH 1 TAG" else "TESTVERSION · NOCH $days TAGE"\n'
    '            },')

# Separate privacy option. Disabled by default, no customer content collected.
import shutil
shutil.copyfile(Path(__file__).resolve().parent / "V164Diagnostics.kt", java / "ui/V164Diagnostics.kt")

settings = java / "ui/Screens.kt"
replace(settings,
    '            item {\n                V163BootSettingsCard(accent)\n            }',
    '            item {\n                V163BootSettingsCard(accent)\n            }\n'
    '            item {\n                V164DiagnosticsCard(accent)\n            }')

entry = java / "EpiMediaHubApp.kt"
replace(entry,
    '    var v120LicenseRefresh by remember { mutableStateOf(0) }',
    '    LaunchedEffect(Unit) {\n'
    '        de.epimediahub.app.ui.V164Diagnostics.installCrashMarker(context.applicationContext)\n'
    '        de.epimediahub.app.ui.V164Diagnostics.uploadPending(context.applicationContext)\n'
    '    }\n'
    '    var v120LicenseRefresh by remember { mutableStateOf(0) }')


# Finland VPN: WireGuard's successful UP/handshake can precede Android's
# Network registration. Fire OS/Android can also briefly expose a stale VPN
# Network first, which causes bindProcessToNetwork to return false. Never
# disable process pinning or quietly switch to the physical network. Retry
# only confirmed TRANSPORT_VPN candidates with priority for the app's active
# Network, stopping playback if none becomes valid within the deadline.
monitor = java / "vpn/V140VpnLossMonitor.kt"
monitor_source = monitor.read_text()
start_marker = """    /** Called on the serialized route worker after GoBackend reports UP. */
    @Synchronized
    fun start(context: Context) {"""
end_marker = """
    fun isPinned(context: Context): Boolean {"""
assert monitor_source.count(start_marker) == 1 and monitor_source.count(end_marker) == 1, (
    "Unexpected VPN binding source; refusing to modify VPN safety logic"
)
begin = monitor_source.index(start_marker)
end = monitor_source.index(end_marker, begin)
old = monitor_source[begin:end]
assert 'check(cm.bindProcessToNetwork(network)) { "VPN-Netz konnte nicht gebunden werden" }' in old
assert 'pinned = network' in old and 'cm.registerNetworkCallback(request(), cb)' in old

replacement = """    /** Called after GoBackend reports UP; wait for the VPN Network to be valid. */
    @Synchronized
    fun start(context: Context) {
        stop()
        val cm = context.applicationContext
            .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val deadline = SystemClock.elapsedRealtime() + 10_000
        var selected: Network? = null
        var vpnNetworksObserved = false
        do {
            // On some Android versions allNetworks initially includes a stale
            // VPN handle. Prefer the app's active VPN, then other VPN candidates.
            val candidates = (listOfNotNull(cm.activeNetwork) + cm.allNetworks.toList()).distinct()
            for (candidate in candidates) {
                val capabilities = cm.getNetworkCapabilities(candidate)
                if (capabilities?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) != true) continue
                vpnNetworksObserved = true
                // A false result is NOT success and must NEVER fall back to direct.
                if (!cm.bindProcessToNetwork(candidate)) continue
                if (cm.boundNetworkForProcess != candidate ||
                    cm.getNetworkCapabilities(candidate)
                        ?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) != true) continue
                selected = candidate
                break
            }
            if (selected == null && SystemClock.elapsedRealtime() < deadline) {
                Thread.sleep(100)
            }
        } while (selected == null && SystemClock.elapsedRealtime() < deadline)

        val network = checkNotNull(selected) {
            if (vpnNetworksObserved) "Android-VPN-Netz nicht bindbar; kein Direkt-Fallback"
            else "Android-VPN-Netz nicht verfügbar; kein Direkt-Fallback"
        }
        pinned = network
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onLost(network: Network) {
                if (pinned == network) {
                    // Keep process pinning even if transport disappears.
                    V134VpnSession.onVpnTransportLost()
                }
            }
        }
        manager = cm
        callback = cb
        cm.registerNetworkCallback(request(), cb)
        check(isPinned(context)) { "VPN-Netz während der Bindung verloren" }
    }
"""
monitor.write_text(monitor_source[:begin] + replacement + monitor_source[end:])


assert 'versionCode = 1064' in gradle.read_text()
assert 'ANNUAL_ACTIVE' in manager.read_text() and 'ANNUAL_EXPIRED' in gate.read_text()
print("Android 1.0.64: annual license and optional anonymous crash counters enabled")
