package de.epimediahub.app.vpn

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class V153DirectPolicyTest {
    @Test fun ordinaryDirectPlaylistDoesNotNeedAnExternalIpProbe() {
        assertTrue(V153DirectPolicy.canPlay(routeDirect = true, appTunnelUp = false, processNetworkBound = false))
    }
    @Test fun neverFailOpenWithoutExplicitDirectSelection() {
        assertFalse(V153DirectPolicy.canPlay(routeDirect = false, appTunnelUp = false, processNetworkBound = false))
    }
    @Test fun neverPlayDirectWithActiveVpnTunnel() {
        assertFalse(V153DirectPolicy.canPlay(routeDirect = true, appTunnelUp = true, processNetworkBound = false))
    }
    @Test fun neverPlayDirectOnStaleVpnBoundNetwork() {
        assertFalse(V153DirectPolicy.canPlay(routeDirect = true, appTunnelUp = false, processNetworkBound = true))
    }
}
