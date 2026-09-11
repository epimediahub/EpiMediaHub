package de.epimediahub.app.data

import android.util.Base64
import de.epimediahub.app.model.*
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class XtreamClient(private val p:PlaylistProfile) {
    private fun enc(s:String)=URLEncoder.encode(s,"UTF-8")
    private fun api(action:String, extra:String="")="${p.server}/player_api.php?username=${enc(p.username)}&password=${enc(p.password)}&action=$action$extra"
    private fun text(url:String):String { val c=(URL(url).openConnection() as HttpURLConnection).apply{connectTimeout=10000;readTimeout=25000;setRequestProperty("User-Agent","EpiMediaHub-Android/0.3")}; return c.inputStream.bufferedReader().use{it.readText()} }
    private fun array(url:String)=JSONArray(text(url))

    fun categories(kind:MediaKind):List<MediaCategory>{
        val action=when(kind){MediaKind.LIVE->"get_live_categories";MediaKind.MOVIE->"get_vod_categories";MediaKind.SERIES->"get_series_categories";else->return emptyList()}
        val a=array(api(action)); return buildList{for(i in 0 until a.length()){val o=a.optJSONObject(i)?:continue;add(MediaCategory(o.optString("category_id"),o.optString("category_name","Andere")))}}
    }

    fun entries(kind:MediaKind, categoryId:String?=null):List<MediaEntry>{
        val action=when(kind){MediaKind.LIVE->"get_live_streams";MediaKind.MOVIE->"get_vod_streams";MediaKind.SERIES->"get_series";else->return emptyList()}
        val extra=if(categoryId.isNullOrBlank())"" else "&category_id=${enc(categoryId)}"; val a=array(api(action,extra))
        return buildList{for(i in 0 until a.length()){val o=a.optJSONObject(i)?:continue
            when(kind){
                MediaKind.LIVE->{val id=o.optString("stream_id");add(MediaEntry(id,o.optString("name"),kind,o.optString("category_id"),o.optString("stream_icon"),o.optString("rating"),streamUrl="${p.server}/live/${enc(p.username)}/${enc(p.password)}/$id.${p.output}",epgId=o.optString("epg_channel_id")))}
                MediaKind.MOVIE->{val id=o.optString("stream_id");val ext=o.optString("container_extension","mp4");add(MediaEntry(id,o.optString("name"),kind,o.optString("category_id"),o.optString("stream_icon"),o.optString("rating"),streamUrl="${p.server}/movie/${enc(p.username)}/${enc(p.password)}/$id.$ext",extension=ext))}
                MediaKind.SERIES->{val id=o.optString("series_id");add(MediaEntry(id,o.optString("name"),kind,o.optString("category_id"),o.optString("cover"),o.optString("rating"),o.optString("plot"),seriesId=id))}
                else->Unit
            }
        }}
    }

    fun episodes(seriesId:String):List<MediaEntry>{
        val root=JSONObject(text(api("get_series_info","&series_id=${enc(seriesId)}"))); val eps=root.optJSONObject("episodes")?:return emptyList(); val out=mutableListOf<MediaEntry>()
        eps.keys().asSequence().toList().sortedBy{it.toIntOrNull()?:999}.forEach{seasonKey->
            val a=eps.optJSONArray(seasonKey)?:return@forEach
            for(i in 0 until a.length()){val o=a.optJSONObject(i)?:continue;val info=o.optJSONObject("info");val id=o.optString("id");val ext=o.optString("container_extension","mp4")
                out+=MediaEntry(id,o.optString("title","Episode ${o.optInt("episode_num",i+1)}"),MediaKind.EPISODE,image=info?.optString("movie_image").orEmpty(),rating=info?.optString("rating").orEmpty(),plot=info?.optString("plot").orEmpty(),streamUrl="${p.server}/series/${enc(p.username)}/${enc(p.password)}/$id.$ext",extension=ext,seriesId=seriesId,season=seasonKey.toIntOrNull()?:0,episode=o.optInt("episode_num",i+1))
            }
        };return out
    }

    fun shortEpg(streamId:String):List<EpgItem>{
        val root=JSONObject(text(api("get_short_epg","&stream_id=${enc(streamId)}&limit=4")));val a=root.optJSONArray("epg_listings")?:return emptyList()
        fun b64(o:JSONObject,k:String)=runCatching{String(Base64.decode(o.optString(k),Base64.DEFAULT))}.getOrDefault(o.optString(k))
        return buildList{for(i in 0 until a.length()){val o=a.optJSONObject(i)?:continue;add(EpgItem(b64(o,"title"),b64(o,"description"),o.optLong("start_timestamp"),o.optLong("stop_timestamp")))}}
    }
}
