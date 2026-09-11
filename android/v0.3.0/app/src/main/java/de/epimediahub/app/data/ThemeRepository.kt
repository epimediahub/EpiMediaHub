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
    fun backgroundRes(id:String)=context.resources.getIdentifier("theme_$id","drawable",context.packageName)
    fun markRes(id:String)=context.resources.getIdentifier("mark_$id","drawable",context.packageName)
}
