package de.epimediahub.app.vpn

import android.content.Context
import android.net.ConnectivityManager
import android.net.Network
import android.net.NetworkCapabilities
import android.net.NetworkInfo
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowNetwork
import org.robolectric.shadows.ShadowNetworkCapabilities
import org.robolectric.shadows.ShadowNetworkInfo
import org.robolectric.util.ReflectionHelpers

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V140VpnLossMonitorTest {
    private val context: Context get() = RuntimeEnvironment.getApplication()
    private lateinit var cm: ConnectivityManager
    private lateinit var vpn: Network
    @Before fun setup() {
        cm = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        V140VpnLossMonitor.releaseForExplicitDirect(context)
        vpn = ShadowNetwork.newInstance(701)
        val info = ShadowNetworkInfo.newInstance(NetworkInfo.DetailedState.CONNECTED,
            ConnectivityManager.TYPE_VPN, 0, true, true)
        shadowOf(cm).addNetwork(vpn, info)
        val capabilities = ShadowNetworkCapabilities.newInstance()
        shadowOf(capabilities).addTransportType(NetworkCapabilities.TRANSPORT_VPN)
        shadowOf(cm).setNetworkCapabilities(vpn, capabilities)
    }
    @After fun teardown() { V140VpnLossMonitor.releaseForExplicitDirect(context) }

    @Test fun requestActuallyMatchesVpnNetworks() {
        val capabilities = ReflectionHelpers.getField<NetworkCapabilities>(
            V140VpnLossMonitor.request(), "networkCapabilities")
        assertTrue(capabilities.hasTransport(NetworkCapabilities.TRANSPORT_VPN))
        assertFalse(capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_NOT_VPN))
    }
    @Test fun lossRetainsBindingAndRejectsRoute() {
        V140VpnLossMonitor.start(context)
        assertEquals(vpn, cm.boundNetworkForProcess)
        assertTrue(V140VpnLossMonitor.isPinned(context))
        shadowOf(cm).removeNetwork(vpn)
        shadowOf(cm).setNetworkCapabilities(vpn, null)
        shadowOf(cm).networkCallbacks.toList().forEach { it.onLost(vpn) }
        assertEquals(vpn, cm.boundNetworkForProcess)
        assertFalse(V140VpnLossMonitor.isPinned(context))
        V140VpnLossMonitor.stop()
        assertEquals("Stopping observation must not unblock sockets", vpn, cm.boundNetworkForProcess)
    }
    @Test fun explicitDirectConsentReleasesBinding() {
        V140VpnLossMonitor.start(context)
        V140VpnLossMonitor.releaseForExplicitDirect(context)
        assertNull(cm.boundNetworkForProcess)
        assertTrue(shadowOf(cm).networkCallbacks.isEmpty())
    }
}
