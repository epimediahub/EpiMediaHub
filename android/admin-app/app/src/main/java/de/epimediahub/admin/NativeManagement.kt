package de.epimediahub.admin

import android.webkit.CookieManager
import android.os.Handler
import android.os.Looper
import java.net.URLEncoder
import kotlinx.coroutines.delay
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.rememberScrollState
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.verticalScroll
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
import androidx.compose.ui.text.input.PasswordVisualTransformation
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
 * License and VPN grants require dedicated audited backend adapters, CSRF and a
 * second confirmation. The existing server business handlers own all writes.
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
        val loaded: Boolean,
        val customerHasMore: Boolean = false,
        val resellerHasMore: Boolean = false,
        val customerNextId: String? = null,
        val resellerNextId: String? = null
    )

    data class DetailItem(
        val id: String, val name: String,
        val description: String, val enabled: Boolean
    )
    data class Detail(
        val name: String,
        val enabled: Boolean,
        val playlists: List<DetailItem>,
        val devices: List<DetailItem>,
        val customers: List<DetailItem>,
        val morePlaylists: Boolean,
        val moreDevices: Boolean,
        val moreCustomers: Boolean
    )

    private class Status(val code: Int) : RuntimeException()

    private fun read(path: String, cookie: String): JSONObject {
        val cleanPath = path.substringBefore("?")
        require(
            cleanPath in setOf(
                "/admin/mobile/management/overview",
                "/admin/mobile/management/customers",
                "/admin/mobile/management/resellers"
            ) || Regex("^/admin/mobile/management/(customers|resellers)/[1-9][0-9]{0,17}$")
                .matches(cleanPath)
        )
        require(path.length < 300 && !path.contains("#"))
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

    private fun nextId(payload: JSONObject): String? {
        val cursor = payload.optString("next_before_id", "")
        return cursor.takeIf { Regex("[1-9][0-9]{0,17}").matches(it) }
    }

    fun search(
        cookie: String, kind: String, term: String,
        done: (List<Entry>?, Boolean, String?, String) -> Unit
    ) {
        if (cookie.isBlank() || kind !in setOf("customers", "resellers") || term.length > 80) {
            main.post { done(null, false, null, "Bitte als Administrator anmelden.") }
            return
        }
        thread(name = "epi-admin-native-search") {
            try {
                val encoded = URLEncoder.encode(term, "UTF-8")
                val payload = read("/admin/mobile/management/$kind?q=$encoded", cookie)
                val found = entries(payload, kind)
                main.post { done(found, payload.optBoolean("has_more", false),
                    nextId(payload), "") }
            } catch (_: Exception) {
                main.post { done(null, false, null, "Suche vorübergehend nicht erreichbar.") }
            }
        }
    }

    fun loadMore(
        cookie: String, kind: String, term: String, cursor: String,
        done: (List<Entry>?, String?, String) -> Unit
    ) {
        if (cookie.isBlank() || kind !in setOf("customers", "resellers")
            || term.length > 80 || !Regex("[1-9][0-9]{0,17}").matches(cursor)) {
            main.post { done(null, null, "Weitere Einträge können nicht geladen werden.") }
            return
        }
        thread(name = "epi-admin-native-next-page") {
            try {
                val encoded = URLEncoder.encode(term, "UTF-8")
                val body = read("/admin/mobile/management/$kind?q=$encoded&before_id=$cursor",
                    cookie)
                val found = entries(body, kind)
                main.post { done(found, nextId(body), "") }
            } catch (_: Exception) {
                main.post { done(null, null, "Weitere Einträge derzeit nicht erreichbar.") }
            }
        }
    }

    private fun detailEntries(body: JSONObject, key: String): List<DetailItem> {
        val array = body.optJSONArray(key) ?: return emptyList()
        if (array.length() > LIMIT) throw IllegalStateException("Unbounded detail list")
        return (0 until array.length()).map { i ->
            val value = array.getJSONObject(i)
            DetailItem(
                id = value.optString("id", "").take(25),
                name = value.optString("name", "").take(160),
                description = value.optString("platform", "").take(48),
                enabled = value.optBoolean("enabled", false)
            )
        }
    }

    fun loadDetail(
        cookie: String,
        kind: String,
        identifier: String,
        done: (Detail?, String) -> Unit
    ) {
        if (cookie.isBlank() || kind !in setOf("customers", "resellers") ||
            !Regex("[1-9][0-9]{0,17}").matches(identifier)) {
            main.post { done(null, "Anmeldung oder Eintrags-ID ungültig.") }
            return
        }
        thread(name = "epi-admin-native-detail") {
            try {
                val payload = read("/admin/mobile/management/$kind/$identifier", cookie)
                val result = Detail(
                    name = payload.optString("name", "").take(160),
                    enabled = payload.optBoolean("enabled", false),
                    playlists = detailEntries(payload, "playlists"),
                    devices = detailEntries(payload, "devices"),
                    customers = detailEntries(payload, "customers"),
                    morePlaylists = payload.optBoolean("more_playlists", false),
                    moreDevices = payload.optBoolean("more_devices", false),
                    moreCustomers = payload.optBoolean("more_customers", false)
                )
                main.post { done(result, "") }
            } catch (_: Exception) {
                main.post { done(null, "Details momentan nicht verfügbar.") }
            }
        }
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
                    null, true, true,
                    customers.optBoolean("has_more", false),
                    resellers.optBoolean("has_more", false),
                    nextId(customers),
                    nextId(resellers)
                )
            } catch (error: Status) {
                val message = when (error.code) {
                    401, 403 -> "Admin-Sitzung abgelaufen. Bitte erneut anmelden."
                    404, 501 -> "Die native Verwaltungs-API ist serverseitig noch nicht aktiviert."
                    else -> "Admin-Verwaltung derzeit nicht erreichbar (HTTP ${error.code})."
                }
                Result(null, emptyList(), emptyList(), message, error.code != 401 && error.code != 403, false)
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
    var searchResult by remember { mutableStateOf<List<NativeManagementApi.Entry>?>(null) }
    var searchHasMore by remember { mutableStateOf(false) }
    var searchNextId by remember { mutableStateOf<String?>(null) }
    var searchError by remember { mutableStateOf("") }
    var searchBusy by remember { mutableStateOf(false) }
    var additionalEntries by remember {
        mutableStateOf<List<NativeManagementApi.Entry>>(emptyList())
    }
    var additionalNextId by remember { mutableStateOf<String?>(null) }
    var additionalLoaded by remember { mutableStateOf(false) }
    var loadingMore by remember { mutableStateOf(false) }
    var moreError by remember { mutableStateOf("") }
    LaunchedEffect(query, section, data?.loaded) {
        searchResult = null
        searchNextId = null
        additionalEntries = emptyList()
        additionalNextId = null
        additionalLoaded = false
        loadingMore = false
        moreError = ""
        searchError = ""
        if (query.isNotBlank() && data?.loaded == true) {
            searchBusy = true
            delay(350)
            val requested = query
            val requestSection = section
            val kind = if (section == 0) "customers" else "resellers"
            val cookie = CookieManager.getInstance()
                .getCookie("https://admin.epimediahub.com") ?: ""
            NativeManagementApi.search(cookie, kind, requested) { list, more, cursor, error ->
                if (query == requested && section == requestSection) {
                    searchResult = list
                    searchHasMore = more
                    searchNextId = cursor
                    searchError = error
                    searchBusy = false
                }
            }
        } else {
            searchBusy = false
        }
    }
    var selected by remember { mutableStateOf<NativeManagementApi.Entry?>(null) }
    var pendingRename by remember { mutableStateOf<NativeManagementApi.Entry?>(null) }
    var inspectingDevice by remember { mutableStateOf<NativeManagementApi.DetailItem?>(null) }
    var renameValue by remember { mutableStateOf("") }
    var renameBusy by remember { mutableStateOf(false) }
    var renameResult by remember { mutableStateOf("") }
    var pendingGrant by remember {
        mutableStateOf<Pair<NativeManagementApi.DetailItem, String>?>(null)
    }
    var grantBusy by remember { mutableStateOf(false) }
    var grantMessage by remember { mutableStateOf("") }
    var operationMessage by remember { mutableStateOf("") }
    var pendingCreate by remember { mutableStateOf(false) }
    var createBusy by remember { mutableStateOf(false) }
    var createName by remember { mutableStateOf("") }
    var resellerUsername by remember { mutableStateOf("") }
    var resellerPassword by remember { mutableStateOf("") }
    var resellerBranding by remember { mutableStateOf("") }
    var resellerCustomerLimit by remember { mutableStateOf("0") }
    var resellerDeviceLimit by remember { mutableStateOf("0") }
    var pendingLegacyAction by remember { mutableStateOf<Triple<String,String,String>?>(null) }
    var editingPlaylist by remember { mutableStateOf<NativeManagementApi.DetailItem?>(null) }
    var createPlaylist by remember { mutableStateOf(false) }
    var actionValue by remember { mutableStateOf("") }
    var actionBusy by remember { mutableStateOf(false) }
    var loadedDetail by remember { mutableStateOf<NativeManagementApi.Detail?>(null) }
    var detailBusy by remember { mutableStateOf(false) }
    var detailMessage by remember { mutableStateOf("") }
    LaunchedEffect(selected?.id, section) {
        val item = selected
        loadedDetail = null
        detailMessage = ""
        grantMessage = ""
        if (item != null) {
            detailBusy = true
            val kind = if (section == 0) "customers" else "resellers"
            val cookie = CookieManager.getInstance().getCookie(
                "https://admin.epimediahub.com") ?: ""
            NativeManagementApi.loadDetail(cookie, kind, item.id) { value, message ->
                if (selected?.id == item.id) {
                    loadedDetail = value
                    detailMessage = message
                    detailBusy = false
                }
            }
        } else {
            detailBusy = false
        }
    }

    if (selected == null) {
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
        if (renameResult.isNotBlank()) {
            Text(renameResult, color = AccentBlue, fontSize = 12.sp,
                modifier = Modifier.padding(vertical = 8.dp))
        }
        if (operationMessage.isNotBlank()) {
            Text(operationMessage, color = AccentBlue, fontSize = 12.sp)
        }
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
        val overview = data?.overview
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
        Spacer(Modifier.height(10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp),
            modifier = Modifier.fillMaxWidth()) {
            OutlinedButton(onClick = openEpiscene, modifier = Modifier.weight(1f)) {
                Text("EpiScene", maxLines = 1)
            }
            OutlinedButton(onClick = openAlerts, modifier = Modifier.weight(1f)) {
                Text("Meldungen", maxLines = 1)
            }
        }
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            FilterChip(selected = section == 0, onClick = { section = 0; query = "" },
                label = { Text("Kunden") })
            FilterChip(selected = section == 1, onClick = { section = 1; query = "" },
                label = { Text("Reseller") })
        }
        Button(
            enabled = !loading && !createBusy && !actionBusy,
            onClick = {
                createName = ""
                resellerUsername = ""
                resellerPassword = ""
                resellerBranding = ""
                resellerCustomerLimit = "0"
                resellerDeviceLimit = "0"
                pendingCreate = true
                operationMessage = ""
            },
            modifier = Modifier.fillMaxWidth()
        ) { Text(if (section == 0) "+ Kunde anlegen" else "+ Reseller anlegen") }
        OutlinedTextField(
            value = query,
            onValueChange = { query = it.take(80) },
            label = { Text(if (section == 0) "Kunden suchen" else "Reseller suchen") },
            leadingIcon = { Icon(Icons.Outlined.Search, null) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth().padding(vertical = 7.dp)
        )
        val all = if (section == 0) data?.customers.orEmpty() else data?.resellers.orEmpty()
        val firstPage = if (query.isBlank()) all else searchResult.orEmpty()
        val filtered = firstPage + additionalEntries
        val initialCursor = if (query.isBlank()) {
            if (section == 0) data?.customerNextId else data?.resellerNextId
        } else searchNextId
        val nextCursor = if (additionalLoaded) additionalNextId else initialCursor
        val legacyMore = if (query.isBlank()) {
            if (section == 0) data?.customerHasMore == true
            else data?.resellerHasMore == true
        } else searchHasMore
        if (searchBusy || loadingMore) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (searchError.isNotBlank()) {
            Text(searchError, color = Secondary, fontSize = 12.sp)
        }
        if (moreError.isNotBlank()) {
            Text(moreError, color = Secondary, fontSize = 12.sp)
        }
        if (nextCursor == null && !additionalLoaded && legacyMore) {
            Text("Für weitere Einträge muss die Server-API aktualisiert werden. "
                + "Bis dahin bitte genauer suchen.", color = Secondary, fontSize = 12.sp)
        }
        if (filtered.isEmpty() && !searchBusy && searchError.isBlank()) {
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
                            Text("ID " + item.id, color = Secondary, fontSize = 10.sp)
                        }
                        Icon(Icons.Outlined.ChevronRight, null, tint = Secondary)
                    }
                }
            }
            if (nextCursor != null) {
                item {
                    OutlinedButton(
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !loadingMore && !searchBusy,
                        onClick = {
                            val cursor = nextCursor
                            if (cursor != null) {
                                val requestedSection = section
                                val requestedQuery = query
                                val kind = if (section == 0) "customers" else "resellers"
                                val cookie = CookieManager.getInstance().getCookie(
                                    "https://admin.epimediahub.com") ?: ""
                                loadingMore = true
                                moreError = ""
                                NativeManagementApi.loadMore(
                                    cookie, kind, requestedQuery, cursor
                                ) { page, next, error ->
                                    if (section == requestedSection && query == requestedQuery) {
                                        loadingMore = false
                                        if (page == null) {
                                            moreError = error
                                        } else {
                                            val ids = filtered.map { it.id }.toSet()
                                            additionalEntries = additionalEntries +
                                                page.filterNot { it.id in ids }
                                            additionalNextId = next
                                            additionalLoaded = true
                                        }
                                    }
                                }
                            }
                        }
                    ) { Text("Weitere Einträge laden") }
                }
            }
        }
    }

    } else {
        val item = selected!!
        BackHandler(enabled = true) {
            if (!grantBusy && !renameBusy) selected = null
        }
        Column(
            modifier = modifier.fillMaxWidth().background(Navy)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 18.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            TextButton(onClick = { if (!grantBusy && !renameBusy) selected = null }) {
                Text("‹ Zurück zur Übersicht", color = AccentBlue)
            }
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text(item.name, color = Foreground, fontSize = 24.sp,
                        fontWeight = FontWeight.ExtraBold)
                    Text(item.subtitle, color = Secondary, fontSize = 12.sp)
                }
                OutlinedButton(
                    onClick = {
                        pendingRename = item
                        renameValue = item.name
                        renameResult = ""
                    },
                    enabled = !renameBusy && !grantBusy
                ) { Text("Bearbeiten") }
            }
            if (detailBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (detailMessage.isNotBlank()) Text(detailMessage, color = Secondary)
            if (renameResult.isNotBlank()) Text(renameResult, color = AccentBlue)
            if (grantMessage.isNotBlank()) Text(grantMessage, color = AccentBlue)
            if (operationMessage.isNotBlank()) Text(operationMessage, color = AccentBlue)
            if (grantBusy || actionBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
            if (section == 0) {
                OutlinedButton(
                    enabled = !actionBusy && !renameBusy && !grantBusy,
                    onClick = {
                        pendingLegacyAction = Triple("assign-reseller",item.id,item.name)
                        actionValue = ""
                    }
                ) { Text("Reseller zuweisen") }
            }
            if (section == 0 && loadedDetail != null) {
                Button(
                    onClick = { createPlaylist = true },
                    enabled = !actionBusy && !grantBusy && !renameBusy,
                    modifier = Modifier.fillMaxWidth()
                ) { Text("+ Playlist anlegen") }
            }
            loadedDetail?.let { detail ->
                Surface(
                    color = SurfaceNavy,
                    shape = RoundedCornerShape(14.dp),
                    border = BorderStroke(1.dp, LineNavy)
                ) {
                    Row(Modifier.fillMaxWidth().padding(14.dp),
                        verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.Shield, null,
                            tint = if (detail.enabled) AccentBlue else Secondary)
                        Spacer(Modifier.width(10.dp))
                        Text(if (detail.enabled) "Konto aktiv" else "Konto deaktiviert",
                            color = Foreground, fontWeight = FontWeight.Medium)
                    }
                }
                val groupings = listOf(
                    Pair("Playlists", detail.playlists),
                    Pair("Geräte", detail.devices),
                    Pair("Zugeordnete Kunden", detail.customers)
                )
                groupings.forEach { (heading, entries) ->
                    if (entries.isNotEmpty()) {
                        Text(heading, color = Foreground, fontSize = 17.sp,
                            fontWeight = FontWeight.Bold)
                        entries.take(100).forEach { entry ->
                            Surface(
                                modifier = Modifier.fillMaxWidth(),
                                color = SurfaceNavy,
                                shape = RoundedCornerShape(14.dp),
                                border = BorderStroke(1.dp, LineNavy)
                            ) {
                                Column(Modifier.fillMaxWidth().padding(12.dp),
                                    verticalArrangement = Arrangement.spacedBy(8.dp)) {
                                    Text(entry.name, color = Foreground,
                                        fontWeight = FontWeight.SemiBold)
                                    Text(
                                        (if (entry.enabled) "Aktiv" else "Deaktiviert") +
                                            if (entry.description.isNotBlank())
                                                " · " + entry.description else "",
                                        color = Secondary, fontSize = 12.sp
                                    )
                                    val playlistEntry = heading == "Playlists" &&
                                        section == 0 &&
                                        Regex("[1-9][0-9]{0,17}").matches(entry.id)
                                    if (playlistEntry) {
                                        TextButton(onClick = { editingPlaylist = entry },
                                            enabled = !actionBusy && !grantBusy) {
                                            Text("Playlist bearbeiten", fontSize = 11.sp)
                                        }
                                        TextButton(
                                            enabled = !actionBusy && !grantBusy,
                                            onClick = {
                                                pendingLegacyAction = Triple(
                                                    "delete-playlist",entry.id,entry.name)
                                                actionValue = ""
                                            }
                                        ) { Text("Playlist löschen", fontSize = 11.sp) }
                                    }
                                    val eligible = heading == "Geräte" && section == 0 &&
                                        Regex("[1-9][0-9]{0,17}").matches(entry.id)
                                    if (eligible) {
                                        TextButton(onClick = { inspectingDevice = entry }) {
                                            Text("Gerätediagnose")
                                        }
                                        Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                                            TextButton(onClick = {
                                                pendingLegacyAction = Triple(
                                                    "rename-device",entry.id,entry.name)
                                                actionValue = entry.name
                                            }, enabled = !actionBusy) {
                                                Text("Umbenennen", fontSize = 11.sp)
                                            }
                                            TextButton(onClick = {
                                                pendingLegacyAction = Triple(
                                                    "sync-device",entry.id,entry.name)
                                                actionValue = ""
                                            }, enabled = !actionBusy) {
                                                Text("Synchronisieren", fontSize = 11.sp)
                                            }
                                        }
                                        TextButton(onClick = {
                                            pendingLegacyAction = Triple(
                                                "move-device",entry.id,entry.name)
                                            actionValue = ""
                                        }, enabled = !actionBusy) {
                                            Text("Anderem Kunden zuordnen", fontSize = 11.sp)
                                        }
                                        if (detail.enabled && entry.enabled) {
                                            Row(horizontalArrangement =
                                                Arrangement.spacedBy(6.dp)) {
                                                OutlinedButton(
                                                    onClick = {
                                                        pendingGrant = entry to "grant-year"
                                                    },
                                                    enabled = !grantBusy,
                                                    contentPadding = PaddingValues(horizontal = 8.dp)
                                                ) {
                                                    Text("1 Jahr App", fontSize = 11.sp)
                                                }
                                                OutlinedButton(
                                                    onClick = {
                                                        pendingGrant = entry to "vpn-trial7"
                                                    },
                                                    enabled = !grantBusy,
                                                    contentPadding = PaddingValues(horizontal = 8.dp)
                                                ) {
                                                    Text("7 Tage VPN", fontSize = 11.sp)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
                if (detail.morePlaylists || detail.moreDevices || detail.moreCustomers) {
                    Text("Weitere Datensätze vorhanden. Nutze die Suche.",
                        color = Secondary, fontSize = 12.sp)
                }
            }
            Text("Änderungen und Freigaben werden durch den Admin-Server geprüft. "
                + "Playlist-Zugangsdaten werden hier nicht angezeigt.",
                color = Secondary, fontSize = 11.sp)
            Spacer(Modifier.height(18.dp))
        }
    }

    if (createPlaylist || editingPlaylist != null) {
        NativePlaylistEditorDialog(
            customerId = selected?.id ?: "0",
            playlistId = editingPlaylist?.id,
            initialName = editingPlaylist?.name ?: "",
            onDismiss = { createPlaylist = false; editingPlaylist = null },
            onFinished = { applied, message ->
                operationMessage = message
                if (applied) {
                    createPlaylist = false
                    editingPlaylist = null
                    val item = selected
                    if (item != null) {
                        val cookie = CookieManager.getInstance()
                            .getCookie("https://admin.epimediahub.com") ?: ""
                        NativeManagementApi.loadDetail(cookie, "customers", item.id) {
                            detail, error ->
                            loadedDetail = detail
                            detailMessage = error
                        }
                    }
                    refresh()
                }
            }
        )
    }

    if (pendingCreate) {
        val creatingReseller = section == 1
        AlertDialog(
            onDismissRequest = { if (!createBusy) pendingCreate = false },
            title = { Text(if (creatingReseller) "Reseller anlegen" else "Kunden anlegen") },
            text = {
                Column(
                    modifier = Modifier.verticalScroll(rememberScrollState()),
                    verticalArrangement = Arrangement.spacedBy(8.dp)
                ) {
                    OutlinedTextField(
                        value = createName, onValueChange = { createName = it.take(120) },
                        label = { Text("Name") }, singleLine = true
                    )
                    if (creatingReseller) {
                        OutlinedTextField(
                            value = resellerUsername,
                            onValueChange = { resellerUsername = it.take(60) },
                            label = { Text("Benutzername") }, singleLine = true
                        )
                        OutlinedTextField(
                            value = resellerPassword,
                            onValueChange = { resellerPassword = it.take(256) },
                            label = { Text("Startpasswort") },
                            visualTransformation = PasswordVisualTransformation(),
                            singleLine = true
                        )
                        OutlinedTextField(
                            value = resellerBranding,
                            onValueChange = { resellerBranding = it.take(120) },
                            label = { Text("Branding (optional)") }, singleLine = true
                        )
                        OutlinedTextField(
                            value = resellerCustomerLimit,
                            onValueChange = { resellerCustomerLimit = it.filter(Char::isDigit).take(6) },
                            label = { Text("Kundenlimit") }, singleLine = true
                        )
                        OutlinedTextField(
                            value = resellerDeviceLimit,
                            onValueChange = { resellerDeviceLimit = it.filter(Char::isDigit).take(6) },
                            label = { Text("Gerätelimit") }, singleLine = true
                        )
                    }
                    Text("Die Neuanlage erfolgt über die vorhandene "
                        + "Server-Verwaltung und wird erst nach bestätigtem "
                        + "Datenbankeintrag als erfolgreich angezeigt.",
                        fontSize = 12.sp)
                    if (createBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingCreate = false }, enabled = !createBusy) {
                    Text("Abbrechen")
                }
            },
            confirmButton = {
                Button(
                    enabled = !createBusy && createName.trim().isNotBlank() &&
                        (!creatingReseller || (
                            resellerUsername.length >= 3 && resellerPassword.length >= 8 &&
                            resellerCustomerLimit.isNotBlank() &&
                            resellerDeviceLimit.isNotBlank())),
                    onClick = {
                        createBusy = true
                        val fields = if (creatingReseller) mapOf(
                            "name" to createName,
                            "username" to resellerUsername,
                            "password" to resellerPassword,
                            "branding_name" to resellerBranding,
                            "customer_limit" to resellerCustomerLimit,
                            "device_limit" to resellerDeviceLimit
                        ) else mapOf("name" to createName)
                        val action = if (creatingReseller) "create-reseller"
                            else "create-customer"
                        NativeLegacyActions.execute(action,"0",fields) { outcome ->
                            createBusy = false
                            operationMessage = outcome.message
                            if (outcome.applied) {
                                pendingCreate = false
                                resellerPassword = ""
                                query = ""
                                refresh()
                            }
                        }
                    }
                ) { Text("Jetzt anlegen") }
            }
        )
    }

    pendingLegacyAction?.let { (action,id,label) ->
        val description = when (action) {
            "rename-device" -> "Gerät umbenennen"
            "sync-device" -> "Gerät synchronisieren"
            "move-device" -> "Gerät einem Kunden zuordnen"
            "delete-playlist" -> "Playlist endgültig löschen"
            else -> "Reseller zuweisen"
        }
        AlertDialog(
            onDismissRequest = { if (!actionBusy) pendingLegacyAction = null },
            title = { Text(description) },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text("Eintrag: " + label)
                    if (action == "delete-playlist") {
                        Text("Die Playlist wird gelöscht und die zugehörigen "
                            + "Kundengeräte werden über die vorhandene "
                            + "Serverfunktion aktualisiert. Die Aktion "
                            + "kann nicht rückgängig gemacht werden.",
                            color = MaterialTheme.colorScheme.error,
                            fontSize = 12.sp)
                    }
                    if (action !in setOf("sync-device","delete-playlist")) {
                        OutlinedTextField(
                            value = actionValue,
                            onValueChange = { actionValue = it.take(120) },
                            label = { Text(when (action) {
                                "rename-device" -> "Neuer Gerätename"
                                "move-device" -> "Ziel-Kunden-ID"
                                else -> "Reseller-ID (leer = ohne Reseller)"
                            }) },
                            singleLine = true
                        )
                    }
                    Text("Nach Bestätigung wird die originale Serverfunktion "
                        + "ausgeführt und der tatsächliche neue Status geprüft.",
                        fontSize = 12.sp)
                    if (actionBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingLegacyAction = null },
                    enabled = !actionBusy) { Text("Abbrechen") }
            },
            confirmButton = {
                Button(
                    enabled = !actionBusy &&
                        (action in setOf("sync-device","assign-reseller",
                            "delete-playlist") || actionValue.isNotBlank()),
                    onClick = {
                        actionBusy = true
                        val fields = when (action) {
                            "rename-device" -> mapOf("name" to actionValue)
                            "move-device" -> mapOf("customer_id" to actionValue)
                            "assign-reseller" -> mapOf("reseller_id" to actionValue)
                            else -> emptyMap()
                        }
                        NativeLegacyActions.execute(action,id,fields) { outcome ->
                            actionBusy = false
                            operationMessage = outcome.message
                            pendingLegacyAction = null
                            if (outcome.applied) {
                                selected = null
                                refresh()
                            }
                        }
                    }
                ) { Text("Aktion bestätigen") }
            }
        )
    }

    pendingRename?.let { entry ->
        AlertDialog(
            onDismissRequest = { if (!renameBusy) pendingRename = null },
            title = { Text(if (section == 0) "Kunde umbenennen" else "Reseller umbenennen") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    OutlinedTextField(
                        value = renameValue,
                        onValueChange = { renameValue = it.take(140) },
                        label = { Text("Neuer Anzeigename") },
                        singleLine = true,
                        modifier = Modifier.fillMaxWidth()
                    )
                    Text("Dies ändert nur den Anzeigenamen, nicht Playlists, "
                        + "Geräte oder Zugangsdaten.", fontSize = 12.sp)
                    if (renameBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingRename = null },enabled = !renameBusy) {
                    Text("Abbrechen")
                }
            },
            confirmButton = {
                Button(
                    enabled = !renameBusy &&
                        renameValue.trim().isNotBlank() &&
                        renameValue.trim() != entry.name,
                    onClick = {
                        renameBusy = true
                        val kind = if (section == 0) "customers" else "resellers"
                        NativeAdminEdits.rename(kind,entry.id,entry.name,renameValue) { outcome ->
                            renameBusy = false
                            renameResult = outcome.message
                            pendingRename = null
                            if (outcome.success) {
                                selected = null
                                refresh()
                            }
                        }
                    }
                ) { Text("Namen speichern") }
            }
        )
    }

    inspectingDevice?.let { inspected ->
        NativeDeviceDiagnosticsDialog(
            deviceRowId=inspected.id,
            close={ inspectingDevice=null }
        )
    }

    pendingGrant?.let { (device, action) ->
        val caption = if (action == "grant-year") "1 Jahr App-Lizenz"
            else "7 Tage VPN-Test"
        AlertDialog(
            onDismissRequest = { if (!grantBusy) pendingGrant = null },
            title = { Text("Freigabe bestätigen") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                    Text("Aktion: $caption")
                    Text("Gerät: " + device.name)
                    Text("Die Vergabe erfolgt unmittelbar und wird serverseitig geprüft "
                        + "und protokolliert. Ein aktiver Anspruch wird nicht erneut vergeben.")
                    if (grantBusy) LinearProgressIndicator(Modifier.fillMaxWidth())
                }
            },
            dismissButton = {
                TextButton(onClick = { pendingGrant = null }, enabled = !grantBusy) {
                    Text("Abbrechen")
                }
            },
            confirmButton = {
                Button(
                    enabled = !grantBusy,
                    onClick = {
                        grantBusy = true
                        grantMessage = ""
                        NativeAdminActions.grant(device.id, action) { outcome ->
                            grantBusy = false
                            grantMessage = outcome.message
                            pendingGrant = null
                            if (outcome.applied) {
                                // A fresh detail read verifies the authoritative device list.
                                val item = selected
                                if (item != null) {
                                    val cookie = CookieManager.getInstance()
                                        .getCookie("https://admin.epimediahub.com") ?: ""
                                    NativeManagementApi.loadDetail(cookie,"customers",item.id) {
                                        detail, message ->
                                        loadedDetail = detail
                                        detailMessage = message
                                    }
                                }
                            }
                        }
                    }
                ) { Text("Jetzt freigeben") }
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
