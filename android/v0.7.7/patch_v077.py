#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# Version.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 706', 'versionCode = 707', 'versionCode')
replace_once(gradle, 'versionName = "0.7.6"', 'versionName = "0.7.7"', 'versionName')

for rel in ["ui/V070Home.kt", "ui/Screens.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.7.6", "0.7.7"))
weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.6", "EpiMediaHub-Android/0.7.7"))


# ---------------------------------------------------------------------------
# Provisioning: explicit server-side revocation and local wipe.
# Existing Dashboard 0.7 multi-playlist code is preserved unchanged.
# ---------------------------------------------------------------------------
setup = java / "data/SetupCodeProvisioning.kt"
s = setup.read_text()

old_result = '''sealed class DeviceSyncResult {
    data class Success(
        val changed: Boolean,
        val configVersion: Int,
        val playlistUrl: String?
    ) : DeviceSyncResult()
    data class Error(val message: String, val retryable: Boolean = true) : DeviceSyncResult()
}
'''
new_result = '''sealed class DeviceSyncResult {
    data class Success(
        val changed: Boolean,
        val configVersion: Int,
        val playlistUrl: String?
    ) : DeviceSyncResult()
    data object Revoked : DeviceSyncResult()
    data class Error(val message: String, val retryable: Boolean = true) : DeviceSyncResult()
}
'''
if old_result not in s:
    raise SystemExit("DeviceSyncResult anchor missing")
s = s.replace(old_result, new_result, 1)

config_anchor = '''    fun configVersion(context: Context): Int = savedPayload(context)?.optInt("config_version", 0) ?: 0

    fun sync(context: Context): DeviceSyncResult {
'''
clear_fn = '''    fun configVersion(context: Context): Int = savedPayload(context)?.optInt("config_version", 0) ?: 0

    fun clearDeviceConfiguration(context: Context) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .remove(KEY_PAYLOAD)
            .remove(KEY_BASE_URL)
            .remove(KEY_PAIRING)
            .commit()

        val repo = PrefsRepository(context)
        repo.savePlaylists(emptyList())
        repo.activePlaylistId = ""
    }

    fun sync(context: Context): DeviceSyncResult {
'''
if config_anchor not in s:
    raise SystemExit("configVersion/sync anchor missing")
s = s.replace(config_anchor, clear_fn, 1)

old_status = '''            if (status !in 200..299) {
                return DeviceSyncResult.Error(
                    if (status == 401) "Gerät ist nicht mehr freigegeben" else "Sync-Serverfehler ($status)",
                    retryable = status != 401 && status !in 400..499
                )
            }
'''
new_status = '''            if (status == 401 || status == 403) {
                clearDeviceConfiguration(context)
                return DeviceSyncResult.Revoked
            }
            if (status !in 200..299) {
                return DeviceSyncResult.Error(
                    "Sync-Serverfehler ($status)",
                    retryable = status !in 400..499
                )
            }
'''
if old_status not in s:
    raise SystemExit("sync authorization anchor missing")
s = s.replace(old_status, new_status, 1)
setup.write_text(s)


# Background worker must understand Revoked as a completed terminal sync.
worker = java / "data/DashboardSyncWorker.kt"
w = worker.read_text()
old_worker = '''        when (val result = SetupCodeProvisioning.sync(applicationContext)) {
            is DeviceSyncResult.Success -> Result.success()
            is DeviceSyncResult.Error -> if (result.retryable) Result.retry() else Result.success()
        }
'''
new_worker = '''        when (val result = SetupCodeProvisioning.sync(applicationContext)) {
            is DeviceSyncResult.Success -> Result.success()
            DeviceSyncResult.Revoked -> Result.success()
            is DeviceSyncResult.Error -> if (result.retryable) Result.retry() else Result.success()
        }
'''
if old_worker not in w:
    raise SystemExit("DashboardSyncWorker anchor missing")
worker.write_text(w.replace(old_worker, new_worker, 1))


# ---------------------------------------------------------------------------
# App lifecycle:
# - unpaired TV and Mobile go to the exact same dashboard pairing screen
# - revoked foreground sessions refresh and go back to pairing immediately
# ---------------------------------------------------------------------------
app = java / "EpiMediaHubApp.kt"
a = app.read_text()

old_poll = '''            val sync = withContext(Dispatchers.IO) { SetupCodeProvisioning.sync(context.applicationContext) }
            if (sync is DeviceSyncResult.Success) vm.refreshProfiles()
            delay(30_000L)
'''
new_poll = '''            val sync = withContext(Dispatchers.IO) { SetupCodeProvisioning.sync(context.applicationContext) }
            when (sync) {
                is DeviceSyncResult.Success -> vm.refreshProfiles()
                DeviceSyncResult.Revoked -> {
                    vm.refreshProfiles()
                    vm.navigate(Screen.WebAdmin)
                }
                is DeviceSyncResult.Error -> Unit
            }
            delay(30_000L)
'''
if old_poll not in a:
    raise SystemExit("foreground dashboard polling anchor missing")
a = a.replace(old_poll, new_poll, 1)

context_anchor = '    val context = LocalContext.current\n'
if a.count(context_anchor) != 1:
    raise SystemExit(f"context anchor expected once, found {a.count(context_anchor)}")
startup = '''    var initialDashboardRedirectDone by remember { mutableStateOf(false) }
    LaunchedEffect(Unit) {
        if (!initialDashboardRedirectDone &&
            SetupCodeProvisioning.sessionToken(context.applicationContext) == null
        ) {
            initialDashboardRedirectDone = true
            vm.navigate(Screen.WebAdmin)
        }
    }
'''
a = a.replace(context_anchor, context_anchor + startup, 1)
app.write_text(a)


# ---------------------------------------------------------------------------
# Pairing surface: generate the 8-character pairing ticket automatically when
# an unpaired device reaches the common TV/Mobile Dashboard screen.
# ---------------------------------------------------------------------------
web = java / "ui/V047WebAdmin.kt"
v = web.read_text()
begin_end = '''    fun beginPairing() {
        if (busy) return
        busy = true
        message = ""
        scope.launch {
            when (val result = withContext(Dispatchers.IO) {
                SetupCodeProvisioning.startPairing(context.applicationContext)
            }) {
                is PairingStartResult.Success -> {
                    ticket = result.ticket
                    message = "Diesen Code im EpiMediaHub-Dashboard einem Kunden zuweisen."
                }
                is PairingStartResult.Error -> message = result.message
            }
            busy = false
        }
    }

'''
auto_pair = begin_end + '''    LaunchedEffect(connected, ticket?.pairingSecret) {
        if (!connected && ticket == null && !busy) beginPairing()
    }

'''
if begin_end not in v:
    raise SystemExit("beginPairing anchor missing")
v = v.replace(begin_end, auto_pair, 1)
web.write_text(v)


checks = [
    (gradle, 'versionName = "0.7.7"'),
    (gradle, 'versionCode = 707'),
    (setup, 'data object Revoked'),
    (setup, 'fun clearDeviceConfiguration(context: Context)'),
    (setup, 'repo.savePlaylists(emptyList())'),
    (setup, 'if (status == 401 || status == 403)'),
    (setup, 'MANAGED_PROFILE_PREFIX = "managed-dashboard-"'),
    (setup, 'config.optJSONArray("playlists")'),
    (worker, 'DeviceSyncResult.Revoked -> Result.success()'),
    (app, 'SetupCodeProvisioning.sessionToken(context.applicationContext) == null'),
    (app, 'vm.navigate(Screen.WebAdmin)'),
    (web, 'if (!connected && ticket == null && !busy) beginPairing()'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.7 marker {marker} in {path}")

print("Android v0.7.7 automatic TV/mobile pairing and remote dashboard device wipe applied")
