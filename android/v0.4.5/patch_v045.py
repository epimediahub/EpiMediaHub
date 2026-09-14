#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


# ---------------------------------------------------------------------------
# Persist Family PIN only as a salted SHA-256 digest.
# ---------------------------------------------------------------------------
prefs = java / "data/PrefsRepository.kt"
s = prefs.read_text()
anchor = '    fun getResume(key:String)=p.getLong("resume_$key",0L)\n'
require_once(s, anchor, "Prefs getResume")
family_methods = r'''    private fun familyPinDigest(pin: String): String {
        val bytes = java.security.MessageDigest.getInstance("SHA-256")
            .digest(("EpiMediaHub-Family-v1|" + pin).toByteArray(Charsets.UTF_8))
        return bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }
    }

    fun hasFamilyPin(): Boolean = p.getString("family_pin_hash", "").orEmpty().isNotBlank()
    fun setFamilyPin(pin: String) { p.edit().putString("family_pin_hash", familyPinDigest(pin)).apply() }
    fun verifyFamilyPin(pin: String): Boolean {
        val stored = p.getString("family_pin_hash", "").orEmpty()
        return stored.isNotBlank() && stored == familyPinDigest(pin)
    }
    fun clearFamilyPin() { p.edit().remove("family_pin_hash").apply() }

'''
s = s.replace(anchor, family_methods + anchor, 1)
prefs.write_text(s)


# ---------------------------------------------------------------------------
# Web admin: expose LAN + secure overlay/VPN address and allow Tailscale CGNAT.
# ---------------------------------------------------------------------------
web = java / "data/LocalWebAdmin.kt"
s = web.read_text()
old = '''    val address: String\n        get() = "http://${localIpv4() ?: "127.0.0.1"}:$listeningPort"\n'''
require_once(s, old, "LocalWebAdmin address")
new = '''    val localAddress: String\n        get() = "http://${localIpv4() ?: "127.0.0.1"}:$listeningPort"\n\n    val remoteAddress: String\n        get() = vpnIpv4()?.let { "http://$it:$listeningPort" }.orEmpty()\n\n    val address: String\n        get() = localAddress\n'''
s = s.replace(old, new, 1)

old_local = '''    private fun localIpv4(): String? = runCatching {\n        Collections.list(NetworkInterface.getNetworkInterfaces())\n            .filter { it.isUp && !it.isLoopback }\n            .flatMap { Collections.list(it.inetAddresses) }\n            .filterIsInstance<Inet4Address>()\n            .firstOrNull { it.isSiteLocalAddress }\n            ?.hostAddress\n    }.getOrNull()\n'''
require_once(s, old_local, "LocalWebAdmin localIpv4")
new_local = r'''    private fun allIpv4(): List<Pair<NetworkInterface, Inet4Address>> = runCatching {
        Collections.list(NetworkInterface.getNetworkInterfaces())
            .filter { it.isUp && !it.isLoopback }
            .flatMap { nic -> Collections.list(nic.inetAddresses).filterIsInstance<Inet4Address>().map { nic to it } }
    }.getOrDefault(emptyList())

    private fun isVpnInterface(nic: NetworkInterface): Boolean {
        val name = ((nic.name ?: "") + " " + (nic.displayName ?: "")).lowercase()
        return name.contains("tailscale") || name.startsWith("tun") || name.startsWith("wg") ||
            name.contains("wireguard") || name.startsWith("zt") || name.contains("zerotier")
    }

    private fun isTailscaleIpv4(ip: String): Boolean {
        val p = ip.split('.')
        if (p.size != 4 || p[0] != "100") return false
        val second = p[1].toIntOrNull() ?: return false
        return second in 64..127
    }

    private fun vpnIpv4(): String? = allIpv4()
        .firstOrNull { (nic, addr) -> isVpnInterface(nic) || isTailscaleIpv4(addr.hostAddress.orEmpty()) }
        ?.second?.hostAddress

    private fun localIpv4(): String? = allIpv4()
        .firstOrNull { (nic, addr) -> addr.isSiteLocalAddress && !isVpnInterface(nic) }
        ?.second?.hostAddress
'''
s = s.replace(old_local, new_local, 1)

needle = '        if (ip.startsWith("192.168.") || ip.startsWith("10.") || ip.startsWith("fd") || ip.startsWith("fe80:")) return true\n'
require_once(s, needle, "private client ranges")
s = s.replace(needle, needle + '        if (isTailscaleIpv4(ip)) return true\n', 1)
web.write_text(s)


# ---------------------------------------------------------------------------
# State + controls for remote URL and Family PIN.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
old = '    val contentFilterKind: MediaKind? = null\n)'
require_once(s, old, "UiState contentFilterKind")
s = s.replace(
    old,
    '    val contentFilterKind: MediaKind? = null,\n    val webAdminRemoteUrl: String = "",\n    val familyProtectionEnabled: Boolean = false\n)',
    1,
)

init_anchor = '''            favorites = prefs.loadFavoriteEntries(),\n            continueWatching = prefs.loadContinue(),\n            preferredAudioLanguage = prefs.preferredAudioLanguage,\n            preferredSubtitleLanguage = prefs.preferredSubtitleLanguage\n'''
require_once(s, init_anchor, "UiState initial preferences")
s = s.replace(
    init_anchor,
    '''            favorites = prefs.loadFavoriteEntries(),\n            continueWatching = prefs.loadContinue(),\n            preferredAudioLanguage = prefs.preferredAudioLanguage,\n            preferredSubtitleLanguage = prefs.preferredSubtitleLanguage,\n            familyProtectionEnabled = prefs.hasFamilyPin()\n''',
    1,
)

old_set = '            set { it.copy(webAdminRunning = true, webAdminUrl = server.address, webAdminPin = pin, error = "") }'
require_once(s, old_set, "startWebAdmin state")
s = s.replace(
    old_set,
    '            set { it.copy(webAdminRunning = true, webAdminUrl = server.localAddress, webAdminRemoteUrl = server.remoteAddress, webAdminPin = pin, error = "") }',
    1,
)

old_stop = '        set { it.copy(webAdminRunning = false, webAdminUrl = "", webAdminPin = "") }'
require_once(s, old_stop, "stopWebAdmin state")
s = s.replace(
    old_stop,
    '        set { it.copy(webAdminRunning = false, webAdminUrl = "", webAdminRemoteUrl = "", webAdminPin = "") }',
    1,
)

insert_anchor = '    override fun onCleared() {\n'
require_once(s, insert_anchor, "onCleared")
controls = r'''    fun restartWebAdmin() {
        stopWebAdmin()
        startWebAdmin()
    }

    fun refreshWebAdminAccess() {
        val server = webAdmin ?: return
        set { it.copy(webAdminUrl = server.localAddress, webAdminRemoteUrl = server.remoteAddress) }
    }

    fun enableFamilyPin(pin: String): Boolean {
        if (!pin.matches(Regex("""\d{4,8}"""))) return false
        prefs.setFamilyPin(pin)
        set { it.copy(familyProtectionEnabled = true, error = "") }
        return true
    }

    fun verifyFamilyPin(pin: String): Boolean = prefs.verifyFamilyPin(pin)

    fun disableFamilyPin(pin: String): Boolean {
        if (!prefs.verifyFamilyPin(pin)) return false
        prefs.clearFamilyPin()
        set { it.copy(familyProtectionEnabled = false, error = "") }
        return true
    }

    fun changeFamilyPin(oldPin: String, newPin: String): Boolean {
        if (!prefs.verifyFamilyPin(oldPin) || !newPin.matches(Regex("""\d{4,8}"""))) return false
        prefs.setFamilyPin(newPin)
        set { it.copy(familyProtectionEnabled = true, error = "") }
        return true
    }

'''
s = s.replace(insert_anchor, controls + insert_anchor, 1)
vm.write_text(s)


# ---------------------------------------------------------------------------
# Route compact web admin + protected themes.
# ---------------------------------------------------------------------------
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
old = '                Screen.Themes -> V044ThemesScreen(vm, accent, isTv)\n'
require_once(s, old, "v0.4.4 themes route")
s = s.replace(old, '                Screen.Themes -> V045ThemesScreen(vm, accent, isTv)\n', 1)
old = '                Screen.WebAdmin -> WebAdminScreen(vm, accent)\n'
require_once(s, old, "web admin route")
s = s.replace(old, '                Screen.WebAdmin -> V045WebAdminScreen(vm, accent, isTv)\n', 1)
app.write_text(s)

# Visible version labels.
home = java / "ui/V044Home.kt"
s = home.read_text().replace('0.4.4', '0.4.5')
home.write_text(s)

screens = java / "ui/Screens.kt"
s = screens.read_text().replace('Android v0.4.4', 'Android v0.4.5')
screens.write_text(s)

med = java / "data/MediathekClient.kt"
s = med.read_text().replace('EpiMediaHub-Android/0.4.4', 'EpiMediaHub-Android/0.4.5').replace('EpiMediaHub/0.4.4', 'EpiMediaHub/0.4.5')
med.write_text(s)

print("Android v0.4.5 compact websetup, VPN remote maintenance and Family PIN patch applied")
