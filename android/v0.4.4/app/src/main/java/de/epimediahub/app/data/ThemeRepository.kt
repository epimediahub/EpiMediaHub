package de.epimediahub.app.data

import android.content.Context
import de.epimediahub.app.R
import de.epimediahub.app.model.*
import org.json.JSONObject

class ThemeRepository(private val context: Context) {
    private val backgroundNames = mutableMapOf<String, String>()

    fun load(): ThemeCatalog {
        val root = JSONObject(context.resources.openRawResource(R.raw.theme_catalog).bufferedReader().use { it.readText() })
        val groupsJson = root.getJSONArray("groups")
        val themesJson = root.getJSONObject("themes")
        val groups = buildList {
            for (i in 0 until groupsJson.length()) {
                val g = groupsJson.getJSONObject(i)
                val a = g.getJSONArray("themes")
                add(ThemeGroup(g.getString("id"), g.getString("label"), List(a.length()) { a.getString(it) }))
            }
        }
        val themes = mutableMapOf<String, ThemeInfo>()
        val keys = themesJson.keys()
        while (keys.hasNext()) {
            val id = keys.next()
            val t = themesJson.getJSONObject(id)
            val background = t.optString("background", "$id.png")
                .substringAfterLast('/')
                .substringBeforeLast('.')
            backgroundNames[id] = safe(background)
            themes[id] = ThemeInfo(id, t.optString("label", id), t.optString("group"), t.optString("accent", "#28A7F2"))
        }
        return ThemeCatalog(groups, themes)
    }

    private fun safe(value: String): String = value.lowercase().replace(Regex("[^a-z0-9_]+"), "_").trim('_')
    private fun drawable(name: String) = context.resources.getIdentifier(name, "drawable", context.packageName)

    fun backgroundRes(id: String): Int {
        val byId = drawable("theme_${safe(id)}")
        if (byId != 0) return byId
        val mapped = backgroundNames[id].orEmpty()
        return if (mapped.isNotBlank()) drawable("theme_$mapped") else 0
    }

    fun markRes(id: String) = drawable("mark_${safe(id)}")
    fun homeMotifRes(id: String) = drawable("home_motif_${safe(id)}")
    fun centerMarkRes(id: String) = drawable("center_mark_${safe(id)}")
    fun bannerMarkRes(id: String) = drawable("banner_mark_${safe(id)}")
}
