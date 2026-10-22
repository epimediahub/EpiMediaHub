package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.concurrent.thread

/** Fully native read-only view; never writes a marker. */
internal object NativeExternalMarkerApi {
    private const val BASE = "https://admin.epimediahub.com"
    private val main = Handler(Looper.getMainLooper())
    data class Marker(
        val playlist: String, val title: String, val season: Int, val episode: Int,
        val source: String, val kind: String, val startMs: Long, val endMs: Long,
        val cacheStatus: String
    )
    data class Page(
        val items: List<Marker>, val total: Int, val introdb: Int,
        val theintrodb: Int, val page: Int, val hasMore: Boolean,
        val truncated: Boolean
    )

    fun load(playlist: String, source: String, state: String, query: String, page: Int,
             done: (Page?, String) -> Unit) {
        if (playlist !in setOf("", "8", "10") ||
            source !in setOf("", "introdb", "theintrodb") ||
            state !in setOf("", "active", "expired") ||
            page !in 1..100 || query.length > 80) {
            main.post { done(null, "Ungültiger Filter") }
            return
        }
        thread(name="epi-external-marker-read") {
            val result = try {
                val cookie = CookieManager.getInstance().getCookie(BASE) ?: ""
                if (cookie.isBlank()) error("Bitte als Administrator anmelden")
                val params = mapOf("playlist" to playlist, "source" to source,
                    "state" to state, "q" to query, "page" to page.toString())
                    .entries.joinToString("&") { (k, v) ->
                        URLEncoder.encode(k, "UTF-8") + "=" + URLEncoder.encode(v, "UTF-8")
                    }
                val connection = (URL(BASE + "/admin/mobile/episcene/markers?" + params)
                    .openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    instanceFollowRedirects = false
                    connectTimeout = 8000
                    readTimeout = 16000
                    setRequestProperty("Cookie",cookie)
                    setRequestProperty("Accept","application/json")
                    setRequestProperty("Cache-Control","no-store")
                }
                try {
                    if (connection.responseCode != 200)
                        error(if (connection.responseCode == 401 ||
                            connection.responseCode == 403) "Anmeldung erforderlich"
                            else "Markerübersicht auf dem Server noch nicht verfügbar")
                    if (connection.contentType?.substringBefore(";") != "application/json")
                        error("Ungültige API-Antwort")
                    val response = JSONObject(connection.inputStream.bufferedReader().use {
                        it.readText().take(100_000)
                    })
                    require(response.getString("scope") == "analysis_playlists_only")
                    require(response.getBoolean("read_only"))
                    val values = response.getJSONArray("markers")
                    require(values.length() <= 50)
                    val items = (0 until values.length()).map { i ->
                        val o = values.getJSONObject(i)
                        val id = o.getString("playlist_id")
                        val sourceName = o.getString("source")
                        val kindName = o.getString("kind")
                        val cache = o.getString("cache_status")
                        val from = o.getLong("start_ms")
                        val to = o.getLong("end_ms")
                        require(id in setOf("8","10"))
                        require(sourceName in setOf("introdb","theintrodb"))
                        require(kindName in setOf("intro","recap","outro"))
                        require(cache in setOf("active","expired"))
                        require(from >= 0 && to > from)
                        Marker(
                            if(id=="8") "4K ANALYSE" else "THE BEST",
                            o.getString("title").take(180),
                            o.getInt("season"),o.getInt("episode"),sourceName,kindName,
                            from,to,cache
                        )
                    }
                    val counts = response.getJSONObject("source_counts")
                    Page(items,response.getInt("total").coerceAtLeast(0),
                        counts.optInt("introdb",0).coerceAtLeast(0),
                        counts.optInt("theintrodb",0).coerceAtLeast(0),
                        response.getInt("page"),response.getBoolean("has_more"),
                        response.optBoolean("truncated_to_recent",false)) to ""
                } finally { connection.disconnect() }
            } catch (e: Exception) {
                null to (e.message?.take(150) ?: "Markerübersicht nicht erreichbar")
            }
            main.post { done(result.first,result.second) }
        }
    }
}

@Composable
private fun ExternalFilter(label: String, selected: Boolean, onClick: () -> Unit) {
    if (selected) Button(onClick=onClick,
        contentPadding=PaddingValues(horizontal=10.dp)) {
        Text(label,style=MaterialTheme.typography.labelSmall)
    } else OutlinedButton(onClick=onClick,
        contentPadding=PaddingValues(horizontal=10.dp)) {
        Text(label,style=MaterialTheme.typography.labelSmall)
    }
}

@Composable
internal fun NativeExternalMarkerPanel() {
    var playlist by remember { mutableStateOf("") }
    var source by remember { mutableStateOf("") }
    var state by remember { mutableStateOf("active") }
    var query by remember { mutableStateOf("") }
    var page by remember { mutableIntStateOf(1) }
    var result by remember { mutableStateOf<NativeExternalMarkerApi.Page?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }

    fun refresh(requestedPage: Int = 1) {
        if (busy) return
        busy = true
        error = ""
        NativeExternalMarkerApi.load(playlist,source,state,query,requestedPage) { value,message ->
            busy = false
            if (value != null) { result = value; page = requestedPage }
            else { error = message; result = null }
        }
    }
    LaunchedEffect(Unit) { refresh() }

    Column(verticalArrangement=Arrangement.spacedBy(10.dp)) {
        Text("IntroDB & TheIntroDB", style=MaterialTheme.typography.titleLarge)
        Text("Externe Marker · schreibgeschützt",
            style=MaterialTheme.typography.bodySmall,
            color=MaterialTheme.colorScheme.onSurfaceVariant)
        Row(horizontalArrangement=Arrangement.spacedBy(6.dp)) {
            ExternalFilter("Beide",playlist=="") { playlist="" }
            ExternalFilter("4K",playlist=="8") { playlist="8" }
            ExternalFilter("THE BEST",playlist=="10") { playlist="10" }
        }
        Row(horizontalArrangement=Arrangement.spacedBy(6.dp)) {
            ExternalFilter("Alle",source=="") { source="" }
            ExternalFilter("IntroDB",source=="introdb") { source="introdb" }
            ExternalFilter("TheIntroDB",source=="theintrodb") { source="theintrodb" }
        }
        Row(horizontalArrangement=Arrangement.spacedBy(6.dp)) {
            ExternalFilter("Aktiv",state=="active") { state="active" }
            ExternalFilter("Abgelaufen",state=="expired") { state="expired" }
            ExternalFilter("Alle",state=="") { state="" }
        }
        OutlinedTextField(value=query,onValueChange={query=it.take(80)},
            label={Text("Serie suchen")},singleLine=true,modifier=Modifier.fillMaxWidth())
        Button(onClick={refresh()},enabled=!busy,modifier=Modifier.fillMaxWidth()) {
            Text("Anzeigen / Aktualisieren")
        }
        if (busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if (error.isNotBlank()) Text(error,color=MaterialTheme.colorScheme.error)
        result?.let { current ->
            Text(current.total.toString()+" Marker · IntroDB "+
                current.introdb+" · TheIntroDB "+current.theintrodb)
            if (current.truncated) Text("Nur die neuesten 5000 Cache-Einträge.",
                style=MaterialTheme.typography.bodySmall)
            if (current.items.isEmpty()) Text("Keine Treffer für diese Filter.")
            for (marker in current.items) {
                ElevatedCard(Modifier.fillMaxWidth()) {
                    Column(Modifier.fillMaxWidth().padding(13.dp),
                        verticalArrangement=Arrangement.spacedBy(5.dp)) {
                        Text(marker.title,style=MaterialTheme.typography.titleMedium)
                        Text(marker.playlist+" · S"+
                            "%02d".format(marker.season)+"E"+
                            "%02d".format(marker.episode))
                        val kind = when(marker.kind) {
                            "intro" -> "Intro"
                            "recap" -> "Rückblick"
                            else -> "Abspann"
                        }
                        fun clock(ms: Long): String =
                            "%02d:%02d".format(ms/60000,(ms/1000)%60)
                        Text((if(marker.source=="introdb") "IntroDB" else "TheIntroDB")+
                            " · "+kind+" · "+clock(marker.startMs)+"–"+clock(marker.endMs))
                        Text(if(marker.cacheStatus=="active")"Cache aktiv" else "Cache abgelaufen",
                            color=if(marker.cacheStatus=="active")
                                MaterialTheme.colorScheme.secondary
                            else MaterialTheme.colorScheme.error)
                    }
                }
            }
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) {
                OutlinedButton(onClick={refresh(page-1)},enabled=!busy&&page>1) {
                    Text("Zurück")
                }
                Text("Seite "+page,modifier=Modifier.padding(top=12.dp))
                OutlinedButton(onClick={refresh(page+1)},enabled=!busy&&current.hasMore) {
                    Text("Weiter")
                }
            }
        }
        Text("Gespeicherte Marker sind kein Nachweis, dass der Player sie angezeigt hat.",
            style=MaterialTheme.typography.bodySmall,
            color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
