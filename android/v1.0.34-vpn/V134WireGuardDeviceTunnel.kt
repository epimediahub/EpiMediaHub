package de.epimediahub.app.vpn

import android.content.Context
import android.content.Intent
import android.net.VpnService
import com.wireguard.android.backend.GoBackend
import com.wireguard.android.backend.Tunnel
import com.wireguard.config.Config
import java.io.BufferedReader
import java.io.StringReader

/**
 * INTERNAL SPIKE: WireGuard GoBackend integration, not hooked to playback or UI.
 * Must be called from a serialized background dispatcher, never the UI thread.
 *
 * No credentials are bundled with the APK. Config must come from an authorized,
 * time-limited device entitlement and must never be logged.
 *
 * A tunnel state of UP is NOT proof that Finland is the internet exit; production
 * playlist playback must also check an authenticated tunnel/exit probe and the
 * V134VpnRoutingPolicy state before starting a stream.
 */
internal class V134WireGuardDeviceTunnel(context: Context) {
    private val appContext = context.applicationContext
    private val backend by lazy { GoBackend(appContext) }
    private val tunnel = object : Tunnel {
        override fun getName(): String = "EpiMediaHubFI"
        override fun onStateChange(newState: Tunnel.State) = Unit
    }

    /** Launch the returned intent from the foreground Activity before calling connect(). */
    fun requestUserConsent(): Intent? = VpnService.prepare(appContext)

    @Synchronized
    fun connect(configText: String): Boolean {
        require(VpnService.prepare(appContext) == null) {
            "VPN authorization has not been granted by Android"
        }
        require(configText.length in 150..12_000) { "Invalid VPN configuration size" }

        // Parse the official WireGuard format. Restrict the Android TUN to our
        // own package; default GoBackend behavior without IncludedApplications
        // would otherwise route *all* apps on the device through the VPN.
        val config = Config.parse(BufferedReader(StringReader(configText)))
        val settings = config.getInterface()
        require(settings.getIncludedApplications() == setOf(appContext.packageName)) {
            "WireGuard configuration must allowlist only EpiMediaHub"
        }
        require(settings.getExcludedApplications().isEmpty()) {
            "Excluded applications are not supported"
        }
        require(config.getPeers().size == 1) { "Only one VPN peer is permitted" }

        // No implicit launch, retries or persistence; the caller handles a
        // playlist switch and retains playback stopped until route verified.
        return backend.setState(tunnel, Tunnel.State.UP, config) == Tunnel.State.UP
    }

    @Synchronized
    fun disconnect(): Boolean =
        backend.setState(tunnel, Tunnel.State.DOWN, null) == Tunnel.State.DOWN

    fun isUp(): Boolean = backend.getState(tunnel) == Tunnel.State.UP
}
