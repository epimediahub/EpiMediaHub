package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AccountCircle
import androidx.compose.material.icons.outlined.Business
import androidx.compose.material.icons.outlined.ChevronRight
import androidx.compose.material.icons.outlined.Refresh
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Shield
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * Native Android management presentation, backed exclusively by authenticated JSON.
 *
 * No HTML and no synthetic customer, reseller, license or VPN data.
 * Until server contracts are installed, requests return an explicit unavailable state.
 * All writes must be added only after server-side roles, CSRF, audit and idempotency
 * are available; buttons deliberately cannot trigger a guessed legacy endpoint.
 */
internal object NativeManagementApi {
    private const val BASE = "https://admin.epimediahub.com"
    private val main = Handler(Looper.getMainLooper())
    private const val LIMIT = 100
    private const val RESPONSE_LIMIT = 512 * 1024

    data class Overview(
        val customers: Int?,
        val resellers: Int?,
        val activeLicenses: Int?,
        val vpnActive: Int?
    )

    data class Entry(
        val id: String,
        val name: String,
        val subtitle: String,
        val playlistCount: Int?,
        val expiresEpoch: Long?
    )

    data class Result(
        val overview: Overview?,
        val customers: List<Entry>,
        val resellers: List<Entry>,
        val error: String?,
        val authenticated: Boolean,
        val loaded: Boolean
    )

    private class Status(val code: Int) : RuntimeException()

    private fun read(path: String, cookie: String): JSONObject {
        require(path in listOf(
            "/admin/mobile/management/overview",
            "/admin/mobile/management/customers",
            "/admin/mobile/management/resellers"
        ))
        val conn = (URL(BASE + path).openConnection() as HttpURLConnection).apply {
            instanceFollowRedirects = false
            connectTimeout = 8000
            readTimeout = 12000
            requestMethod = "GET"
            setRequestProperty("Cookie", cookie)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-store")
        }
        try {
            if (conn.responseCode != 200) throw Status(conn.responseCode)
            if (conn.contentType?.substringBefore(";") != "application/json") {
                throw IllegalStateException("Invalid content type")
            }
            val text = conn.inputStream.bufferedReader().use { source ->
                val buffer = CharArray(8192)
                val value = StringBuilder()
                while (true) {
                    val size = source.read(buffer)
                    if (size < 0) break
                    value.append(buffer, 0, size)
                    if (value.length > RESPONSE_LIMIT) throw IllegalStateException("Response too large")
                }
                value.toString()
            }
            return JSONObject(text)
        } finally {
            conn.disconnect()
        }
    }

    private fun count(data: JSONObject, key: String): Int? {
        if (data.isNull(key)) return null
        val count = data.optInt(key, -1)
        return count.takeIf { it >= 0 }
    }

    private fun entries(data: JSONObject, key: String): List<Entry> {
        val array: JSONArray = data.optJSONArray(key)
            ?: throw IllegalStateException("Missing server data")
        if (array.length() > LIMIT) throw IllegalStateException("Unbounded server list")
        val found = mutableListOf<Entry>()
        repeat(array.length()) { i ->
            val obj = array.getJSONObject(i)
            val id = obj.getString("id").trim()
            val name = obj.getString("name").trim()
            if (id.isEmpty() || name.isEmpty() || id.length > 120 || name.length > 160) {
                throw IllegalStateException("Invalid account item")
            }
            val epoch = if (obj.isNull("expires_at_epoch")) null
                else obj.optLong("expires_at_epoch", -1L).takeIf { it >= 0 }
            found += Entry(
                id = id,
                name = name,
                subtitle = obj.optString("subtitle", "").take(140),
                playlistCount = count(obj, "playlist_count"),
                expiresEpoch = epoch
            )
        }
        return found
    }

    fun load(cookie: String, done: (Result) -> Unit) {
        if (cookie.isBlank()) {
            main.post { done(Result(null, emptyList(), emptyList(),
                "Bitte als Administrator anmelden.", false, false)) }
            return
        }
        thread(name = "epi-admin-native-management") {
            val result = try {
                val overview = read("/admin/mobile/management/overview", cookie)
                val customers = read("/admin/mobile/management/customers", cookie)
                val resellers = read("/admin/mobile/management/resellers", cookie)
                Result(
                    Overview(count(overview, "customers"), count(overview, "resellers"),
                        count(overview, "active_licenses"), count(overview, "active_vpns")),
                    entries(customers, "customers"),
                    entries(resellers, "resellers"),
                    null, true, true
                )
            } catch (error: Status) {
                val message = when (error.code) {
                    401, 403 -> "Admin-Sitzung abgelaufen. Bitte erneut anmelden."
                    404, 501 -> "Die native Verwaltungs-API ist serverseitig noch nicht aktiviert."
                    else -> "Admin-Verwaltung derzeit nicht erreichbar (HTTP ${error.code})."
                }
                Result(null, emptyList(), emptyList(), message, error.code !in (401,403), false)
            } catch (_: Exception) {
                Result(null, emptyList(), emptyList(),
                    "Verwaltungsdaten konnten nicht sicher geladen werden.", true, false)
            }
            main.post { done(result) }
        }
    }
}

private val Navy = Color(0xFF080E1B)
private val SurfaceNavy = Color(0xFF101B2D)
private val LighterNavy = Color(0xFF152238)
private val LineNavy = Color(0xFF27374D)
private val AccentBlue = Color(0xFF59C9FA)
private val Foreground = Color(0xFFF1F6FF)
private val Secondary = Color(0xFFA1B2CB)

@Composable
internal fun NativeManagementScreen(
    data: NativeManagementApi.Result?,
    loading: Boolean,
    refresh: () -> Unit,
    signIn: () -> Unit,
    openEpiscene: () -> Unit,
    openAlerts: () -> Unit,
    modifier: Modifier = Modifier
) {
    var section by remember { mutableIntStateOf(0) }
    var query by remember { mutableStateOf("") }
    var selected by remember { mutableStateOf<NativeManagementApi.Entry?>(null) }

    Column(modifier = modifier.fillMaxWidth().background(Navy).padding(horizontal = 18.dp)) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(top = 17.dp, bottom = 14.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text("Verwaltung", fontSize = 27.sp, color = Foreground,
                    fontWeight = FontWeight.ExtraBold)
                Text("EpiMediaHub · Native Admin", color = Secondary, fontSize = 12.sp)
            }
            OutlinedIconButton(onClick = refresh, enabled = !loading,
                border = BorderStroke(1.dp, LineNavy)) {
                Icon(Icons.Outlined.Refresh, contentDescription = "Aktualisieren",
                    tint = AccentBlue)
            }
        }
        if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        if (data?.loaded != true) {
            Surface(
                shape = RoundedCornerShape(18.dp), color = SurfaceNavy,
                border = BorderStroke(1.dp, LineNavy)
            ) {
                Column(Modifier.fillMaxWidth().padding(20.dp),
                    verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Icon(Icons.Outlined.Shield, contentDescription = null,
                        tint = AccentBlue, modifier = Modifier.size(28.dp))
                    Text("Verwaltung noch nicht verbunden", color = Foreground,
                        fontWeight = FontWeight.Bold, fontSize = 17.sp)
                    Text(data?.error ?: "Gesicherte Verwaltungsdaten werden geladen.",
                        color = Secondary, fontSize = 13.sp)
                    if (data?.authenticated == false) {
                        Button(onClick = signIn) { Text("Administrator anmelden") }
                    }
                    OutlinedButton(onClick = refresh, enabled = !loading) {
                        Text("Verbindung erneut prüfen")
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
            Text("Keine erfundenen Kunden, Lizenzen oder Live-Zähler. Erst nach einer "
                + "authentifizierten Serverantwort werden Verwaltungsdaten angezeigt.",
                color = Secondary, fontSize = 12.sp)
            return@Column
        }
        val overview = data.overview
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth()) {
            ManagementMetric("Kunden", overview?.customers, Modifier.weight(1f))
            ManagementMetric("Reseller", overview?.resellers, Modifier.weight(1f))
        }
        Spacer(Modifier.height(8.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth()) {
            ManagementMetric("App-Lizenzen", overview?.activeLicenses, Modifier.weight(1f))
            ManagementMetric("VPN aktiv", overview?.vpnActive, Modifier.weight(1f))
        }
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = section == 0, onClick = { section = 0; query = "" },
                label = { Text("Kunden") })
            FilterChip(selected = section == 1, onClick = { section = 1; query = "" },
                label = { Text("Reseller") })
        }
        OutlinedTextField(
            value = query,
            onValueChange = { query = it.take(80) },
            label = { Text(if (section == 0) "Kunden suchen" else "Reseller suchen") },
            leadingIcon = { Icon(Icons.Outlined.Search, null) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(vertical = 7.dp)
        )
        val all = if (section == 0) data.customers else data.resellers
        val filtered = all.filter { it.name.contains(query, ignoreCase = true) ||
            it.subtitle.contains(query, ignoreCase = true) }
        if (filtered.isEmpty()) {
            Text("Keine Einträge für diese Auswahl.", color = Secondary,
                modifier = Modifier.padding(12.dp))
        }
        LazyColumn(verticalArrangement = Arrangement.spacedBy(9.dp)) {
            items(filtered, key = { it.id }) { item ->
                Surface(
                    modifier = Modifier.fillMaxWidth().clickable { selected = item },
                    shape = RoundedCornerShape(15.dp), color = SurfaceNavy,
                    border = BorderStroke(1.dp, LineNavy)
                ) {
                    Row(Modifier.padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(if (section == 0) Icons.Outlined.AccountCircle
                             else Icons.Outlined.Business, null, tint = AccentBlue)
                        Spacer(Modifier.width(11.dp))
                        Column(Modifier.weight(1f)) {
                            Text(item.name, color = Foreground,
                                fontWeight = FontWeight.Bold,
                                maxLines = 1, overflow = TextOverflow.Ellipsis)
                            Text(item.subtitle, color = Secondary, fontSize = 12.sp,
                                maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                        Icon(Icons.Outlined.ChevronRight, null, tint = Secondary)
                    }
                }
            }
        }
    }

    selected?.let { item ->
        AlertDialog(
            onDismissRequest = { selected = null },
            title = { Text(item.name) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                    Text(item.subtitle.ifBlank { "Keine weiteren Details verfügbar." })
                    Text("Playlists: " + (item.playlistCount?.toString() ?: "Unbekannt"))
                    Text("Lizenz- und VPN-Aktionen werden erst aktiviert, wenn der "
                        + "Server Berechtigungen, CSRF-Schutz und die konkrete Aktion bestätigt.")
                }
            },
            confirmButton = {
                TextButton(onClick = { selected = null }) { Text("Schließen") }
            }
        )
    }
}

@Composable
private fun ManagementMetric(title: String, count: Int?, modifier: Modifier) {
    Surface(modifier = modifier, color = SurfaceNavy,
        shape = RoundedCornerShape(16.dp),
        border = BorderStroke(1.dp, LineNavy)) {
        Column(Modifier.padding(14.dp)) {
            Text(title, fontSize = 11.sp, color = Secondary)
            Spacer(Modifier.height(6.dp))
            Text(count?.toString() ?: "—", fontSize = 26.sp,
                fontWeight = FontWeight.Bold, color = Foreground)
        }
    }
}
