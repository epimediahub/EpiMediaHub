#!/usr/bin/env python3
"""Private v167: no forced display changes, per-series history, fail-closed VPN."""
import os,shutil
from pathlib import Path
root=Path(os.environ['PROJECT_ROOT'])
here=Path(__file__).resolve().parent
java=root/'app/src/main/java/de/epimediahub/app'
tests=root/'app/src/test/java/de/epimediahub/app'
def replace(path,old,new):
    content=path.read_text()
    if content.count(old)!=1: raise SystemExit(f'v167 incompatible source: {path}: {old[:100]}')
    path.write_text(content.replace(old,new,1))
gradle=root/'app/build.gradle.kts'
replace(gradle,'versionCode = 1066','versionCode = 1067')
replace(gradle,'versionName = "1.0.66"','versionName = "1.0.67"')
shutil.copyfile(here/'V167HistoryIdentity.kt',java/'data/V167HistoryIdentity.kt')
shutil.copyfile(here/'V167HistoryIdentityTest.kt',tests/'data/V167HistoryIdentityTest.kt')
prefs=java/'data/PrefsRepository.kt'
replace(prefs,'''    private fun continueIdentity(item: MediaEntry): String =
        if (item.kind == MediaKind.EPISODE && item.seriesId.isNotBlank()) "series:${item.seriesId}" else item.resumeKey''',
'''    private fun continueIdentity(item: MediaEntry): String =
        V167HistoryIdentity.key(item)''')
replace(prefs,'writeArray(collectionKey("continue", profileId),list.take(60).map(::continueJson))',
              'writeArray(collectionKey("continue", profileId),list.take(160).map(::continueJson))')
replace(prefs,'val list = loadRecentlyWatched(profileId).filterNot { it.resumeKey == item.resumeKey }.toMutableList()',
              'val list = loadRecentlyWatched(profileId).filterNot { continueIdentity(it) == continueIdentity(item) }.toMutableList()')
replace(prefs,'writeArray(collectionKey("recently_watched", profileId), list.take(80).map(::mediaJson))',
              'writeArray(collectionKey("recently_watched", profileId), list.take(200).map(::mediaJson))')
replace(prefs,'''        val scoped = decode(collectionKey("recently_watched", profileId))
        if (profileId.isBlank() || scoped.isNotEmpty()) return scoped
        return decode("recently_watched").filter { it.sourceProfileId == profileId }''',
'''        fun clean(list: List<MediaEntry>) = list.distinctBy { continueIdentity(it) }
        val scoped = clean(decode(collectionKey("recently_watched", profileId)))
        if (profileId.isBlank() || scoped.isNotEmpty()) return scoped
        return clean(decode("recently_watched").filter { it.sourceProfileId == profileId })''')
surface=java/'ui/V121VodSurface.kt'
replace(surface,'Text("TV-Bildrate an Video anpassen: " + if (enabled) "Automatisch" else "Aus",',
                'Text("Nahtlose Bildanpassung: " + if (enabled) "Automatisch" else "Aus",')
replace(surface,'Text("Beim Wechsel der Bildrate kann der Fernseher kurz schwarz werden.", color = Color.LightGray, fontSize = 12.sp)',
                'Text("Nur nahtlose Anpassungen. Kein HDMI-Moduswechsel beim Zappen.", color = Color.LightGray, fontSize = 12.sp)')
replace(surface,'''        val attributes = host.window.attributes
        attributes.preferredDisplayModeId = target.id
        host.window.attributes = attributes
        requestedMode = target.id
        Log.i("EpiMediaHubVideo", "TV cadence: $fps fps -> ${target.hz} Hz")
        return "${v122Number(target.hz)} Hz angefordert"''',
'''        // Older Fire OS cannot guarantee a seamless mode switch.
        // Never force an HDMI blackout for better frame cadence.
        return "${v122Number(current.hz)} Hz bleiben aktiv; kein nahtloser Moduswechsel verfügbar"''')
replace(surface,'Surface.CHANGE_FRAME_RATE_ALWAYS)','Surface.CHANGE_FRAME_RATE_ONLY_IF_SEAMLESS)')
replace(surface,'request = "${v122Number(fps)} fps beim System angefordert"',
                'request = "${v122Number(fps)} fps nur nahtlos angefordert"')
assert 'preferredDisplayModeId = target.id' not in surface.read_text()
assert 'CHANGE_FRAME_RATE_ALWAYS' not in surface.read_text()
monitor=java/'vpn/V140VpnLossMonitor.kt'
monitor_source=monitor.read_text()
start_marker="""    /** Called on the serialized route worker after GoBackend reports UP. */
    @Synchronized
    fun start(context: Context) {"""
end_marker="""
    fun isPinned(context: Context): Boolean {"""
assert monitor_source.count(start_marker)==1 and monitor_source.count(end_marker)==1
begin=monitor_source.index(start_marker)
end=monitor_source.index(end_marker,begin)
old=monitor_source[begin:end]
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
monitor.write_text(monitor_source[:begin]+replacement+monitor_source[end:])
assert 'SystemClock.elapsedRealtime() + 10_000' in monitor.read_text()
print('PRIVATE v167: series history, seamless video, strict VPN ready')
