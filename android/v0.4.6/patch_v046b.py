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
# Use two independent immutable gates:
# - Family skin PIN: same fixed PIN/hash as Enigma.
# - Remote maintenance PIN: separate fixed PIN/hash for Tailscale maintenance.
# Only SHA-256 digests are shipped in the APK.
# ---------------------------------------------------------------------------
prefs = java / "data/PrefsRepository.kt"
s = prefs.read_text()
family_const = '        const val FAMILY_PIN_HASH = "ed946f65d2c785d90e827c5ffd879ce3b49c68d4c88013074176a7e73bc58bcf"\n'
require_once(s, family_const, "Family PIN hash")
s = s.replace(
    family_const,
    family_const + '        const val REMOTE_MAINTENANCE_PIN_HASH = "7a866153fcd1a9ed6c44f051287622547d959709cd49731684a70dbfac852c58"\n',
    1,
)
family_verify = '''    fun verifyFixedFamilyPin(pin: String): Boolean =\n        pin.length == 4 && pin.all(Char::isDigit) && sha256(pin) == FAMILY_PIN_HASH\n\n'''
require_once(s, family_verify, "Family PIN verifier")
s = s.replace(
    family_verify,
    family_verify + '''    fun verifyFixedRemoteMaintenancePin(pin: String): Boolean =\n        pin.length == 4 && pin.all(Char::isDigit) && sha256(pin) == REMOTE_MAINTENANCE_PIN_HASH\n\n''',
    1,
)
prefs.write_text(s)


# ---------------------------------------------------------------------------
# ViewModel: remote maintenance uses its own PIN. Websetup is independent of
# playlist state: a fresh install with zero playlists opens Websetup directly.
# Once remote maintenance was unlocked, its web server also auto-starts later.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
old_remote = '''    fun unlockRemoteMaintenance(pin: String): Boolean {\n        if (!prefs.verifyFixedFamilyPin(pin)) return false\n        prefs.setRemoteMaintenanceUnlocked(true)\n        set { it.copy(remoteMaintenanceUnlocked = true, error = "") }\n        refreshWebAdminAccess()\n        return true\n    }'''
require_once(s, old_remote, "Remote unlock verifier")
s = s.replace(
    old_remote,
    '''    fun unlockRemoteMaintenance(pin: String): Boolean {\n        if (!prefs.verifyFixedRemoteMaintenancePin(pin)) return false\n        prefs.setRemoteMaintenanceUnlocked(true)\n        if (webAdmin == null) startWebAdmin()\n        set { it.copy(remoteMaintenanceUnlocked = true, error = "") }\n        refreshWebAdminAccess()\n        return true\n    }''',
    1,
)
old_init = '''    init {\n        enforceFamilyThemeGate()\n        refreshProfiles()\n    }'''
require_once(s, old_init, "ViewModel init")
s = s.replace(
    old_init,
    '''    init {\n        enforceFamilyThemeGate()\n        refreshProfiles()\n        val noPlaylist = _ui.value.playlists.isEmpty()\n        if (prefs.remoteMaintenanceUnlocked() || noPlaylist) startWebAdmin()\n        // Fernwartung/Websetup must be reachable before any playlist exists.\n        // Therefore a fresh installation starts here instead of trapping the\n        // user inside the playlist form. A direct on-device playlist button is\n        // available on this screen as well.\n        if (noPlaylist) set { it.copy(screen = Screen.WebAdmin) }\n    }''',
    1,
)
vm.write_text(s)


# ---------------------------------------------------------------------------
# Make the shared PIN dialog reusable so remote maintenance clearly asks for a
# separate Fernwartungs-PIN instead of calling it the Family PIN.
# ---------------------------------------------------------------------------
themes = java / "ui/V046Themes.kt"
s = themes.read_text()
old_sig = '''fun V046FamilyPinDialog(\n    title: String,\n    message: String,\n    onDismiss: () -> Unit,\n    onVerify: (String) -> Boolean\n) {'''
require_once(s, old_sig, "PIN dialog signature")
s = s.replace(
    old_sig,
    '''fun V046FamilyPinDialog(\n    title: String,\n    message: String,\n    pinLabel: String = "Family-PIN",\n    errorText: String = "Family-PIN ist falsch.",\n    onDismiss: () -> Unit,\n    onVerify: (String) -> Boolean\n) {''',
    1,
)
require_once(s, '                    label = { Text("Family-PIN") },', "PIN dialog label")
s = s.replace('                    label = { Text("Family-PIN") },', '                    label = { Text(pinLabel) },', 1)
require_once(s, '                if (error) Text("Family-PIN ist falsch.", color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 6.dp))', "PIN dialog error")
s = s.replace(
    '                if (error) Text("Family-PIN ist falsch.", color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 6.dp))',
    '                if (error) Text(errorText, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 6.dp))',
    1,
)
themes.write_text(s)


# ---------------------------------------------------------------------------
# Remote screen wording: separate remote PIN, no Family-PIN ambiguity, and a
# direct on-device playlist setup button when no playlist exists yet.
# ---------------------------------------------------------------------------
remote = java / "ui/V046WebAdmin.kt"
s = remote.read_text()
import_anchor = 'import de.epimediahub.app.MainViewModel\n'
require_once(s, import_anchor, "V046WebAdmin MainViewModel import")
s = s.replace(import_anchor, import_anchor + 'import de.epimediahub.app.Screen\n', 1)
replacements = {
    'Freischaltung nur mit der speziellen Family-PIN – danach ausschließlich über Tailscale.': 'Freischaltung nur mit der separaten Fernwartungs-PIN – danach ausschließlich über Tailscale.',
    'Text("Mit Family-PIN freischalten", color = Color.Black, fontWeight = FontWeight.Black)': 'Text("Mit Fernwartungs-PIN freischalten", color = Color.Black, fontWeight = FontWeight.Black)',
    'Text("Family-Freigabe aktiv · Tailscale-Verbindung fehlt noch.", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)': 'Text("Fernwartungs-Freigabe aktiv · Tailscale-Verbindung fehlt noch.", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)',
    'message = "Gib die spezielle Family-PIN ein. Die Freigabe öffnet ausschließlich den Tailscale-Wartungsweg für deinen Raspberry; es wird kein Internet-Port geöffnet.",': 'message = "Gib die separate Fernwartungs-PIN ein. Die Freigabe öffnet ausschließlich den Tailscale-Wartungsweg für deinen Raspberry; es wird kein Internet-Port geöffnet.",\n            pinLabel = "Fernwartungs-PIN",\n            errorText = "Fernwartungs-PIN ist falsch.",',
}
for old, new in replacements.items():
    require_once(s, old, f"Remote wording {old[:28]}")
    s = s.replace(old, new, 1)
old_buttons = '''                            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {\n                                TextButton(onClick = { vm.restartWebAdmin() }) { Text("Websetup neu starten") }\n                                TextButton(onClick = { vm.stopWebAdmin() }) { Text("Websetup stoppen") }\n                            }'''
require_once(s, old_buttons, "Websetup action row")
s = s.replace(
    old_buttons,
    '''                            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {\n                                if (u.playlists.isEmpty()) {\n                                    TextButton(onClick = { vm.navigate(Screen.AddPlaylist) }) { Text("Playlist am Gerät") }\n                                }\n                                TextButton(onClick = { vm.restartWebAdmin() }) { Text("Websetup neu starten") }\n                                TextButton(onClick = { vm.stopWebAdmin() }) { Text("Websetup stoppen") }\n                            }''',
    1,
)
remote.write_text(s)


# Web page copy should describe the independent remote gate too.
web = java / "data/LocalWebAdmin.kt"
s = web.read_text()
s = s.replace(
    'Playlist-Verwaltung · lokal mit Websetup-PIN · Fernwartung nach Family-Freigabe über Tailscale',
    'Playlist-Verwaltung · lokal mit Websetup-PIN · Fernwartung nach separater Fernwartungs-PIN über Tailscale',
)
web.write_text(s)

print("Android v0.4.6 separate Family/remote PINs + zero-playlist Websetup/remote access patch applied")
