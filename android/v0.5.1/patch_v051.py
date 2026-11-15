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
# Version metadata.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
require_once(s, 'versionCode = 500', 'v0.5.0 versionCode')
require_once(s, 'versionName = "0.5.0"', 'v0.5.0 versionName')
s = s.replace('versionCode = 500', 'versionCode = 501', 1)
s = s.replace('versionName = "0.5.0"', 'versionName = "0.5.1"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.5.0", "0.5.1"))


# ---------------------------------------------------------------------------
# Provisioning: fixed 12-character dashboard code, auto formatting only in the
# provisioning surface, and actually apply dashboard M3U/Xtream configuration
# to the app's playlist repository.
# ---------------------------------------------------------------------------
provision = java / "data/SetupCodeProvisioning.kt"
s = provision.read_text()
import_anchor = 'import android.provider.Settings\n'
require_once(s, import_anchor, 'SetupCodeProvisioning imports')
s = s.replace(
    import_anchor,
    import_anchor + 'import de.epimediahub.app.model.PlaylistProfile\nimport de.epimediahub.app.model.PlaylistType\n',
    1,
)
old = ' fun normalize(raw:String)=raw.trim().uppercase(Locale.ROOT).replace(Regex("[^A-Z0-9]"),"").chunked(4).joinToString("-")\n fun isValid(code:String)=normalize(code).replace("-","").length in 8..16\n'
require_once(s, old, 'setup code normalization')
new = ''' fun rawCode(raw:String)=raw.uppercase(Locale.ROOT).replace(Regex("[^A-Z0-9]"),"").take(12)\n fun normalize(raw:String)=rawCode(raw).chunked(4).joinToString("-")\n fun isValid(code:String)=rawCode(code).length==12\n'''
s = s.replace(old, new, 1)

old_success = 'when(status){in 200..299->{val payload=JSONObject(text);context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_PAYLOAD,payload.toString()).putString(KEY_BASE_URL,cleanBase).apply();SetupCodeResult.Success(payload)};404->SetupCodeResult.Error("Einrichtungscode ungültig");409->SetupCodeResult.Error("Einrichtung wurde bereits verwendet");410->SetupCodeResult.Error("Einrichtungscode ist abgelaufen");else->SetupCodeResult.Error("Serverfehler ($status)")}\n'
require_once(s, old_success, 'redeem success handler')
new_success = 'when(status){in 200..299->{val payload=JSONObject(text);context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_PAYLOAD,payload.toString()).putString(KEY_BASE_URL,cleanBase).commit();applyConfigToApp(context,payload.optJSONObject("config")?:JSONObject());SetupCodeResult.Success(payload)};404->SetupCodeResult.Error("Einrichtungscode ungültig");409->SetupCodeResult.Error("Einrichtung wurde bereits verwendet");410->SetupCodeResult.Error("Einrichtungscode ist abgelaufen");else->SetupCodeResult.Error("Serverfehler ($status)")}\n'
s = s.replace(old_success, new_success, 1)

old_sync_start = '  val base=provisioningBaseUrl(context)?:return DeviceSyncResult.Error("Gerät ist noch nicht eingerichtet")\n  val token=sessionToken(context)?:return DeviceSyncResult.Error("Geräteschlüssel fehlt")\n  return try {\n   val conn=connection(base.trimEnd(\'/\')+"/v1/device/config","GET",token); val status=conn.responseCode; val text=read(conn,status)\n'
require_once(s, old_sync_start, 'device sync request')
new_sync_start = '  val base=provisioningBaseUrl(context)\n  val token=sessionToken(context)?:return DeviceSyncResult.Error("Gerät ist noch nicht eingerichtet")\n  return try {\n   val known=configVersion(context); val conn=connection(base.trimEnd(\'/\')+"/v1/device/config?version=$known","GET",token); val status=conn.responseCode; val text=read(conn,status)\n'
s = s.replace(old_sync_start, new_sync_start, 1)

old_sync_store = '   context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_PAYLOAD,merged.toString()).commit()\n   reportSync(context,base,token,version,"ok","")\n'
require_once(s, old_sync_store, 'device sync store')
new_sync_store = '   context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_PAYLOAD,merged.toString()).commit()\n   applyConfigToApp(context,config)\n   reportSync(context,base,token,version,"ok","")\n'
s = s.replace(old_sync_store, new_sync_store, 1)

report_anchor = ' private fun reportSync(context:Context,base:String,token:String,version:Int,statusValue:String,error:String){\n'
require_once(s, report_anchor, 'reportSync anchor')
apply_fn = r''' private fun applyConfigToApp(context:Context,config:JSONObject){
  val type=config.optString("playlist_type","").uppercase(Locale.ROOT)
  val name=config.optString("playlist_name","EpiMediaHub Dashboard").ifBlank{"EpiMediaHub Dashboard"}
  val url=config.optString("playlist_url","").trim()
  val server=config.optString("xtream_server","").trim().trimEnd('/')
  val username=config.optString("xtream_username","").trim()
  val password=config.optString("xtream_password","")
  val output=config.optString("xtream_output","ts").ifBlank{"ts"}
  val profile=when {
   type=="XTREAM" && server.isNotBlank() && username.isNotBlank() && password.isNotBlank() -> PlaylistProfile("managed-dashboard",name,"",PlaylistType.XTREAM,server,username,password,output)
   url.isNotBlank() -> PlaylistProfile("managed-dashboard",name,url,PlaylistType.M3U)
   else -> null
  } ?: return
  val repo=PrefsRepository(context)
  val local=repo.loadPlaylists().filterNot{it.id=="managed-dashboard"}
  repo.savePlaylists(listOf(profile)+local)
  repo.activePlaylistId=profile.id
 }
'''
s = s.replace(report_anchor, apply_fn + report_anchor, 1)
provision.write_text(s)


# ---------------------------------------------------------------------------
# A dedicated Fire-TV friendly dashboard-code dialog. It explains exactly what
# belongs in the field, auto-inserts separators after 4/8 characters, hides the
# software keyboard once 12 characters are complete and moves focus to Connect.
# Back/Cancel always dismisses it.
# ---------------------------------------------------------------------------
(java / "ui/V051DashboardConnect.kt").write_text(r'''package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import de.epimediahub.app.data.SetupCodeProvisioning
import de.epimediahub.app.data.SetupCodeResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun V051DashboardConnectDialog(
    onDismiss: () -> Unit,
    onProvisioned: () -> Unit
) {
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current
    val keyboard = LocalSoftwareKeyboardController.current
    val scope = rememberCoroutineScope()
    val codeFocus = remember { FocusRequester() }
    val connectFocus = remember { FocusRequester() }
    var code by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var fieldFocused by remember { mutableStateOf(false) }

    fun close() {
        keyboard?.hide()
        focusManager.clearFocus(force = true)
        onDismiss()
    }

    val submit: () -> Unit = {
        if (!busy && SetupCodeProvisioning.isValid(code)) {
            keyboard?.hide()
            focusManager.clearFocus(force = true)
            busy = true
            error = null
            scope.launch {
                val result = withContext(Dispatchers.IO) {
                    SetupCodeProvisioning.redeem(
                        context.applicationContext,
                        SetupCodeProvisioning.PRODUCTION_BASE_URL,
                        code
                    )
                }
                busy = false
                when (result) {
                    is SetupCodeResult.Success -> onProvisioned()
                    is SetupCodeResult.Error -> {
                        error = result.message
                        runCatching { codeFocus.requestFocus() }
                    }
                }
            }
        }
    }

    LaunchedEffect(Unit) {
        delay(150)
        runCatching { codeFocus.requestFocus() }
    }
    LaunchedEffect(code) {
        if (SetupCodeProvisioning.rawCode(code).length == 12 && fieldFocused) {
            keyboard?.hide()
            focusManager.clearFocus(force = true)
            delay(100)
            runCatching { connectFocus.requestFocus() }
        }
    }

    BackHandler(enabled = true) { close() }

    AlertDialog(
        onDismissRequest = { close() },
        title = { Text("Mit Dashboard verbinden") },
        text = {
            Column {
                Text("Gib den 12-stelligen Einrichtungscode ein, den du im EpiMediaHub-Dashboard für dieses Gerät erzeugt hast.")
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = code,
                    onValueChange = {
                        code = SetupCodeProvisioning.normalize(it)
                        error = null
                    },
                    enabled = !busy,
                    singleLine = true,
                    label = { Text("Einrichtungscode") },
                    placeholder = { Text("ABCD-EFGH-IJKL") },
                    supportingText = { Text("Bindestriche werden automatisch gesetzt.") },
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Ascii, imeAction = ImeAction.Done),
                    keyboardActions = KeyboardActions(onDone = { submit() }),
                    modifier = Modifier
                        .fillMaxWidth()
                        .focusRequester(codeFocus)
                        .onFocusChanged { fieldFocused = it.isFocused }
                )
                error?.let {
                    Spacer(Modifier.height(6.dp))
                    Text(it, color = MaterialTheme.colorScheme.error)
                }
            }
        },
        confirmButton = {
            Button(
                enabled = !busy && SetupCodeProvisioning.isValid(code),
                onClick = submit,
                modifier = Modifier.focusRequester(connectFocus)
            ) { Text(if (busy) "Wird verbunden …" else "Verbinden") }
        },
        dismissButton = {
            TextButton(enabled = !busy, onClick = { close() }) { Text("Abbrechen") }
        }
    )
}
''')


# ---------------------------------------------------------------------------
# MainViewModel: expose a side-effect-free PIN check for Dashboard linking.
# The old Tailscale unlock method remains available as a separate optional path.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()
unlock_anchor = '    fun unlockRemoteMaintenance(pin: String): Boolean {\n'
require_once(s, unlock_anchor, 'unlockRemoteMaintenance anchor')
s = s.replace(
    unlock_anchor,
    '    fun verifyRemoteMaintenancePin(pin: String): Boolean = prefs.verifyFixedRemoteMaintenancePin(pin)\n\n' + unlock_anchor,
    1,
)
vm.write_text(s)


# ---------------------------------------------------------------------------
# Websetup/Fernwartung screen: Dashboard linking is optional and starts only
# after the user explicitly presses Connect. Remove v0.4.11's automatic PIN
# popup and chain PIN -> dashboard code without launching interactive Tailscale.
# ---------------------------------------------------------------------------
web = java / "ui/V047WebAdmin.kt"
s = web.read_text()
import_anchor = 'import androidx.compose.ui.graphics.Color\n'
require_once(s, import_anchor, 'V047WebAdmin Color import')
s = s.replace(import_anchor, import_anchor + 'import androidx.compose.ui.platform.LocalContext\n', 1)
app_import_anchor = 'import de.epimediahub.app.Screen\n'
require_once(s, app_import_anchor, 'V047WebAdmin Screen import')
s = s.replace(app_import_anchor, app_import_anchor + 'import de.epimediahub.app.data.SetupCodeProvisioning\n', 1)
state_anchor = '    var showRemoteUnlock by remember { mutableStateOf(false) }\n'
require_once(s, state_anchor, 'V047WebAdmin state anchor')
s = s.replace(
    state_anchor,
    state_anchor + '''    val context = LocalContext.current\n    var dashboardConnected by remember { mutableStateOf(SetupCodeProvisioning.sessionToken(context) != null) }\n    var showDashboardPin by remember { mutableStateOf(false) }\n    var showDashboardCode by remember { mutableStateOf(false) }\n''',
    1,
)
auto_popup = '''\n    // A migrated installation may already be marked as remote-maintenance\n    // unlocked while native Tailscale has never been authenticated. Surface\n    // the only required action immediately instead of leaving it below the\n    // fold on short TV layouts.\n    LaunchedEffect(u.remoteMaintenanceUnlocked, ts.phase) {\n        if (u.remoteMaintenanceUnlocked && ts.phase == RemoteTailscaleManager.Phase.PIN_REQUIRED) {\n            showRemoteUnlock = true\n        }\n    }\n'''
require_once(s, auto_popup, 'automatic PIN popup')
s = s.replace(auto_popup, '\n', 1)

divider_anchor = '                            HorizontalDivider(Modifier.padding(vertical = if (compact) 5.dp else 9.dp), color = Color.White.copy(.12f))\n'
require_once(s, divider_anchor, 'V047 dashboard insertion point')
dashboard_block = r'''                            Text("EPIMEDIAHUB DASHBOARD", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)
                            if (dashboardConnected) {
                                Text("Verbunden · Playlist-Zuweisungen werden automatisch synchronisiert", color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)
                                TextButton(onClick = { showDashboardPin = true }) { Text("Neu verbinden") }
                            } else {
                                Text("Optional: Gerät mit deinem zentralen Dashboard verbinden. Erst nach Klick auf Verbinden wird die PIN abgefragt.", color = Color.White.copy(.78f), fontSize = 11.sp, lineHeight = 15.sp)
                                Spacer(Modifier.height(if (compact) 4.dp else 7.dp))
                                Button(
                                    onClick = { showDashboardPin = true },
                                    colors = ButtonDefaults.buttonColors(containerColor = accent),
                                    shape = RoundedCornerShape(12.dp)
                                ) {
                                    Icon(Icons.Default.Computer, null, tint = Color.Black, modifier = Modifier.size(18.dp))
                                    Spacer(Modifier.width(7.dp))
                                    Text("Verbinden", color = Color.Black, fontWeight = FontWeight.Black)
                                }
                            }

'''
s = s.replace(divider_anchor, dashboard_block + divider_anchor, 1)

end_anchor = '''    if (showRemoteUnlock) {\n        V046FamilyPinDialog('''
require_once(s, end_anchor, 'existing remote PIN dialog')
# Keep the existing optional Tailscale dialog untouched and append Dashboard
# dialogs at the end of the composable, just before its final closing brace.
insert = r'''

    if (showDashboardPin) {
        V046FamilyPinDialog(
            title = "Dashboard verbinden",
            message = "Gib zuerst die Fernwartungs-PIN ein. Danach öffnet sich die Eingabe für den Einrichtungscode aus deinem Dashboard.",
            pinLabel = "Fernwartungs-PIN",
            errorText = "Fernwartungs-PIN ist falsch.",
            onDismiss = { showDashboardPin = false },
            onVerify = { pin ->
                val ok = vm.verifyRemoteMaintenancePin(pin)
                if (ok) {
                    showDashboardPin = false
                    showDashboardCode = true
                }
                ok
            }
        )
    }

    if (showDashboardCode) {
        V051DashboardConnectDialog(
            onDismiss = { showDashboardCode = false },
            onProvisioned = {
                dashboardConnected = true
                showDashboardCode = false
                vm.refreshProfiles()
            }
        )
    }
'''
# The file's final brace closes V047WebAdminScreen.
if not s.rstrip().endswith('}'):
    raise SystemExit('V047WebAdmin final brace missing')
pos = s.rfind('}')
s = s[:pos] + insert + s[pos:]
web.write_text(s)


# ---------------------------------------------------------------------------
# Poll central configuration while a dashboard session exists. This makes a
# playlist edited in the Dashboard arrive on Fire TV without restarting the app.
# ---------------------------------------------------------------------------
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
data_import = 'import de.epimediahub.app.data.AppUpdateManager\n'
require_once(s, data_import, 'EpiMediaHubApp data import')
s = s.replace(data_import, data_import + 'import de.epimediahub.app.data.DeviceSyncResult\nimport de.epimediahub.app.data.SetupCodeProvisioning\n', 1)
coroutine_import = 'import kotlinx.coroutines.launch\n'
require_once(s, coroutine_import, 'EpiMediaHubApp coroutine import')
s = s.replace(coroutine_import, 'import kotlinx.coroutines.Dispatchers\nimport kotlinx.coroutines.delay\nimport kotlinx.coroutines.launch\nimport kotlinx.coroutines.withContext\n', 1)
context_anchor = '    val context = LocalContext.current\n'
require_once(s, context_anchor, 'EpiMediaHubApp context anchor')
s = s.replace(
    context_anchor,
    context_anchor + '''    LaunchedEffect(context) {\n        while (true) {\n            val sync = withContext(Dispatchers.IO) { SetupCodeProvisioning.sync(context.applicationContext) }\n            if (sync is DeviceSyncResult.Success && sync.changed) vm.refreshProfiles()\n            delay(30_000L)\n        }\n    }\n''',
    1,
)
app.write_text(s)

print("Android v0.5.1 Fire TV dashboard setup and managed playlist sync patch applied")
