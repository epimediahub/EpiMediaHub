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
# Theme metadata: use the Enigma catalog's explicit family=true flag.
# ---------------------------------------------------------------------------
models = java / "model/Models.kt"
s = models.read_text()
old = 'data class ThemeInfo(val id: String, val label: String, val group: String, val accent: String)'
require_once(s, old, "ThemeInfo")
s = s.replace(old, 'data class ThemeInfo(val id: String, val label: String, val group: String, val accent: String, val family: Boolean = false)', 1)
models.write_text(s)

repo = java / "data/ThemeRepository.kt"
s = repo.read_text()
old = '            themes[id] = ThemeInfo(id, t.optString("label", id), t.optString("group"), t.optString("accent", "#28A7F2"))'
require_once(s, old, "ThemeInfo catalog mapping")
s = s.replace(old, '            themes[id] = ThemeInfo(id, t.optString("label", id), t.optString("group"), t.optString("accent", "#28A7F2"), t.optBoolean("family", false))', 1)
repo.write_text(s)


# ---------------------------------------------------------------------------
# Replace v0.4.5's user-defined optional PIN with the same fixed Family gate
# as Enigma. Only the SHA-256 digest is shipped; plaintext is never stored.
# ---------------------------------------------------------------------------
prefs = java / "data/PrefsRepository.kt"
s = prefs.read_text()
start = s.find('    private fun familyPinDigest(pin: String): String {')
end = s.find('    fun getResume(key:String)', start)
if start < 0 or end < 0:
    raise SystemExit("v0.4.5 Family PIN block not found")
fixed_family = '''    private companion object {\n        // Same fixed Family access digest as the Enigma edition.\n        // The plaintext Family PIN is intentionally never embedded or persisted.\n        const val FAMILY_PIN_HASH = "ed946f65d2c785d90e827c5ffd879ce3b49c68d4c88013074176a7e73bc58bcf"\n    }\n\n    private fun sha256(value: String): String {\n        val bytes = java.security.MessageDigest.getInstance("SHA-256")\n            .digest(value.toByteArray(Charsets.UTF_8))\n        return bytes.joinToString("") { "%02x".format(it.toInt() and 0xff) }\n    }\n\n    fun verifyFixedFamilyPin(pin: String): Boolean =\n        pin.length == 4 && pin.all(Char::isDigit) && sha256(pin) == FAMILY_PIN_HASH\n\n    fun familySkinsUnlocked(): Boolean = p.getBoolean("family_skins_unlocked", false)\n    fun setFamilySkinsUnlocked(value: Boolean) { p.edit().putBoolean("family_skins_unlocked", value).apply() }\n\n    fun remoteMaintenanceUnlocked(): Boolean = p.getBoolean("remote_maintenance_unlocked", false)\n    fun setRemoteMaintenanceUnlocked(value: Boolean) { p.edit().putBoolean("remote_maintenance_unlocked", value).apply() }\n\n'''
s = s[:start] + fixed_family + s[end:]
prefs.write_text(s)


# ---------------------------------------------------------------------------
# Local web admin: LAN stays available with the temporary setup PIN. Remote
# access is Tailscale-only and is refused until the fixed Family gate was
# explicitly unlocked on the device. A permitted Tailscale peer then does not
# need the temporary local-web PIN: Family unlock + Tailnet identity is the
# remote-maintenance gate, matching the Enigma/Raspberry workflow.
# ---------------------------------------------------------------------------
web = java / "data/LocalWebAdmin.kt"
s = web.read_text()
old = '''    private val pin: String,\n    private val playlistsProvider: () -> List<PlaylistProfile>,'''
require_once(s, old, "LocalWebAdmin constructor")
s = s.replace(old, '''    private val pin: String,\n    private val allowTailscaleRemote: () -> Boolean = { false },\n    private val playlistsProvider: () -> List<PlaylistProfile>,''', 1)

old = '''    val remoteAddress: String\n        get() = vpnIpv4()?.let { "http://$it:$listeningPort" }.orEmpty()'''
require_once(s, old, "remoteAddress")
s = s.replace(old, '''    val remoteAddress: String\n        get() = if (allowTailscaleRemote()) tailscaleIpv4()?.let { "http://$it:$listeningPort" }.orEmpty() else ""''', 1)

old = '''    private fun vpnIpv4(): String? = allIpv4()\n        .firstOrNull { (nic, addr) -> isVpnInterface(nic) || isTailscaleIpv4(addr.hostAddress.orEmpty()) }\n        ?.second?.hostAddress'''
require_once(s, old, "vpnIpv4")
s = s.replace(old, '''    private fun tailscaleIpv4(): String? = allIpv4()\n        .firstOrNull { (_, addr) -> isTailscaleIpv4(addr.hostAddress.orEmpty()) }\n        ?.second?.hostAddress''', 1)

old = '''    private fun isPrivateClient(ip: String): Boolean {\n        if (ip.isBlank() || ip == "127.0.0.1" || ip == "::1") return true\n        if (ip.startsWith("192.168.") || ip.startsWith("10.") || ip.startsWith("fd") || ip.startsWith("fe80:")) return true\n        if (isTailscaleIpv4(ip)) return true\n        val parts = ip.split('.')\n        if (parts.size == 4 && parts[0] == "172") {\n            val second = parts[1].toIntOrNull() ?: return false\n            if (second in 16..31) return true\n        }\n        return false\n    }'''
require_once(s, old, "isPrivateClient")
s = s.replace(old, '''    private fun isTailscaleClient(ip: String): Boolean =\n        isTailscaleIpv4(ip) || ip.lowercase().startsWith("fd7a:115c:a1e0:")\n\n    private fun isPrivateClient(ip: String): Boolean {\n        if (ip.isBlank() || ip == "127.0.0.1" || ip == "::1") return true\n        // Tailscale IPv6 also starts with fd, therefore this test must happen\n        // before the generic private-IPv6 allowance below.\n        if (isTailscaleClient(ip)) return allowTailscaleRemote()\n        if (ip.startsWith("192.168.") || ip.startsWith("10.") || ip.startsWith("fd") || ip.startsWith("fe80:")) return true\n        val parts = ip.split('.')\n        if (parts.size == 4 && parts[0] == "172") {\n            val second = parts[1].toIntOrNull() ?: return false\n            if (second in 16..31) return true\n        }\n        return false\n    }''', 1)

s = s.replace('"Nur im lokalen Netzwerk verfügbar."', '"Lokales Websetup oder freigeschaltete Tailscale-Fernwartung erforderlich."', 1)
old = '        if (p["pin"].orEmpty().trim() != pin) return page("PIN ist falsch.", isError = true)'
require_once(s, old, "web POST PIN")
s = s.replace(old, '''        val fromTailscale = isTailscaleClient(session.remoteIpAddress.orEmpty())\n        if (!fromTailscale && p["pin"].orEmpty().trim() != pin) return page("PIN ist falsch.", isError = true)''', 1)

s = s.replace('Playlist-Verwaltung im lokalen Netzwerk · Android TV & Mobile', 'Playlist-Verwaltung · lokal mit Websetup-PIN · Fernwartung nach Family-Freigabe über Tailscale')
s = s.replace('<label>PIN aus der App</label><input name="pin" inputmode="numeric" autocomplete="off" required>', '<label>Lokales Websetup: PIN aus der App (über Tailscale nicht nötig)</label><input name="pin" inputmode="numeric" autocomplete="off">')
web.write_text(s)


# ---------------------------------------------------------------------------
# ViewModel: two persistent unlock states, one immutable Family PIN verifier.
# Family skins and remote maintenance are deliberately separate unlocks.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
old = '''    val webAdminRemoteUrl: String = "",\n    val familyProtectionEnabled: Boolean = false\n)'''
require_once(s, old, "UiState v0.4.5 family fields")
s = s.replace(old, '''    val webAdminRemoteUrl: String = "",\n    val familyProtectionEnabled: Boolean = true,\n    val familySkinsUnlocked: Boolean = false,\n    val remoteMaintenanceUnlocked: Boolean = false\n)''', 1)

old = '            familyProtectionEnabled = prefs.hasFamilyPin()'
require_once(s, old, "v0.4.5 initial Family state")
s = s.replace(old, '''            familyProtectionEnabled = true,\n            familySkinsUnlocked = prefs.familySkinsUnlocked(),\n            remoteMaintenanceUnlocked = prefs.remoteMaintenanceUnlocked()''', 1)

old = '''        val server = LocalWebAdmin(\n            pin = pin,\n            playlistsProvider = { prefs.loadPlaylists() },'''
require_once(s, old, "LocalWebAdmin construction")
s = s.replace(old, '''        val server = LocalWebAdmin(\n            pin = pin,\n            allowTailscaleRemote = { prefs.remoteMaintenanceUnlocked() },\n            playlistsProvider = { prefs.loadPlaylists() },''', 1)

old = '            set { it.copy(webAdminRunning = true, webAdminUrl = server.localAddress, webAdminRemoteUrl = server.remoteAddress, webAdminPin = pin, error = "") }'
require_once(s, old, "web admin start state")
s = s.replace(old, '            set { it.copy(webAdminRunning = true, webAdminUrl = server.localAddress, webAdminRemoteUrl = server.remoteAddress, webAdminPin = pin, remoteMaintenanceUnlocked = prefs.remoteMaintenanceUnlocked(), error = "") }', 1)

start = s.find('    fun restartWebAdmin() {')
end = s.find('    override fun onCleared() {', start)
if start < 0 or end < 0:
    raise SystemExit("v0.4.5 web/family controls block not found")
controls = '''    fun restartWebAdmin() {\n        stopWebAdmin()\n        startWebAdmin()\n    }\n\n    fun refreshWebAdminAccess() {\n        val server = webAdmin\n        val remoteAllowed = prefs.remoteMaintenanceUnlocked()\n        set {\n            it.copy(\n                webAdminUrl = server?.localAddress ?: it.webAdminUrl,\n                webAdminRemoteUrl = if (remoteAllowed) server?.remoteAddress.orEmpty() else "",\n                familyProtectionEnabled = true,\n                familySkinsUnlocked = prefs.familySkinsUnlocked(),\n                remoteMaintenanceUnlocked = remoteAllowed\n            )\n        }\n    }\n\n    fun unlockFamilySkins(pin: String): Boolean {\n        if (!prefs.verifyFixedFamilyPin(pin)) return false\n        prefs.setFamilySkinsUnlocked(true)\n        set { it.copy(familyProtectionEnabled = true, familySkinsUnlocked = true, error = "") }\n        return true\n    }\n\n    fun unlockRemoteMaintenance(pin: String): Boolean {\n        if (!prefs.verifyFixedFamilyPin(pin)) return false\n        prefs.setRemoteMaintenanceUnlocked(true)\n        set { it.copy(remoteMaintenanceUnlocked = true, error = "") }\n        refreshWebAdminAccess()\n        return true\n    }\n\n    fun lockRemoteMaintenance() {\n        prefs.setRemoteMaintenanceUnlocked(false)\n        set { it.copy(remoteMaintenanceUnlocked = false, webAdminRemoteUrl = "") }\n    }\n\n'''
s = s[:start] + controls + s[end:]

# Never allow a stale v0.4.5 selection to keep a Family theme active before
# the fixed Enigma Family gate has been unlocked.
old = '    init { refreshProfiles() }'
require_once(s, old, "ViewModel init")
s = s.replace(old, '''    init {\n        enforceFamilyThemeGate()\n        refreshProfiles()\n    }\n\n    private fun enforceFamilyThemeGate() {\n        val state = _ui.value\n        if (!state.familySkinsUnlocked && state.themeCatalog?.themes?.get(state.themeId)?.family == true) {\n            prefs.themeId = "default"\n            _ui.value = state.copy(themeId = "default")\n        }\n    }''', 1)

old = '''    fun selectTheme(id: String) {\n        prefs.themeId = id\n        set { it.copy(themeId = id) }\n    }'''
require_once(s, old, "selectTheme")
s = s.replace(old, '''    fun selectTheme(id: String) {\n        val theme = _ui.value.themeCatalog?.themes?.get(id) ?: return\n        if (theme.family && !prefs.familySkinsUnlocked()) return\n        prefs.themeId = id\n        set { it.copy(themeId = id) }\n    }''', 1)
vm.write_text(s)


# ---------------------------------------------------------------------------
# Route v0.4.6 screens and update visible version labels.
# ---------------------------------------------------------------------------
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
old = '                Screen.Themes -> V045ThemesScreen(vm, accent, isTv)\n'
require_once(s, old, "v0.4.5 themes route")
s = s.replace(old, '                Screen.Themes -> V046ThemesScreen(vm, accent, isTv)\n', 1)
old = '                Screen.WebAdmin -> V045WebAdminScreen(vm, accent, isTv)\n'
require_once(s, old, "v0.4.5 web route")
s = s.replace(old, '                Screen.WebAdmin -> V046WebAdminScreen(vm, accent, isTv)\n', 1)
app.write_text(s)

home = java / "ui/V044Home.kt"
s = home.read_text().replace('0.4.5', '0.4.6')
home.write_text(s)

screens = java / "ui/Screens.kt"
s = screens.read_text().replace('Android v0.4.5', 'Android v0.4.6')
screens.write_text(s)

med = java / "data/MediathekClient.kt"
s = med.read_text().replace('EpiMediaHub-Android/0.4.5', 'EpiMediaHub-Android/0.4.6').replace('EpiMediaHub/0.4.5', 'EpiMediaHub/0.4.6')
med.write_text(s)

print("Android v0.4.6 fixed Family PIN + Tailscale-only Raspberry remote gate applied")
