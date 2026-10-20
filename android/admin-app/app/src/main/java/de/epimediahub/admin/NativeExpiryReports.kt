package de.epimediahub.admin

import android.content.Context
import android.os.Bundle
import android.os.CancellationSignal
import android.os.Handler
import android.os.Looper
import android.os.ParcelFileDescriptor
import android.print.PageRange
import android.print.PrintAttributes
import android.print.PrintDocumentAdapter
import android.print.PrintDocumentInfo
import android.print.PrintManager
import android.webkit.CookieManager
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.time.LocalDate
import java.time.YearMonth
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.Locale
import kotlin.concurrent.thread

/** Private subscriber expiry reporting: native Compose only, no WebView. */
internal object NativeExpiryApi {
    private const val BASE = "https://admin.epimediahub.com"
    private val main=Handler(Looper.getMainLooper())
    private const val LIMIT=600000
    private const val PDF_LIMIT=8*1024*1024

    data class Subscriber(val name:String,val expiry:LocalDate)
    data class Group(val playlist:String,val customers:List<Subscriber>)
    data class Report(val groups:List<Group>,val total:Int)

    private fun request(path:String,accept:String,max:Int):ByteArray {
        require(path.length<160 && path.matches(
            Regex("^/admin/mobile/reports/expiry/(month|week|month\\.pdf|month\\.preview\\.pdf)\\?[A-Za-z0-9=&-]+$")
        ))
        val cookie=CookieManager.getInstance().getCookie(BASE) ?: ""
        if (cookie.isBlank()) throw IllegalStateException("Admin-Sitzung fehlt")
        val conn=(URL(BASE+path).openConnection() as HttpURLConnection).apply {
            requestMethod="GET"
            instanceFollowRedirects=false
            connectTimeout=8000
            readTimeout=16000
            setRequestProperty("Cookie",cookie)
            setRequestProperty("Accept",accept)
            setRequestProperty("Cache-Control","no-store")
        }
        try {
            if(conn.responseCode!=200) throw IllegalStateException(
                if(conn.responseCode==503) "Ablaufdaten vom Anbieter noch nicht verfügbar."
                else if(conn.responseCode==401||conn.responseCode==403)
                    "Admin-Sitzung abgelaufen."
                else "Bericht derzeit nicht verfügbar (HTTP ${conn.responseCode}).")
            if(conn.contentType?.substringBefore(";")!=accept) {
                throw IllegalStateException("Unerwartete Antwort des Servers")
            }
            val result=conn.inputStream.use { input ->
                val out=java.io.ByteArrayOutputStream()
                val buffer=ByteArray(8192)
                while(true){
                    val read=input.read(buffer)
                    if(read<0) break
                    if(out.size()+read>max) throw IllegalStateException("Bericht zu groß")
                    out.write(buffer,0,read)
                }
                out.toByteArray()
            }
            return result
        } finally {
            conn.disconnect()
        }
    }

    fun getReport(month:Boolean,yearMonth:YearMonth,monday:LocalDate,
                  done:(Report?,String)->Unit) {
        thread(name="epi-expiry-read-only") {
            val outcome=try {
                val path=if(month)
                    "/admin/mobile/reports/expiry/month?year=${yearMonth.year}&month=${yearMonth.monthValue}"
                else "/admin/mobile/reports/expiry/week?from=$monday"
                val root=JSONObject(String(request(path,"application/json",LIMIT),Charsets.UTF_8))
                val groups=root.getJSONArray("playlists")
                if(groups.length()>1000)throw IllegalStateException("Ungewöhnlich viele Playlists")
                val result=mutableListOf<Group>()
                for(i in 0 until groups.length()){
                    val obj=groups.getJSONObject(i)
                    val name=obj.getString("name").trim().take(160)
                    val entries=obj.getJSONArray("entries")
                    if(entries.length()>10000) throw IllegalStateException("Ungewöhnlich viele Kunden")
                    val people=mutableListOf<Subscriber>()
                    for(j in 0 until entries.length()){
                        val customer=entries.getJSONObject(j)
                        people.add(Subscriber(
                            customer.getString("customer").take(160),
                            LocalDate.parse(customer.getString("expires_on"))
                        ))
                    }
                    result.add(Group(name,people))
                }
                Report(result,root.getInt("count")) to ""
            } catch(e:Exception) {
                null to (e.message?.take(130) ?: "Bericht konnte nicht geladen werden")
            }
            main.post { done(outcome.first,outcome.second) }
        }
    }

    fun printMonthly(context:Context,yearMonth:YearMonth,
                     preview:Boolean=false,done:(String)->Unit) {
        thread(name="epi-private-pdf-print") {
            val result=try {
                val path=if(preview)
                    "/admin/mobile/reports/expiry/month.preview.pdf?year=${yearMonth.year}&month=${yearMonth.monthValue}"
                else
                    "/admin/mobile/reports/expiry/month.pdf?year=${yearMonth.year}&month=${yearMonth.monthValue}"
                val bytes=request(path,"application/pdf",PDF_LIMIT)
                if(bytes.size<5 || !bytes.copyOfRange(0,5).contentEquals("%PDF-".toByteArray()))
                    throw IllegalStateException("Ungültige PDF-Datei")
                bytes to ""
            } catch(e:Exception) {
                null to (e.message?.take(130) ?: "PDF nicht verfügbar")
            }
            main.post {
                val bytes=result.first
                if(bytes==null){
                    done(result.second)
                } else {
                    try {
                        val manager=context.getSystemService(Context.PRINT_SERVICE) as PrintManager
                        val label="EpiMediaHub Ablauf ${yearMonth.year}-${yearMonth.monthValue}"
                        val adapter=object:PrintDocumentAdapter(){
                            override fun onLayout(
                                oldAttributes:PrintAttributes?,
                                newAttributes:PrintAttributes,
                                cancellationSignal:CancellationSignal,
                                callback:LayoutResultCallback,
                                extras:Bundle?
                            ) {
                                if(cancellationSignal.isCanceled){
                                    callback.onLayoutCancelled()
                                    return
                                }
                                val info=PrintDocumentInfo.Builder(label+".pdf")
                                    .setContentType(PrintDocumentInfo.CONTENT_TYPE_DOCUMENT)
                                    .setPageCount(PrintDocumentInfo.PAGE_COUNT_UNKNOWN)
                                    .build()
                                callback.onLayoutFinished(info,true)
                            }
                            override fun onWrite(
                                pages:Array<out PageRange>,
                                destination:ParcelFileDescriptor,
                                cancellationSignal:CancellationSignal,
                                callback:WriteResultCallback
                            ){
                                try{
                                    if(cancellationSignal.isCanceled){
                                        callback.onWriteCancelled()
                                        return
                                    }
                                    ParcelFileDescriptor.AutoCloseOutputStream(destination).use {
                                        it.write(bytes)
                                    }
                                    callback.onWriteFinished(arrayOf(PageRange.ALL_PAGES))
                                } catch(_:Exception){ callback.onWriteFailed("Druckdaten nicht verfügbar") }
                            }
                        }
                        manager.print(label,adapter,
                            PrintAttributes.Builder()
                                .setMediaSize(PrintAttributes.MediaSize.ISO_A4)
                                .setColorMode(PrintAttributes.COLOR_MODE_COLOR)
                                .build())
                        done("")
                    } catch(_:Exception) {
                        done("Android-Druckdienst momentan nicht verfügbar")
                    }
                }
            }
        }
    }
}

@Composable
internal fun NativeExpiryScreen(modifier:Modifier=Modifier) {
    val context=LocalContext.current
    val today=remember { LocalDate.now(ZoneId.of("Europe/Berlin")) }
    var monthly by remember { mutableStateOf(true) }
    var period by remember { mutableStateOf(YearMonth.from(today).plusMonths(1)) }
    var monday by remember { mutableStateOf(today.minusDays((today.dayOfWeek.value-1).toLong())) }
    var value by remember { mutableStateOf<NativeExpiryApi.Report?>(null) }
    var busy by remember { mutableStateOf(false) }
    var printing by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    val periodLabel=if(monthly) period.format(
        DateTimeFormatter.ofPattern("LLLL yyyy",Locale.GERMAN))
    else "${monday.format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))} – "+
        monday.plusDays(6).format(DateTimeFormatter.ofPattern("dd.MM.yyyy"))
    LaunchedEffect(monthly,period,monday){
        busy=true
        error=""
        value=null
        val requestedMonthly=monthly
        val requestedPeriod=period
        val requestedMonday=monday
        NativeExpiryApi.getReport(monthly,period,monday) { result,message ->
            if(requestedMonthly==monthly && requestedPeriod==period &&
               requestedMonday==monday){
                value=result
                error=message
                busy=false
            }
        }
    }
    Column(modifier.fillMaxWidth().verticalScroll(rememberScrollState())
        .padding(horizontal=17.dp,vertical=14.dp),
        verticalArrangement=Arrangement.spacedBy(12.dp)){
        Text("Ablaufübersichten",style=MaterialTheme.typography.headlineSmall,
            fontWeight=FontWeight.Bold)
        Text("Direktkunden und Reseller-Kunden · Nur bestätigte Anbieter-Ablaufdaten",
            style=MaterialTheme.typography.bodySmall)
        NativeExpiryCoverage()
        Row(horizontalArrangement=Arrangement.spacedBy(8.dp)){
            FilterChip(selected=monthly,onClick={monthly=true},
                label={Text("Monatsbericht")})
            FilterChip(selected=!monthly,onClick={monthly=false},
                label={Text("Woche")})
        }
        Row(horizontalArrangement=Arrangement.spacedBy(5.dp)){
            OutlinedButton(onClick={
                if(monthly)period=period.minusMonths(1) else monday=monday.minusWeeks(1)
            }){ Text("‹") }
            Text(periodLabel,modifier=Modifier.weight(1f)
                .padding(vertical=12.dp),fontWeight=FontWeight.Bold)
            OutlinedButton(onClick={
                if(monthly)period=period.plusMonths(1) else monday=monday.plusWeeks(1)
            }){ Text("›") }
        }
        if(monthly) Button(
            enabled=!busy&&!printing&&value!=null,
            onClick={
                printing=true
                NativeExpiryApi.printMonthly(context,period) { message ->
                    printing=false
                    if(message.isNotBlank())error=message
                }
            },modifier=Modifier.fillMaxWidth()){
            Text(if(printing)"Druckdaten werden geladen …" else "PDF drucken / als PDF speichern")
        }
        if(monthly) OutlinedButton(
            enabled=!busy&&!printing,
            onClick={
                printing=true
                NativeExpiryApi.printMonthly(context,period,preview=true) { message ->
                    printing=false
                    if(message.isNotBlank())error=message
                }
            },modifier=Modifier.fillMaxWidth()){
            Text("Unvollständige Arbeitsliste drucken (inkl. unbekannter Abläufe)")
        }
        if(busy) LinearProgressIndicator(Modifier.fillMaxWidth())
        if(error.isNotBlank()) Text(error,color=MaterialTheme.colorScheme.error)
        value?.let { data ->
            Text("${data.total} bestätigte Abläufe",fontWeight=FontWeight.SemiBold)
            if(data.groups.isEmpty()) Text("Keine bestätigten Abläufe in diesem Zeitraum.")
            data.groups.forEach { group ->
                ElevatedCard(Modifier.fillMaxWidth()){
                    Column(Modifier.padding(14.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                        Text(group.playlist,fontWeight=FontWeight.Bold)
                        Text("${group.customers.size} Kunden",
                            style=MaterialTheme.typography.bodySmall)
                        HorizontalDivider()
                        group.customers.forEach { entry ->
                            Row {
                                Text(entry.name,modifier=Modifier.weight(1f))
                                Text(entry.expiry.format(
                                    DateTimeFormatter.ofPattern("dd.MM.yyyy")))
                            }
                        }
                    }
                }
            }
        }
        Text("Persönliche Kundendaten werden nur nach sicherer Admin-Anmeldung "+
            "geladen. Bei unbekanntem Anbieter-Ablaufdatum wird kein Datum erfunden.",
            style=MaterialTheme.typography.bodySmall)
    }
}
