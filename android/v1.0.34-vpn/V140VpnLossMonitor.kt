package de.epimediahub.app.vpn

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkRequest

/**
 * Defense in depth for the test app: reacts to Android's VPN transport loss,
 * immediately invalidates the app's playback authorization and NEVER grants
 * direct access. This is NOT a system-level always-on VPN lockdown / kill switch:
 * only Android's "Block connections without VPN" can enforce that below the app.
 */
internal object V140VpnLossMonitor {
    private var manager: ConnectivityManager? = null
    private var callback: ConnectivityManager.NetworkCallback? = null

    @Synchronized
    fun start(context: Context) {
        stop()
        val cm = context.applicationContext
            .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val req = NetworkRequest.Builder()
            .addTransportType(NetworkCapabilities.TRANSPORT_VPN).build()
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onLost(network: Network) {
                // Block synchronously, never switch to direct. The UI also rechecks
                // the backend state and Finnish exit and removes playback on failure.
                V134VpnSession.onVpnTransportLost()
            }
        }
        cm.registerNetworkCallback(req, cb)
        manager = cm
        callback = cb
    }

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
}
