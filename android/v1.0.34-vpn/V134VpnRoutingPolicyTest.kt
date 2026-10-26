package de.epimediahub.app.vpn

import de.epimediahub.app.vpn.V134VpnRoutingPolicy as P

/** Portable safety contract, runnable outside Android. */
object V134VpnRoutingPolicyTest {
    @JvmStatic fun main(args: Array<String>) {
        var cases = 0
        val direct = P.Selection(42, false)
        val selected = P.Selection(42, true, "fi")
        val license = P.Entitlement("firetv-1", 5_000, true)
        val up = P.TunnelObservation(authorized = true, connected = true,
            appIsRoutedThroughTunnel = true, exitCountry = "fi")
        val down = P.TunnelObservation()
        val media = P.VerifiedPlayers(media3 = true)
        fun check(expected: P.Route, reason: P.Reason, selection: P.Selection = selected,
                  device: String = "firetv-1", now: Long = 1_000,
                  licenseValue: P.Entitlement? = license,
                  tunnel: P.TunnelObservation = up,
                  player: P.Player = P.Player.MEDIA3,
                  verified: P.VerifiedPlayers = media) {
            val actual = P.decide(selection, device, now, licenseValue, tunnel, player, verified)
            require(actual.route == expected && actual.reason == reason) {
                "case ${cases + 1}: expected $expected/$reason got ${actual.route}/${actual.reason}"
            }
            cases++
        }
        check(P.Route.DIRECT, P.Reason.NONE, selection = direct, tunnel = down)
        check(P.Route.BLOCKED, P.Reason.VPN_STILL_ACTIVE, selection = direct)
        check(P.Route.BLOCKED, P.Reason.INVALID_PLAYLIST, selection = P.Selection(0, true))
        check(P.Route.BLOCKED, P.Reason.UNSUPPORTED_COUNTRY, selection = P.Selection(42, true, "us"))
        check(P.Route.BLOCKED, P.Reason.MISSING_LICENSE, licenseValue = null)
        check(P.Route.BLOCKED, P.Reason.MISSING_LICENSE, licenseValue = license.copy(enabled = false))
        check(P.Route.BLOCKED, P.Reason.WRONG_DEVICE, device = "firetv-2")
        check(P.Route.BLOCKED, P.Reason.LICENSE_EXPIRED, now = 5_000)
        check(P.Route.BLOCKED, P.Reason.VPN_NOT_AUTHORIZED, tunnel = up.copy(authorized = false))
        check(P.Route.BLOCKED, P.Reason.VPN_NOT_CONNECTED, tunnel = up.copy(connected = false))
        check(P.Route.BLOCKED, P.Reason.VPN_NOT_CONNECTED, tunnel = up.copy(appIsRoutedThroughTunnel = false))
        check(P.Route.BLOCKED, P.Reason.WRONG_EXIT_COUNTRY, tunnel = up.copy(exitCountry = "de"))
        check(P.Route.BLOCKED, P.Reason.UNSAFE_PLAYER_ROUTING, verified = P.VerifiedPlayers())
        check(P.Route.BLOCKED, P.Reason.UNSAFE_PLAYER_ROUTING, player = P.Player.VLC)
        check(P.Route.FINLAND, P.Reason.NONE)
        check(P.Route.FINLAND, P.Reason.NONE, player = P.Player.VLC,
            verified = P.VerifiedPlayers(media3 = true, vlc = true))
        println("PASS: $cases VPN-Routing-Sicherheitsfaelle")
    }
}
