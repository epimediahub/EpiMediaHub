package de.epimediahub.app.vpn

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest
import android.os.SystemClock

/**
 * Pins future app sockets and DNS to the VPN. Android retains the binding when
 * that Network is lost: new sockets and DNS fail instead of falling back to
 * Wi-Fi/mobile. Only explicit direct consent may clear it. This is process-scoped,
 * not device-wide always-on lockdown; it does not cover process death or sockets
 * explicitly bound by another library.
 */
internal object V140VpnLossMonitor {
    @Volatile private var pinned: Network? = null
    private var manager: ConnectivityManager? = null
    private var callback: ConnectivityManager.NetworkCallback? = null

    internal fun request(): NetworkRequest = NetworkRequest.Builder()
        // Builder includes NOT_VPN by default; TRANSPORT_VPN alone never matches.
        .removeCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN)
        .addTransportType(NetworkCapabilities.TRANSPORT_VPN).build()

    /** Called on the serialized route worker after GoBackend reports UP. */
    @Synchronized
    fun start(context: Context) {
        stop()
        val cm = context.applicationContext
            .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val deadline = SystemClock.elapsedRealtime() + 5_000
        var selected: Network? = null
        while (selected == null && SystemClock.elapsedRealtime() < deadline) {
            selected = cm.allNetworks.firstOrNull { network ->
                cm.getNetworkCapabilities(network)
                    ?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
            }
            if (selected == null) Thread.sleep(50)
        }
        val network = checkNotNull(selected) { "Android-VPN-Netz nicht verfügbar" }
        check(cm.bindProcessToNetwork(network)) { "VPN-Netz konnte nicht gebunden werden" }
        pinned = network
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onLost(network: Network) {
                if (pinned == network) {
                    // Do NOT unbind, even if the service/tunnel disappeared.
                    V134VpnSession.onVpnTransportLost()
                }
            }
        }
        manager = cm
        callback = cb
        cm.registerNetworkCallback(request(), cb)
        check(isPinned(context)) { "VPN-Netz während der Bindung verloren" }
    }

    fun isPinned(context: Context): Boolean {
        val network = pinned ?: return false
        val cm = context.applicationContext
            .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        return cm.boundNetworkForProcess == network &&
            cm.getNetworkCapabilities(network)
                ?.hasTransport(NetworkCapabilities.TRANSPORT_VPN) == true
    }

    /** Stop observation without releasing the protective network binding. */
    @Synchronized
    fun stop() {
        val cm = manager
        val cb = callback
        manager = null
        callback = null
        if (cm != null && cb != null) {
            runCatching { cm.unregisterNetworkCallback(cb) }
        }
    }

    /** ONLY after user chose DIRECT, confirmed fallback, or erased their profile. */
    @Synchronized
    fun releaseForExplicitDirect(context: Context) {
        stop()
        val cm = context.applicationContext
            .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        check(cm.bindProcessToNetwork(null)) { "Direktverbindung konnte nicht freigegeben werden" }
        pinned = null
    }
}
