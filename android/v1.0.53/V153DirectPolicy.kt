package de.epimediahub.app.vpn

/**
 * Playback is DIRECT only if the user has selected an explicit direct route,
 * our WireGuard tunnel is down and the process is not still pinned to VPN.
 * A third-party public-IP service is not a prerequisite for direct playback.
 * VPN-required playlists are checked separately by V134VpnSession.
 */
internal object V153DirectPolicy {
    fun canPlay(routeDirect: Boolean, appTunnelUp: Boolean, processNetworkBound: Boolean): Boolean =
        routeDirect && !appTunnelUp && !processNetworkBound
}
