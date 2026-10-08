package de.epimediahub.app.vpn

import android.content.Context
import android.net.VpnService
import java.net.HttpURLConnection
import java.net.URL

/**
 * BETA ONLY. Serialized route changes; profile held in process memory, never
 * persisted or logged. Uses a dedicated, per-device WireGuard test peer.
 */
internal object V134VpnSession {
    enum class Route { BLOCKED, DIRECT, FINLAND }
    @Volatile private var route = Route.BLOCKED
    @Volatile private var profile: String? = null
    @Volatile private var tunnel: V134WireGuardDeviceTunnel? = null
    private const val FINLAND_IP = "37.27.42.215"

    @Synchronized private fun tunnel(context: Context): V134WireGuardDeviceTunnel {
        if (tunnel == null) tunnel = V134WireGuardDeviceTunnel(context.applicationContext)
        return requireNotNull(tunnel)
    }

    fun storeProfile(value: String) {
        profile = value
        route = Route.BLOCKED
    }

    fun mode(context: Context, playlistId: String): Boolean =
        context.getSharedPreferences("vpn-beta-routing", Context.MODE_PRIVATE)
            .getBoolean("vpn_$playlistId", false)

    fun setMode(context: Context, playlistId: String, enabled: Boolean) {
        context.getSharedPreferences("vpn-beta-routing", Context.MODE_PRIVATE)
            .edit().putBoolean("vpn_$playlistId", enabled).apply()
        route = Route.BLOCKED
    }

    @Synchronized
    fun routeReady(context: Context, playlistId: String): Boolean {
        val actual = tunnel(context).isUp()
        return if (mode(context, playlistId))
            route == Route.FINLAND && actual
        else route == Route.DIRECT && !actual
    }

    fun block() { route = Route.BLOCKED }

    /** Called in a worker thread. Never change playlist until this returns true. */
    @Synchronized
    fun connectAndVerify(context: Context): String {
        route = Route.BLOCKED
        val cfg = profile ?: error("Bitte Finnland-Profil neu importieren")
        check(VpnService.prepare(context) == null) { "VPN-Einwilligung fehlt" }
        check(tunnel(context).connect(cfg)) { "WireGuard konnte nicht verbunden werden" }
        return try {
            val ip = publicIpv4()
            check(ip == FINLAND_IP) { "Finnland-Ausgang nicht bestätigt" }
            route = Route.FINLAND
            ip
        } catch (error: Exception) {
            runCatching { tunnel(context).disconnect() }
            route = Route.BLOCKED
            throw error
        }
    }

    @Synchronized
    fun disconnectAndVerify(context: Context): String {
        route = Route.BLOCKED
        check(tunnel(context).disconnect()) { "VPN konnte nicht getrennt werden" }
        check(!tunnel(context).isUp()) { "VPN noch verbunden" }
        val ip = publicIpv4()
        check(ip != FINLAND_IP) { "Direktverbindung nicht bestätigt" }
        route = Route.DIRECT
        return ip
    }

    fun publicIpv4(): String {
        val conn = URL("https://api.ipify.org").openConnection() as HttpURLConnection
        return try {
            conn.connectTimeout = 10_000
            conn.readTimeout = 10_000
            conn.useCaches = false
            conn.setRequestProperty("Cache-Control", "no-cache")
            conn.inputStream.bufferedReader().use { it.readText().trim() }.also {
                require(it.matches(Regex("(?:\\d{1,3}\\.){3}\\d{1,3}")))
            }
        } finally { conn.disconnect() }
    }

    @Synchronized
    fun routeTo(context: Context, playlistId: String): Boolean {
        return runCatching {
            if (mode(context, playlistId)) connectAndVerify(context)
            else disconnectAndVerify(context)
            routeReady(context, playlistId)
        }.getOrElse { route = Route.BLOCKED; false }
    }
}
