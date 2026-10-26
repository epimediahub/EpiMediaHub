#!/usr/bin/env python3
"""v1.0.53: restore DIRECT-playlist playback independently of ipify availability.

Apply only AFTER patch_v152.py. Leave VPN-enabled fail-closed behavior, saved
playlist preferences, VPN keys and encrypted profiles unchanged.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
src = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (path, text.count(old), old[:100])
    path.write_text(text.replace(old, new, 1))

build = root / "app/build.gradle.kts"
replace(build, "versionCode = 1052", "versionCode = 1053")
replace(build, 'versionName = "1.0.52"', 'versionName = "1.0.53"')

shutil.copyfile(here / "V153DirectPolicy.kt", src / "vpn/V153DirectPolicy.kt")
shutil.copyfile(here / "V153DirectPolicyTest.kt", tests / "vpn/V153DirectPolicyTest.kt")

session = src / "vpn/V134VpnSession.kt"
replace(session,
    "import android.net.VpnService\n",
    "import android.net.VpnService\nimport android.net.ConnectivityManager\n")
replace(session,
    """        if (mode(context, playlistId) && temporaryDirectPlaylist == playlistId) {
            return route == Route.DIRECT && !actual
        }
        if (!mode(context, playlistId)) return route == Route.DIRECT && !actual""",
    """        if (mode(context, playlistId) && temporaryDirectPlaylist == playlistId) {
            val cm = context.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            return V153DirectPolicy.canPlay(route == Route.DIRECT, actual, cm.boundNetworkForProcess != null)
        }
        if (!mode(context, playlistId)) {
            val cm = context.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
            return V153DirectPolicy.canPlay(route == Route.DIRECT, actual, cm.boundNetworkForProcess != null)
        }""")

# Only the explicitly chosen DIRECT path is changed. It now verifies the own
# VPN tunnel was disconnected and process unpinned without contacting api.ipify.
# The verified VPN route and consent-first one-time fallback still use ip checks.
replace(session,
    """        V140VpnLossMonitor.releaseForExplicitDirect(context)
        val ip = publicIpv4()
        check(ip != FINLAND_IP) { "Direktverbindung nicht bestätigt" }
        route = Route.DIRECT
        return ip""",
    """        V140VpnLossMonitor.releaseForExplicitDirect(context)
        val cm = context.applicationContext.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        check(!tunnel(context).isUp() && cm.boundNetworkForProcess == null) {
            "EpiMediaHub-VPN ist noch aktiv oder der Prozess weiterhin an ein Netz gebunden"
        }
        route = Route.DIRECT
        return "EpiMediaHub-VPN getrennt" """ .rstrip())
source = session.read_text()
method = source.split("fun disconnectAndVerify(context: Context): String", 1)[1].split("fun publicIpv4()", 1)[0]
assert "publicIpv4()" not in method, "DIRECT should not depend on external IP service"
assert "val directIp = publicIpv4()" in source, "Explicit one-time VPN fallback must stay verified"
assert 'check(ip == FINLAND_IP)' in source, "Verified Finnish VPN route must stay protected"
print("v1.0.53: verified DIRECT mode works without public-IP service; VPN stays fail-closed.")
