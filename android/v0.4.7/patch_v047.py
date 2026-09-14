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
# MainViewModel: unlocking remote maintenance starts the embedded Tailscale
# enrollment immediately. Existing enrolled nodes reconnect on every app start.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
old_unlock = '''    fun unlockRemoteMaintenance(pin: String): Boolean {\n        if (!prefs.verifyFixedRemoteMaintenancePin(pin)) return false\n        prefs.setRemoteMaintenanceUnlocked(true)\n        if (webAdmin == null) startWebAdmin()\n        set { it.copy(remoteMaintenanceUnlocked = true, error = "") }\n        refreshWebAdminAccess()\n        return true\n    }'''
require_once(s, old_unlock, "v0.4.6 remote unlock")
s = s.replace(
    old_unlock,
    '''    fun unlockRemoteMaintenance(pin: String): Boolean {\n        if (!prefs.verifyFixedRemoteMaintenancePin(pin)) return false\n        prefs.setRemoteMaintenanceUnlocked(true)\n        if (webAdmin == null) startWebAdmin()\n        set { it.copy(remoteMaintenanceUnlocked = true, error = "") }\n        RemoteTailscaleManager.provisionAndConnect(pin)\n        refreshWebAdminAccess()\n        return true\n    }''',
    1,
)

old_lock = '''    fun lockRemoteMaintenance() {\n        prefs.setRemoteMaintenanceUnlocked(false)\n        set { it.copy(remoteMaintenanceUnlocked = false, webAdminRemoteUrl = "") }\n    }'''
require_once(s, old_lock, "v0.4.6 remote lock")
s = s.replace(
    old_lock,
    '''    fun lockRemoteMaintenance() {\n        prefs.setRemoteMaintenanceUnlocked(false)\n        RemoteTailscaleManager.disconnect()\n        set { it.copy(remoteMaintenanceUnlocked = false, webAdminRemoteUrl = "") }\n    }''',
    1,
)

old_init = '''    init {\n        enforceFamilyThemeGate()\n        refreshProfiles()\n        val noPlaylist = _ui.value.playlists.isEmpty()\n        if (prefs.remoteMaintenanceUnlocked() || noPlaylist) startWebAdmin()\n        // Fernwartung/Websetup must be reachable before any playlist exists.\n        // Therefore a fresh installation starts here instead of trapping the\n        // user inside the playlist form. A direct on-device playlist button is\n        // available on this screen as well.\n        if (noPlaylist) set { it.copy(screen = Screen.WebAdmin) }\n    }'''
require_once(s, old_init, "v0.4.6 init")
s = s.replace(
    old_init,
    '''    init {\n        enforceFamilyThemeGate()\n        refreshProfiles()\n        val noPlaylist = _ui.value.playlists.isEmpty()\n        if (prefs.remoteMaintenanceUnlocked() || noPlaylist) startWebAdmin()\n        if (prefs.remoteMaintenanceUnlocked()) RemoteTailscaleManager.ensureConnected()\n        // Websetup and remote maintenance are available before the first playlist.\n        if (noPlaylist) set { it.copy(screen = Screen.WebAdmin) }\n    }''',
    1,
)
vm.write_text(s)


# ---------------------------------------------------------------------------
# Route the new automatic Tailscale status/setup screen.
# ---------------------------------------------------------------------------
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
old = '                Screen.WebAdmin -> V046WebAdminScreen(vm, accent, isTv)\n'
require_once(s, old, "v0.4.6 web route")
s = s.replace(old, '                Screen.WebAdmin -> V047WebAdminScreen(vm, accent, isTv)\n', 1)
app.write_text(s)

# Visible version labels.
home = java / "ui/V044Home.kt"
s = home.read_text().replace('0.4.6', '0.4.7')
home.write_text(s)

screens = java / "ui/Screens.kt"
s = screens.read_text().replace('Android v0.4.6', 'Android v0.4.7')
screens.write_text(s)

med = java / "data/MediathekClient.kt"
s = med.read_text().replace('EpiMediaHub-Android/0.4.6', 'EpiMediaHub-Android/0.4.7').replace('EpiMediaHub/0.4.6', 'EpiMediaHub/0.4.7')
med.write_text(s)

print("Android v0.4.7 automatic Raspberry/Tailscale provisioning patch applied")
