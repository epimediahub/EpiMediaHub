package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

object MediathekClient {
    const val API_URL = "https://mediathekviewweb.de/api/query"

    data class Country(
        val id: String,
        val label: String,
        val meta: String,
        val info: String
    )

    data class Provider(
        val id: String,
        val countryId: String,
        val label: String,
        val channel: String = "",
        val availability: String = "",
        val info: String = "",
        val playable: Boolean = true
    )

    val countries = listOf(
        Country("de", "Deutschland", "ARD · ZDF · Dritte · ARTE · DW", "Nationale Sender, Spartenprogramme und große Regionalprogramme."),
        Country("at", "Österreich", "ORF", "ORF-Inhalte über MediathekView; einzelne Titel können regional eingeschränkt sein."),
        Country("ch", "Schweiz", "SRF", "SRF-Inhalte über MediathekView; Auslandsverfügbarkeit ist titelabhängig."),
        Country("it", "Italien", "RaiPlay International", "Freie Rai-Inhalte; Geo-Sperren werden nicht umgangen."),
        Country("tr", "Türkei", "TRT · tabii", "Offizielle TRT-Angebote; Verfügbarkeit hängt vom jeweiligen Stream und Standort ab."),
        Country("fr", "Frankreich / International", "ARTE France · TV5MONDEplus", "Französische und internationale öffentlich zugängliche Angebote.")
    )

    val providers = listOf(
        Provider("ard", "de", "ARD / Das Erste", "ARD", "Deutschland: verfügbar"),
        Provider("zdf", "de", "ZDF", "ZDF", "Deutschland: verfügbar"),
        Provider("zdfneo", "de", "ZDFneo", "ZDFneo", "Deutschland: verfügbar"),
        Provider("zdfinfo", "de", "ZDFinfo", "ZDFinfo", "Deutschland: verfügbar"),
        Provider("3sat", "de", "3sat", "3sat", "D/A/CH: verfügbar"),
        Provider("kika", "de", "KiKA", "KiKA", "Deutschland: verfügbar"),
        Provider("phoenix", "de", "phoenix", "phoenix", "Deutschland: verfügbar"),
        Provider("one", "de", "ONE", "ONE", "Deutschland: verfügbar"),
        Provider("wdr", "de", "WDR", "WDR", "Deutschland: verfügbar"),
        Provider("ndr", "de", "NDR", "NDR", "Deutschland: verfügbar"),
        Provider("br", "de", "BR", "BR", "Deutschland: verfügbar"),
        Provider("swr", "de", "SWR", "SWR", "Deutschland: verfügbar"),
        Provider("mdr", "de", "MDR", "MDR", "Deutschland: verfügbar"),
        Provider("hr", "de", "hr", "HR", "Deutschland: verfügbar"),
        Provider("rbb", "de", "rbb", "RBB", "Deutschland: verfügbar"),
        Provider("sr", "de", "SR", "SR", "Deutschland: verfügbar"),
        Provider("arte", "de", "ARTE", "ARTE.DE", "Deutschland: meist verfügbar"),
        Provider("dw", "de", "DW", "DW", "International"),
        Provider("orf", "at", "ORF", "ORF", "Österreich / titelabhängig"),
        Provider("srf", "ch", "SRF", "SRF", "Schweiz / titelabhängig"),
        Provider("rai", "it", "RaiPlay International · freie Inhalte", availability = "Deutschland: titelabhängig", info = "Rai bleibt in v0.4.0 als transparenter Verfügbarkeits-Hinweis sichtbar; geschützte oder geo-gesperrte Inhalte werden nicht umgangen.", playable = false),
        Provider("trt", "tr", "TRT / tabii", availability = "International / streamabhängig", info = "TRT und tabii bleiben als Anbieterübersicht sichtbar. Es werden keine geschützten Webplayer umgangen.", playable = false),
        Provider("arte_fr", "fr", "ARTE France", "ARTE.FR", "Deutschland: meist nutzbar"),
        Provider("tv5", "fr", "TV5MONDEplus", availability = "International · kostenlos", info = "Anbieterübersicht; direkte native Wiedergabe wird erst bei einer stabilen offenen Stream-Schnittstelle aktiviert.", playable = false)
    )

    fun providers(countryId: String): List<Provider> = providers.filter { it.countryId == countryId }
    fun provider(id: String): Provider? = providers.firstOrNull { it.id == id }

    fun query(provider: Provider, term: String = "", size: Int = 60): List<MediaEntry> {
        if (!provider.playable || provider.channel.isBlank()) return emptyList()
        val queries = JSONArray().apply {
            put(JSONObject().apply {
                put("fields", JSONArray().put("channel"))
                put("query", provider.channel)
            })
            if (term.isNotBlank()) put(JSONObject().apply {
                put("fields", JSONArray().put("title").put("topic").put("description"))
                put("query", term.trim())
            })
        }
        val body = JSONObject().apply {
            put("queries", queries)
            put("sortBy", "timestamp")
            put("sortOrder", "desc")
            put("future", false)
            put("offset", 0)
            put("size", size.coerceIn(1, 120))
        }.toString()

        val connection = (URL(API_URL).openConnection() as HttpURLConnection).apply {
            requestMethod = "POST"
            connectTimeout = 12000
            readTimeout = 25000
            doOutput = true
            setRequestProperty("Content-Type", "application/json")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "EpiMediaHub-Android/0.4.0")
        }
        connection.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
        val code = connection.responseCode
        if (code !in 200..299) throw IllegalStateException("MediathekViewWeb HTTP $code")
        val root = JSONObject(connection.inputStream.bufferedReader().use { it.readText() })
        val rows = root.optJSONObject("result")?.optJSONArray("results") ?: JSONArray()
        return buildList {
            for (i in 0 until rows.length()) {
                val item = rows.optJSONObject(i) ?: continue
                val stream = sequenceOf("url_video_hd", "url_video", "url_video_low")
                    .map { item.optString(it).trim() }
                    .firstOrNull { it.startsWith("http") }
                    .orEmpty()
                if (stream.isBlank()) continue
                val title = item.optString("title").ifBlank { item.optString("topic") }.ifBlank { provider.label }
                val topic = item.optString("topic")
                val desc = item.optString("description")
                val channel = item.optString("channel")
                val timestamp = item.optLong("timestamp", 0L)
                val stable = (stream + title + timestamp).hashCode().toUInt().toString(16)
                add(
                    MediaEntry(
                        id = "mediathek:$stable",
                        name = title,
                        kind = MediaKind.MOVIE,
                        categoryId = provider.id,
                        image = item.optString("url_image").ifBlank { item.optString("url_image_small") },
                        plot = listOf(topic, channel, desc).filter { it.isNotBlank() }.joinToString(" · "),
                        streamUrl = stream,
                        extension = if (stream.contains(".m3u8", true)) "m3u8" else "mp4"
                    )
                )
            }
        }
    }
}
