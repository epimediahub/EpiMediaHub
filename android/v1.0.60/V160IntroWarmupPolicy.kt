package de.epimediahub.app.ui

/**
 * Warm-up may fetch catalogue metadata but never media streams.
 * Reuse the existing VPN route decision and pairing/license gates.
 */
internal object V160IntroWarmupPolicy {
    fun allowed(introVisible: Boolean, paired: Boolean, licensed: Boolean,
                routeApproved: Boolean, hasPlaylist: Boolean): Boolean =
        introVisible && paired && licensed && routeApproved && hasPlaylist
}
