package de.epimediahub.app.vpn

/**
 * Conservative policy ONLY. A separate transport adapter must prove VPN state.
 * No VPN connection, license issuance or playback interception happens here.
 */
internal object V134VpnRoutingPolicy {
    enum class Route { DIRECT, FINLAND, BLOCKED }
    enum class Player { MEDIA3, VLC }
    enum class Reason {
        NONE, INVALID_PLAYLIST, UNSUPPORTED_COUNTRY, VPN_STILL_ACTIVE,
        MISSING_LICENSE, WRONG_DEVICE, LICENSE_EXPIRED,
        VPN_NOT_AUTHORIZED, VPN_NOT_CONNECTED, WRONG_EXIT_COUNTRY,
        UNSAFE_PLAYER_ROUTING
    }

    data class Selection(val playlistId: Long, val vpnEnabled: Boolean, val exitCountry: String = "fi")
    data class Entitlement(val deviceId: String, val expiresAtEpochMillis: Long, val enabled: Boolean)
    data class TunnelObservation(
        val authorized: Boolean = false, val connected: Boolean = false,
        val appIsRoutedThroughTunnel: Boolean = false, val exitCountry: String? = null
    )
    data class VerifiedPlayers(val media3: Boolean = false, val vlc: Boolean = false) {
        fun isVerified(player: Player): Boolean = when (player) {
            Player.MEDIA3 -> media3
            Player.VLC -> vlc
        }
    }
    data class Decision(val route: Route, val reason: Reason = Reason.NONE) {
        val mayStartPlayback: Boolean get() = route != Route.BLOCKED
    }

    fun decide(
        selection: Selection, currentDeviceId: String, nowEpochMillis: Long,
        entitlement: Entitlement?, tunnel: TunnelObservation, player: Player,
        players: VerifiedPlayers = VerifiedPlayers()
    ): Decision {
        if (selection.playlistId <= 0L) return Decision(Route.BLOCKED, Reason.INVALID_PLAYLIST)
        if (!selection.vpnEnabled) {
            return if (tunnel.connected || tunnel.appIsRoutedThroughTunnel)
                Decision(Route.BLOCKED, Reason.VPN_STILL_ACTIVE)
            else Decision(Route.DIRECT)
        }
        if (selection.exitCountry != "fi") return Decision(Route.BLOCKED, Reason.UNSUPPORTED_COUNTRY)
        if (entitlement == null || !entitlement.enabled) return Decision(Route.BLOCKED, Reason.MISSING_LICENSE)
        if (currentDeviceId.isBlank() || entitlement.deviceId != currentDeviceId)
            return Decision(Route.BLOCKED, Reason.WRONG_DEVICE)
        if (nowEpochMillis >= entitlement.expiresAtEpochMillis)
            return Decision(Route.BLOCKED, Reason.LICENSE_EXPIRED)
        if (!tunnel.authorized) return Decision(Route.BLOCKED, Reason.VPN_NOT_AUTHORIZED)
        if (!tunnel.connected || !tunnel.appIsRoutedThroughTunnel)
            return Decision(Route.BLOCKED, Reason.VPN_NOT_CONNECTED)
        if (tunnel.exitCountry != "fi") return Decision(Route.BLOCKED, Reason.WRONG_EXIT_COUNTRY)
        if (!players.isVerified(player)) return Decision(Route.BLOCKED, Reason.UNSAFE_PLAYER_ROUTING)
        return Decision(Route.FINLAND)
    }
}
