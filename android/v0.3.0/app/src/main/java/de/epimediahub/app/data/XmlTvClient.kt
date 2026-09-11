package de.epimediahub.app.data

import de.epimediahub.app.model.EpgItem
import org.xmlpull.v1.XmlPullParser
import org.xmlpull.v1.XmlPullParserFactory
import java.io.BufferedInputStream
import java.net.HttpURLConnection
import java.net.URL
import java.text.SimpleDateFormat
import java.util.Locale
import java.util.zip.GZIPInputStream

object XmlTvClient {
    fun nowNext(url:String, channelIds:Set<String>):Map<String,List<EpgItem>> {
        if(url.isBlank()||channelIds.isEmpty()) return emptyMap()
        val c=(URL(url).openConnection() as HttpURLConnection).apply{connectTimeout=12000;readTimeout=35000;setRequestProperty("User-Agent","EpiMediaHub-Android/0.3")}
        val raw=BufferedInputStream(c.inputStream)
        val input=if(url.endsWith(".gz",true)||c.contentEncoding?.contains("gzip",true)==true) GZIPInputStream(raw) else raw
        input.use { stream ->
            val x=XmlPullParserFactory.newInstance().newPullParser().apply{setInput(stream,null)}
            val now=System.currentTimeMillis()/1000L; val min=now-4*3600; val max=now+12*3600
            val out=mutableMapOf<String,MutableList<EpgItem>>()
            var event=x.eventType
            while(event!=XmlPullParser.END_DOCUMENT){
                if(event==XmlPullParser.START_TAG && x.name.equals("programme",true)){
                    val ch=x.getAttributeValue(null,"channel").orEmpty(); val start=parseTime(x.getAttributeValue(null,"start")); val end=parseTime(x.getAttributeValue(null,"stop"))
                    val wanted=ch in channelIds && end>=min && start<=max; var title=""; var desc=""; val depth=x.depth
                    while(true){
                        event=x.next()
                        if(event==XmlPullParser.START_TAG && wanted){ when(x.name.lowercase(Locale.ROOT)){"title"->title=x.nextText().trim();"desc"->desc=x.nextText().trim()} }
                        else if(event==XmlPullParser.END_TAG && x.name.equals("programme",true) && x.depth==depth) break
                        else if(event==XmlPullParser.END_DOCUMENT) break
                    }
                    if(wanted&&title.isNotBlank()) out.getOrPut(ch){mutableListOf()}.add(EpgItem(title,desc,start,end))
                }
                event=x.next()
            }
            return out.mapValues{it.value.sortedBy(EpgItem::start).take(8)}
        }
    }
    private fun parseTime(raw:String?):Long {
        if(raw.isNullOrBlank()) return 0
        for(f in listOf("yyyyMMddHHmmss Z","yyyyMMddHHmmssZ","yyyyMMddHHmmss")) runCatching{return (SimpleDateFormat(f,Locale.US).parse(raw.trim())?.time?:0)/1000}
        return 0
    }
}
