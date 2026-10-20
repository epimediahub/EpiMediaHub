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
import java.net.URLEncoder
import java.util.UUID
import kotlin.concurrent.thread

/** Native EpiScene marker review; original server business handler does writes. */
internal object NativeMarkerApi {
    private const val BASE="https://admin.epimediahub.com"
    private val main=Handler(Looper.getMainLooper())

    data class Marker(
        val id:String,val title:String,val playlist:String,val kind:String,
        val season:Int,val episode:Int,val startMs:Long,val endMs:Long
    )
    data class Page(
        val markers:List<Marker>,val reviewCsrf:String,val nextId:String?
    )

    private fun read(path:String, accept:String="application/json"):JSONObject {
        require(path.startsWith("/admin/mobile/") && path.length<210 &&
            !path.contains("#") && !path.contains(".."))
        val cookie=CookieManager.getInstance().getCookie(BASE) ?: ""
        if(cookie.isBlank())throw IllegalStateException("Admin-Sitzung fehlt")
        val conn=(URL(BASE+path).openConnection() as HttpURLConnection).apply {
            requestMethod="GET"
            instanceFollowRedirects=false
            connectTimeout=8000
            readTimeout=14000
            setRequestProperty("Cookie",cookie)
            setRequestProperty("Accept",accept)
            setRequestProperty("Cache-Control","no-store")
        }
        try{
            if(conn.responseCode!=200) throw IllegalStateException(
                if(conn.responseCode==503)
                    "Markerfreigabe auf dem Server noch nicht freigeschaltet."
                else "EpiScene derzeit nicht erreichbar.")
            if(conn.contentType?.substringBefore(";")!="application/json")
                throw IllegalStateException("Ungültige API-Antwort")
            val text=conn.inputStream.bufferedReader().use{it.readText().take(160_000)}
            return JSONObject(text)
        } finally { conn.disconnect() }
    }

    fun load(before:String?=null,done:(Page?,String)->Unit){
        if(before!=null && !Regex("[1-9][0-9]{0,17}").matches(before)){
            main.post{done(null,"Ungültige Marker-Seite")}
            return
        }
        thread(name="epi-native-marker-read"){
            val result=try{
                val path="/admin/mobile/episcene/reviews"+
                    (if(before==null)"" else "?before_id=$before")
                val root=read(path)
                val token=root.getString("review_csrf")
                if(token.length<32)throw IllegalStateException("Sicherheitsprüfung fehlt")
                val arr=root.getJSONArray("markers")
                if(arr.length()>100)throw IllegalStateException("Zu viele Marker")
                val items=mutableListOf<Marker>()
                for(i in 0 until arr.length()){
                    val obj=arr.getJSONObject(i)
                    val id=obj.getString("id")
                    if(!Regex("[1-9][0-9]{0,17}").matches(id))continue
                    items+=Marker(
                        id=id,
                        title=obj.getString("title").take(150),
                        playlist=obj.getString("playlist").take(50),
                        kind=obj.getString("kind").take(20),
                        season=obj.optInt("season",0),
                        episode=obj.optInt("episode",0),
                        startMs=obj.getLong("start_ms"),
                        endMs=obj.getLong("end_ms")
                    )
                }
                val next=root.optString("next_before_id","").takeIf{
                    Regex("[1-9][0-9]{0,17}").matches(it)
                }
                Page(items,token,next) to ""
            }catch(e:Exception){
                null to (e.message?.take(140) ?: "Markerliste nicht verfügbar")
            }
            main.post{done(result.first,result.second)}
        }
    }

    fun decide(marker:Marker,decision:String,reviewCsrf:String,
               done:(Boolean,String)->Unit){
        if(decision !in setOf("approve","reject") ||
            !Regex("[1-9][0-9]{0,17}").matches(marker.id) ||
            reviewCsrf.length<32){
            main.post{done(false,"Freigabe-Eingaben ungültig")}
            return
        }
        thread(name="epi-native-marker-decision"){
            val result=try{
                val boot=read("/admin/mobile/bootstrap")
                val csrf=boot.getString("csrf")
                if(csrf.length<32)throw IllegalStateException("Admin-Sicherheitsprüfung fehlt")
                val cookie=CookieManager.getInstance().getCookie(BASE) ?: ""
                val fields=mapOf(
                    "csrf" to reviewCsrf,"decision" to decision,
                    "confirm" to "true","request_id" to UUID.randomUUID().toString()
                )
                val encoded=fields.entries.joinToString("&"){ (k,v)->
                    URLEncoder.encode(k,"UTF-8")+"="+URLEncoder.encode(v,"UTF-8")
                }
                val conn=(URL(
                    "$BASE/admin/mobile/episcene/reviews/${marker.id}/$decision"
                ).openConnection() as HttpURLConnection).apply{
                    requestMethod="POST"
                    instanceFollowRedirects=false
                    doOutput=true
                    connectTimeout=8000
                    readTimeout=16000
                    setRequestProperty("Cookie",cookie)
                    setRequestProperty("X-Dashboard-CSRF",csrf)
                    setRequestProperty("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                    setRequestProperty("Accept","application/json")
                    setRequestProperty("Cache-Control","no-store")
                }
                try{
                    conn.outputStream.use{it.write(encoded.toByteArray(Charsets.UTF_8))}
                    if(conn.responseCode!=200)
                        throw IllegalStateException(
                            "Aktion nicht bestätigt. Markerstatus aktualisieren, "+
                            "nicht sofort erneut freigeben.")
                    val result=JSONObject(conn.inputStream.bufferedReader().use{
                        it.readText().take(3000)
                    })
                    if(!result.optBoolean("applied",false))
                        throw IllegalStateException("Markerfreigabe nicht bestätigt.")
                    true to "Markerstatus erfolgreich überprüft."
                } finally { conn.disconnect() }
            }catch(e:Exception){
                false to (e.message?.take(160) ?:
                    "Ergebnis unbestätigt. Bitte Markerstatus aktualisieren.")
            }
            main.post{done(result.first,result.second)}
        }
    }
}

@Composable
internal fun NativeMarkerReviewPanel(){
    var markers by remember { mutableStateOf<List<NativeMarkerApi.Marker>>(emptyList()) }
    var csrf by remember { mutableStateOf("") }
    var nextId by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var selected by remember { mutableStateOf<Pair<NativeMarkerApi.Marker,String>?>(null) }
    var saving by remember { mutableStateOf(false) }
    fun reload(){
        busy=true
        error=""
        NativeMarkerApi.load(){ page,message ->
            busy=false
            if(page!=null){
                markers=page.markers
                csrf=page.reviewCsrf
                nextId=page.nextId
            }else{
                error=message
            }
        }
    }
    LaunchedEffect(Unit){ reload() }
    Column(verticalArrangement=Arrangement.spacedBy(10.dp)){
        Row(modifier=Modifier.fillMaxWidth()){
            Text("Marker zur Prüfung",modifier=Modifier.weight(1f),
                style=MaterialTheme.typography.titleLarge)
            OutlinedButton(onClick={reload()},enabled=!busy&&!saving){Text("Aktualisieren")}
        }
        if(busy)LinearProgressIndicator(Modifier.fillMaxWidth())
        if(error.isNotBlank())Text(error,color=MaterialTheme.colorScheme.error)
        if(markers.isEmpty()&&!busy&&error.isBlank()){
            Text("Keine offenen Marker in den Analysequellen 4K und THE BEST.")
        }
        for(marker in markers){
            ElevatedCard(Modifier.fillMaxWidth()){
                Column(Modifier.padding(13.dp),
                    verticalArrangement=Arrangement.spacedBy(5.dp)){
                    Text(marker.title,style=MaterialTheme.typography.titleMedium)
                    Text("${marker.playlist} · S${marker.season}E${marker.episode} "+
                        "· ${marker.kind}")
                    Text("${marker.startMs/1000}s – ${marker.endMs/1000}s")
                    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
                        Button(onClick={selected=marker to "approve"},
                            enabled=!saving){Text("Freigeben")}
                        OutlinedButton(onClick={selected=marker to "reject"},
                            enabled=!saving){Text("Ablehnen")}
                    }
                }
            }
        }
        if(nextId!=null){
            OutlinedButton(onClick={
                val cursor=nextId
                if(cursor!=null){
                    busy=true
                    NativeMarkerApi.load(cursor){ page,message ->
                        busy=false
                        if(page==null) error=message
                        else{
                            val existing=markers.map{it.id}.toSet()
                            markers=markers+page.markers.filterNot{it.id in existing}
                            csrf=page.reviewCsrf
                            nextId=page.nextId
                        }
                    }
                }
            },enabled=!busy&&!saving){Text("Weitere Marker laden")}
        }
    }
    selected?.let{ (marker,decision) ->
        AlertDialog(
            onDismissRequest={if(!saving)selected=null},
            title={Text(if(decision=="approve")"Marker freigeben" else "Marker ablehnen")},
            text={
                Column(verticalArrangement=Arrangement.spacedBy(8.dp)){
                    Text(marker.title)
                    Text("${marker.playlist} · ${marker.kind}")
                    Text("Vorhandene Originalzeitwerte werden unverändert übernommen.")
                    if(saving)LinearProgressIndicator(Modifier.fillMaxWidth())
                }
            },
            dismissButton={
                TextButton(onClick={selected=null},enabled=!saving){Text("Abbrechen")}
            },
            confirmButton={
                Button(enabled=!saving,onClick={
                    saving=true
                    NativeMarkerApi.decide(marker,decision,csrf){ ok,message ->
                        saving=false
                        selected=null
                        if(ok) reload()
                        else error=message
                    }
                }){Text("Bestätigen")}
            }
        )
    }
}
