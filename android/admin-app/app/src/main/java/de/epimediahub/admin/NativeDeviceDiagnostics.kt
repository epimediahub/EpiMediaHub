package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/** Read-only native diagnostics. Streaming, device IDs and provider secrets stay server-side. */
internal object NativeDeviceDiagnostics {
    private const val BASE="https://admin.epimediahub.com"
    private val main=Handler(Looper.getMainLooper())

    data class Fault(val code:String, val component:String, val version:String, val reported:String)
    data class Status(
        val name:String, val platform:String, val enabled:Boolean,
        val lastSeen:String, val lastSync:String, val syncStatus:String,
        val serverVersion:String, val appliedVersion:String,
        val faults:List<Fault>
    )

    fun load(deviceRowId:String,done:(Status?,String)->Unit) {
        if (!Regex("[1-9][0-9]{0,17}").matches(deviceRowId)) {
            main.post { done(null,"Ungültiges Gerät.") }
            return
        }
        thread(name="epi-native-device-diagnostics") {
            var value:Status?=null
            val message=try {
                val cookie=CookieManager.getInstance().getCookie(BASE) ?: ""
                if (cookie.isBlank()) "Admin-Anmeldung erforderlich."
                else {
                    val link="$BASE/admin/mobile/management/devices/$deviceRowId/diagnostics"
                    val conn=(URL(link).openConnection() as HttpURLConnection).apply {
                        requestMethod="GET"
                        instanceFollowRedirects=false
                        connectTimeout=8000
                        readTimeout=9000
                        setRequestProperty("Cookie",cookie)
                        setRequestProperty("Accept","application/json")
                        setRequestProperty("Cache-Control","no-store")
                    }
                    try {
                        if (conn.responseCode!=200) "Diagnose derzeit nicht verfügbar."
                        else {
                            val payload=JSONObject(conn.inputStream.bufferedReader().use {
                                it.readText().take(65536)
                            })
                            val issues=payload.optJSONArray("recent_errors")
                            if (issues!=null && issues.length()>15)
                                throw IllegalStateException("unbounded error feed")
                            val faults=if (issues==null) emptyList() else
                                (0 until issues.length()).map { pos ->
                                    val item=issues.getJSONObject(pos)
                                    Fault(
                                        item.optString("code").take(60),
                                        item.optString("component").take(60),
                                        item.optString("app_version").take(35),
                                        item.optString("reported_at").take(45)
                                    )
                                }
                            value=Status(
                                name=payload.optString("name").take(150),
                                platform=payload.optString("platform").take(40),
                                enabled=payload.optBoolean("enabled",false),
                                lastSeen=payload.optString("last_seen_at").take(45),
                                lastSync=payload.optString("last_sync_at").take(45),
                                syncStatus=payload.optString("last_sync_status").take(30),
                                serverVersion=if (payload.isNull("config_version")) "—"
                                    else payload.optString("config_version","—"),
                                appliedVersion=if (payload.isNull("applied_config_version")) "—"
                                    else payload.optString("applied_config_version","—"),
                                faults=faults
                            )
                            ""
                        }
                    } finally { conn.disconnect() }
                }
            } catch (_:Exception) {
                "Geräteinformationen konnten nicht sicher geladen werden."
            }
            val result=value
            main.post { done(result,message) }
        }
    }
}

@Composable
internal fun NativeDeviceDiagnosticsDialog(
    deviceRowId:String,
    close:()->Unit
) {
    var status by remember(deviceRowId) {
        mutableStateOf<NativeDeviceDiagnostics.Status?>(null)
    }
    var message by remember(deviceRowId) { mutableStateOf("") }
    var busy by remember(deviceRowId) { mutableStateOf(true) }
    LaunchedEffect(deviceRowId) {
        NativeDeviceDiagnostics.load(deviceRowId) { received,error ->
            status=received
            message=error
            busy=false
        }
    }
    AlertDialog(
        onDismissRequest=close,
        title={ Text("Gerätediagnose") },
        text={
            Column(Modifier.heightIn(max=480.dp).verticalScroll(rememberScrollState()),
                verticalArrangement=Arrangement.spacedBy(9.dp)) {
                if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
                if (message.isNotBlank()) Text(message)
                status?.let { state ->
                    Text(state.name,style=MaterialTheme.typography.titleMedium)
                    Text(state.platform+" · "+if (state.enabled) "Aktiv" else "Deaktiviert")
                    Text("Zuletzt gesehen: "+state.lastSeen.ifBlank { "Keine Angabe" })
                    Text("Letzte Synchronisierung: "+state.lastSync.ifBlank { "Keine Angabe" })
                    Text("Sync-Status: "+state.syncStatus)
                    Text("Konfigurationsstand Server / Gerät: "+
                        state.serverVersion+" / "+state.appliedVersion)
                    HorizontalDivider()
                    Text("Aktuelle Fehlerereignisse",
                        style=MaterialTheme.typography.titleSmall)
                    if (state.faults.isEmpty()) Text("Keine Fehlerereignisse vorhanden.")
                    state.faults.forEach { issue ->
                        Text("• "+issue.component+" · "+issue.code)
                        Text(issue.version+" · "+issue.reported,
                            style=MaterialTheme.typography.bodySmall)
                    }
                }
            }
        },
        confirmButton={ TextButton(onClick=close) { Text("Schließen") } }
    )
}
