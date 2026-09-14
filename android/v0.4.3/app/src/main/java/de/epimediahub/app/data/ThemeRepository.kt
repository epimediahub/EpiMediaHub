package de.epimediahub.app.data

import android.content.Context
import de.epimediahub.app.R
import de.epimediahub.app.model.*
import org.json.JSONObject

class ThemeRepository(private val context: Context) {
    fun load(): ThemeCatalog {
        val root=JSONObject(context.resources.openRawResource(R.raw.theme_catalog).bufferedReader().use{it.readText()})
        val gj=root.getJSONArray("groups"); val tj=root.getJSONObject("themes")
        val groups=buildList { for(i in 0 until gj.length()){ val g=gj.getJSONObject(i); val a=g.getJSONArray("themes"); add(ThemeGroup(g.getString("id"),g.getString("label"),List(a.length()){a.getString(it)})) } }
        val themes=mutableMapOf<String,ThemeInfo>(); val keys=tj.keys()
        while(keys.hasNext()){ val id=keys.next(); val t=tj.getJSONObject(id); themes[id]=ThemeInfo(id,t.optString("label",id),t.optString("group"),t.optString("accent","#28A7F2")) }
        return ThemeCatalog(groups,themes)
    }

    private fun drawable(name:String)=context.resources.getIdentifier(name,"drawable",context.packageName)
    fun backgroundRes(id:String)=drawable("theme_$id")
    fun markRes(id:String)=drawable("mark_$id")
    fun homeMotifRes(id:String)=drawable("home_motif_$id")
    fun centerMarkRes(id:String)=drawable("center_mark_$id")
    fun bannerMarkRes(id:String)=drawable("banner_mark_$id")
}
