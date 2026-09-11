package de.epimediahub.app.data

import android.content.Context
import de.epimediahub.app.model.*
import org.json.JSONArray
import org.json.JSONObject

class PrefsRepository(context: Context) {
    private val p = context.getSharedPreferences("epimediahub", Context.MODE_PRIVATE)

    fun loadPlaylists(): List<PlaylistProfile> = readArray("playlists").mapNotNull { o ->
        runCatching {
            PlaylistProfile(
                id=o.getString("id"), name=o.optString("name","IPTV"), originalUrl=o.optString("url"),
                type=PlaylistType.valueOf(o.optString("type","M3U")), server=o.optString("server"),
                username=o.optString("username"), password=o.optString("password"), output=o.optString("output","ts")
            )
        }.getOrNull()
    }

    fun savePlaylists(list: List<PlaylistProfile>) = writeArray("playlists", list.map { x -> JSONObject().apply {
        put("id",x.id); put("name",x.name); put("url",x.originalUrl); put("type",x.type.name); put("server",x.server)
        put("username",x.username); put("password",x.password); put("output",x.output)
    }})

    var activePlaylistId: String
        get()=p.getString("active_playlist","").orEmpty()
        set(v){p.edit().putString("active_playlist",v).apply()}
    var themeId: String
        get()=p.getString("theme","default") ?: "default"
        set(v){p.edit().putString("theme",v).apply()}
    var preferredAudioLanguage: String
        get()=p.getString("audio_lang","de") ?: "de"
        set(v){p.edit().putString("audio_lang",v).apply()}
    var preferredSubtitleLanguage: String
        get()=p.getString("subtitle_lang","de") ?: "de"
        set(v){p.edit().putString("subtitle_lang",v).apply()}

    fun getResume(key:String)=p.getLong("resume_$key",0L)

    fun savePlayback(item: MediaEntry, pos: Long, duration: Long) {
        if(item.kind==MediaKind.LIVE) return
        val safe=pos.coerceAtLeast(0L)
        val done=duration>0 && safe >= (duration*.93).toLong()
        if(done) p.edit().remove("resume_${item.resumeKey}").apply() else p.edit().putLong("resume_${item.resumeKey}",safe).apply()
        val list=loadContinue().filterNot{it.media.resumeKey==item.resumeKey}.toMutableList()
        if(!done && safe>=15_000) list.add(0,ContinueItem(item,safe,duration.coerceAtLeast(0),System.currentTimeMillis()))
        writeArray("continue",list.take(60).map(::continueJson))
    }

    fun loadContinue(): List<ContinueItem> = readArray("continue").mapNotNull { o ->
        runCatching { ContinueItem(mediaFromJson(o.getJSONObject("media")),o.optLong("position"),o.optLong("duration"),o.optLong("updated")) }.getOrNull()
    }.sortedByDescending{it.updatedAt}

    fun toggleFavorite(item: MediaEntry): Boolean {
        val list=loadFavoriteEntries().toMutableList()
        val i=list.indexOfFirst{it.resumeKey==item.resumeKey}
        val added=i<0
        if(added) list.add(0,item) else list.removeAt(i)
        writeArray("favorites_items",list.take(200).map(::mediaJson))
        return added
    }
    fun isFavorite(item: MediaEntry)=loadFavoriteEntries().any{it.resumeKey==item.resumeKey}
    fun loadFavoriteEntries(): List<MediaEntry> = readArray("favorites_items").mapNotNull { runCatching{mediaFromJson(it)}.getOrNull() }

    private fun continueJson(c: ContinueItem)=JSONObject().apply{put("media",mediaJson(c.media));put("position",c.positionMs);put("duration",c.durationMs);put("updated",c.updatedAt)}
    private fun mediaJson(m: MediaEntry)=JSONObject().apply{
        put("id",m.id);put("name",m.name);put("kind",m.kind.name);put("categoryId",m.categoryId);put("image",m.image);put("rating",m.rating)
        put("plot",m.plot);put("streamUrl",m.streamUrl);put("extension",m.extension);put("seriesId",m.seriesId);put("season",m.season);put("episode",m.episode);put("epgId",m.epgId)
    }
    private fun mediaFromJson(o:JSONObject)=MediaEntry(
        o.getString("id"),o.optString("name"),MediaKind.valueOf(o.optString("kind","LIVE")),o.optString("categoryId"),o.optString("image"),o.optString("rating"),
        o.optString("plot"),o.optString("streamUrl"),o.optString("extension","ts"),o.optString("seriesId"),o.optInt("season"),o.optInt("episode"),o.optString("epgId")
    )
    private fun readArray(key:String): List<JSONObject> { val a=runCatching{JSONArray(p.getString(key,"[]"))}.getOrElse{JSONArray()}; return (0 until a.length()).mapNotNull{a.optJSONObject(it)} }
    private fun writeArray(key:String, list:List<JSONObject>){ val a=JSONArray();list.forEach(a::put);p.edit().putString(key,a.toString()).apply() }
}
