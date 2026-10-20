package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/** Native, admin-only, read-only coverage of the separate provider snapshot.
 * An unknown provider date is NOT the same as an unlimited or expired account.
 * This screen never contacts IPTV servers or saves provider credentials.
 */
private data class UnknownPlaylist(val name:String,val customers:List<String>)
private data class ExpiryCoverageState(val total:Int,val confirmed:Int,
    val missing:Int,val unknown:List<UnknownPlaylist>)

private fun readExpiryCoverage():ExpiryCoverageState {
    val base="https://admin.epimediahub.com"
    val cookie=CookieManager.getInstance().getCookie(base).orEmpty()
    if(cookie.isBlank()) throw IllegalStateException("Admin-Sitzung fehlt")
    val conn=URL("$base/admin/mobile/reports/expiry/coverage")
        .openConnection() as HttpURLConnection
    conn.connectTimeout=8000
    conn.readTimeout=16000
    conn.requestMethod="GET"
    conn.instanceFollowRedirects=false
    conn.setRequestProperty("Cookie",cookie)
    conn.setRequestProperty("Accept","application/json")
    conn.setRequestProperty("Cache-Control","no-store")
    try {
        if(conn.responseCode!=200) throw IllegalStateException(
            if(conn.responseCode==401 || conn.responseCode==403)
                "Admin-Sitzung abgelaufen"
            else "Kontenstatus noch nicht verfügbar")
        if(conn.contentType?.substringBefore(";")!="application/json")
            throw IllegalStateException("Unerwartete Serverantwort")
        val data=conn.inputStream.use { input ->
            val out=java.io.ByteArrayOutputStream()
            val buffer=ByteArray(4096)
            while(true){
                val n=input.read(buffer)
                if(n<0) break
                if(out.size()+n>600000)
                    throw IllegalStateException("Antwort zu groß")
                out.write(buffer,0,n)
            }
            out.toString("UTF-8")
        }
        val root=JSONObject(data)
        val total=root.getInt("active_accounts")
        val confirmed=root.getInt("confirmed_accounts")
        val missing=root.getInt("unverified_accounts")
        if(total !in 0..10000 || confirmed !in 0..total
            || missing!=total-confirmed)
            throw IllegalStateException("Ungültige Kontenstatistik")
        val groups=root.getJSONArray("playlists")
        if(groups.length()>1000)
            throw IllegalStateException("Zu viele Playlists")
        val unknown=mutableListOf<UnknownPlaylist>()
        var totalEntries=0
        for(i in 0 until groups.length()){
            val g=groups.getJSONObject(i)
            val name=g.getString("name").take(160)
            val entries=g.getJSONArray("entries")
            if(entries.length()>10000)
                throw IllegalStateException("Zu viele Kunden")
            val customers=mutableListOf<String>()
            for(j in 0 until entries.length()){
                val row=entries.getJSONObject(j)
                totalEntries++
                when(row.getString("status")){
                    "unverified" -> customers.add(row.getString("customer").take(160))
                    "confirmed" -> Unit
                    else -> throw IllegalStateException("Ungültiger Kontostatus")
                }
            }
            if(customers.isNotEmpty())
                unknown.add(UnknownPlaylist(name,customers))
        }
        if(totalEntries!=total || unknown.sumOf{it.customers.size}!=missing)
            throw IllegalStateException("Unvollständige Kontenstatistik")
        return ExpiryCoverageState(total,confirmed,missing,unknown)
    } finally { conn.disconnect() }
}

@Composable
internal fun NativeExpiryCoverage(){
    var value by remember { mutableStateOf<ExpiryCoverageState?>(null) }
    var error by remember { mutableStateOf("") }
    LaunchedEffect(Unit) {
        thread(name="epi-admin-expiry-coverage") {
            val result=try { readExpiryCoverage() to "" }
            catch(e:Exception){ null to (
                e.message?.take(100) ?: "Kontenstatus nicht verfügbar") }
            Handler(Looper.getMainLooper()).post{
                value=result.first
                error=result.second
            }
        }
    }
    if(error.isNotBlank())
        Text("Datenabdeckung: $error",
            color=MaterialTheme.colorScheme.error,
            style=MaterialTheme.typography.bodySmall)
    value?.let { state ->
        ElevatedCard(Modifier.fillMaxWidth()){
            Column(Modifier.padding(14.dp),
                verticalArrangement=Arrangement.spacedBy(7.dp)){
                Text("Ablaufdaten: ${state.confirmed} von ${state.total} Konten bestätigt",
                    fontWeight=FontWeight.Bold)
                if(state.missing>0){
                    Text("${state.missing} Konten haben kein aktuell bestätigtes Ablaufdatum. "+
                        "Die Monatsübersicht ist möglicherweise unvollständig. "+
                        "Unbekannt bedeutet nicht abgelaufen.",
                        color=MaterialTheme.colorScheme.error,
                        style=MaterialTheme.typography.bodySmall)
                    state.unknown.forEach { group ->
                        Text(group.name,fontWeight=FontWeight.SemiBold)
                        group.customers.forEach { customer ->
                            Text("• $customer — Ablauf unbekannt",
                                style=MaterialTheme.typography.bodySmall)
                        }
                    }
                } else {
                    Text("Für alle aktiven Konten liegen aktuelle Ablaufdaten vor.",
                        style=MaterialTheme.typography.bodySmall)
                }
            }
        }
    }
}
