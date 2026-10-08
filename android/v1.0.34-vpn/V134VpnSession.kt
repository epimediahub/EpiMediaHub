package de.epimediahub.app.vpn

import android.content.Context
import android.net.VpnService
import java.net.HttpURLConnection
import java.net.URL

/**
 * BETA ONLY. Serialized route changes; profile cached in memory and stored
 * only as AES-GCM ciphertext in no-backup internal storage using AndroidKeyStore.
 * Uses a dedicated, per-device WireGuard test peer.
 */
internal object V134VpnSession {
    enum class Route { BLOCKED, DIRECT, FINLAND }
    @Volatile private var route = Route.BLOCKED
    @Volatile private var profile: String? = null
    @Volatile private var tunnel: V134WireGuardDeviceTunnel? = null
    // Per-process, single-playlist opt-in only. NEVER write the override to preferences.
    @Volatile private var temporaryDirectPlaylist: String? = null
    private var lastExitCheckMs: Long = 0
    private var lastExitOk: Boolean = false
    private const val EXIT_CHECK_INTERVAL_MS = 3_000L
    private const val FINLAND_IP = "37.27.42.215"

    @Synchronized private fun tunnel(context: Context): V134WireGuardDeviceTunnel {
        if (tunnel == null) tunnel = V134WireGuardDeviceTunnel(context.applicationContext)
        return requireNotNull(tunnel)
    }

    /** Best-effort early VPN loss notification. Never authorizes DIRECT. */
    @Synchronized
    fun onVpnTransportLost() {
        if (route == Route.FINLAND) {
            route = Route.BLOCKED
            lastExitOk = false
            lastExitCheckMs = 0
        }
    }

    @Synchronized
    fun hasProfile(context: Context): Boolean =
        profile != null || V139VpnEncryptedProfileStore.exists(context)

    @Synchronized
    fun storeProfile(context: Context, value: String) {
        // Fail closed: never mark the profile imported before encryption succeeded.
        V139VpnEncryptedProfileStore.save(context, value)
        V140VpnLossMonitor.stop()
        profile = value
        route = Route.BLOCKED
        temporaryDirectPlaylist = null
        lastExitOk = false
        lastExitCheckMs = 0
    }

    @Synchronized
    fun eraseProfile(context: Context) {
        V140VpnLossMonitor.stop()
        route = Route.BLOCKED
        temporaryDirectPlaylist = null
        // Never remove the only saved connection details while leaving a tunnel up.
        if (tunnel != null) {
            check(tunnel(context).disconnect()) { "VPN-Verbindung konnte nicht beendet werden" }
            check(!tunnel(context).isUp()) { "VPN-Verbindung noch aktiv" }
        }
        V139VpnEncryptedProfileStore.erase(context)
        profile = null
        lastExitOk = false
        lastExitCheckMs = 0
    }

    fun mode(context: Context, playlistId: String): Boolean =
        context.getSharedPreferences("vpn-beta-routing", Context.MODE_PRIVATE)
            .getBoolean("vpn_$playlistId", false)

    @Synchronized
    fun setMode(context: Context, playlistId: String, enabled: Boolean) {
        // A fresh user selection always cancels any temporary direct exception.
        temporaryDirectPlaylist = null
        route = Route.BLOCKED
        context.getSharedPreferences("vpn-beta-routing", Context.MODE_PRIVATE)
            .edit().putBoolean("vpn_$playlistId", enabled).apply()
    }

    @Synchronized
    fun routeReady(context: Context, playlistId: String): Boolean {
        val actual = tunnel(context).isUp()
        if (mode(context, playlistId) && temporaryDirectPlaylist == playlistId) {
            return route == Route.DIRECT && !actual
        }
        if (!mode(context, playlistId)) return route == Route.DIRECT && !actual
        if (route != Route.FINLAND || !actual) {
            route = Route.BLOCKED
            lastExitOk = false
            return false
        }
        // A tunnel reporting UP is not proof of a working Finnish exit. Probe at
        // bounded intervals while playing; on failed proof remove the player UI.
        val now = android.os.SystemClock.elapsedRealtime()
        if (now - lastExitCheckMs >= EXIT_CHECK_INTERVAL_MS || lastExitCheckMs == 0L) {
            lastExitCheckMs = now
            lastExitOk = runCatching { publicIpv4() == FINLAND_IP }.getOrDefault(false)
        }
        if (!lastExitOk) route = Route.BLOCKED
        return route == Route.FINLAND && actual && lastExitOk
    }

    fun needsDirectFallbackPrompt(context: Context, playlistId: String): Boolean =
        mode(context, playlistId) && temporaryDirectPlaylist != playlistId

    /**
     * Called ONLY after the user confirms the explicit privacy warning.
     * Disconnects WireGuard, verifies the direct exit, then grants THIS playlist
     * temporary direct access. The saved VPN playlist preference is unchanged.
     */
    @Synchronized
    fun allowDirectOnce(context: Context, playlistId: String): Boolean {
        if (!mode(context, playlistId)) return false
        V140VpnLossMonitor.stop()
        temporaryDirectPlaylist = null
        route = Route.BLOCKED
        return runCatching {
            check(tunnel(context).disconnect()) { "VPN konnte nicht getrennt werden" }
            check(!tunnel(context).isUp()) { "VPN weiterhin verbunden" }
            val directIp = publicIpv4()
            check(directIp != FINLAND_IP) { "Direktausgang nicht bestätigt" }
            route = Route.DIRECT
            temporaryDirectPlaylist = playlistId
            true
        }.getOrElse {
            route = Route.BLOCKED
            temporaryDirectPlaylist = null
            false
        }
    }

    @Synchronized
    fun block() {
        route = Route.BLOCKED
        temporaryDirectPlaylist = null
        lastExitOk = false
        lastExitCheckMs = 0
    }

    /** Called in a worker thread. Never change playlist until this returns true. */
    @Synchronized
    fun connectAndVerify(context: Context): String {
        V140VpnLossMonitor.stop()
        route = Route.BLOCKED
        temporaryDirectPlaylist = null
        lastExitOk = false
        lastExitCheckMs = 0
        val cfg = profile
            ?: V139VpnEncryptedProfileStore.load(context)?.also { profile = it }
            ?: error("Bitte Finnland-Profil importieren")
        check(VpnService.prepare(context) == null) { "VPN-Einwilligung fehlt" }
        check(tunnel(context).connect(cfg)) { "WireGuard konnte nicht verbunden werden" }
        return try {
            val ip = publicIpv4()
            check(ip == FINLAND_IP) { "Finnland-Ausgang nicht bestätigt" }
            route = Route.FINLAND
            // Additional rapid Android VPN network-loss signal. Failure to register
            // does not turn on DIRECT; the 750ms UI + exit-IP checks remain.
            runCatching { V140VpnLossMonitor.start(context) }
            lastExitOk = true
            lastExitCheckMs = android.os.SystemClock.elapsedRealtime()
            ip
        } catch (error: Exception) {
            V140VpnLossMonitor.stop()
            runCatching { tunnel(context).disconnect() }
            route = Route.BLOCKED
            throw error
        }
    }

    @Synchronized
    fun disconnectAndVerify(context: Context): String {
        V140VpnLossMonitor.stop()
        route = Route.BLOCKED
        temporaryDirectPlaylist = null
        lastExitOk = false
        lastExitCheckMs = 0
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
        // Explicit playlist reselection re-enforces its saved VPN/DIRECT mode.
        temporaryDirectPlaylist = null
        return runCatching {
            if (mode(context, playlistId)) connectAndVerify(context)
            else disconnectAndVerify(context)
            routeReady(context, playlistId)
        }.getOrElse { route = Route.BLOCKED; false }
    }
}
