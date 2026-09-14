package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.json.JSONArray
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.ConcurrentHashMap

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

    data class Item(
        val media: MediaEntry,
        val channel: String,
        val topic: String,
        val description: String,
        val websiteUrl: String,
        val durationSeconds: Long,
        val timestamp: Long,
        val imageHint: String = ""
    ) {
        val id: String get() = media.id
    }

    val countries = listOf(
        Country("de", "Deutschland", "ARD · ZDF · Dritte · ARTE · DW", "Aktuelle Sendungen, Reportagen, Magazine, Nachrichten, Dokumentationen und Unterhaltung der öffentlich-rechtlichen Mediatheken."),
        Country("at", "Österreich", "ORF", "ORF-Inhalte über MediathekView; einzelne Titel können regional eingeschränkt sein."),
        Country("ch", "Schweiz", "SRF", "SRF-Inhalte über MediathekView; Auslandsverfügbarkeit ist titelabhängig."),
        Country("it", "Italien", "RaiPlay International", "Freie Rai-Inhalte; Geo-Sperren werden nicht umgangen."),
        Country("tr", "Türkei", "TRT · tabii", "Offizielle TRT-Angebote; Verfügbarkeit hängt vom jeweiligen Stream und Standort ab."),
        Country("fr", "Frankreich / International", "ARTE France · TV5MONDEplus", "Französische und internationale öffentlich zugängliche Angebote.")
    )

    val providers = listOf(
        Provider("ard", "de", "ARD / Das Erste", "ARD", "Deutschland: verfügbar", "Das Erste mit Nachrichten, Serien, Filmen, Magazinen, Dokumentationen und Unterhaltung."),
        Provider("zdf", "de", "ZDF", "ZDF", "Deutschland: verfügbar", "ZDF-Mediathek mit Nachrichten, Shows, Dokumentationen, Serien, Filmen und Sportbeiträgen."),
        Provider("zdfneo", "de", "ZDFneo", "ZDFneo", "Deutschland: verfügbar", "Serien, Comedy, Shows, Filme und junge Unterhaltungsformate von ZDFneo."),
        Provider("zdfinfo", "de", "ZDFinfo", "ZDFinfo", "Deutschland: verfügbar", "Dokumentationen, Geschichte, Gesellschaft, Politik, Wissen und Zeitgeschehen."),
        Provider("3sat", "de", "3sat", "3sat", "D/A/CH: verfügbar", "Kultur, Wissenschaft, Dokumentation und gesellschaftliche Themen aus Deutschland, Österreich und der Schweiz."),
        Provider("kika", "de", "KiKA", "KiKA", "Deutschland: verfügbar", "Kinder- und Familienprogramme, Wissen, Serien und Unterhaltung."),
        Provider("phoenix", "de", "phoenix", "phoenix", "Deutschland: verfügbar", "Politik, Ereignisübertragungen, Gespräche und Dokumentationen."),
        Provider("one", "de", "ONE", "ONE", "Deutschland: verfügbar", "Serien, Filme, Unterhaltung und ausgewählte ARD-Produktionen."),
        Provider("wdr", "de", "WDR", "WDR", "Deutschland: verfügbar", "Regionalprogramm aus Nordrhein-Westfalen mit Nachrichten, Reportagen, Kultur und Unterhaltung."),
        Provider("ndr", "de", "NDR", "NDR", "Deutschland: verfügbar", "Norddeutsche Nachrichten, Magazine, Reportagen, Dokumentationen und Unterhaltung."),
        Provider("br", "de", "BR", "BR", "Deutschland: verfügbar", "Bayerische Nachrichten, Wissen, Kultur, Reportagen und Unterhaltung."),
        Provider("swr", "de", "SWR", "SWR", "Deutschland: verfügbar", "Programme aus Baden-Württemberg und Rheinland-Pfalz mit Nachrichten, Wissen und Unterhaltung."),
        Provider("mdr", "de", "MDR", "MDR", "Deutschland: verfügbar", "Nachrichten, regionale Magazine, Dokumentationen und Unterhaltung aus Mitteldeutschland."),
        Provider("hr", "de", "hr", "HR", "Deutschland: verfügbar", "Hessische Nachrichten, Magazine, Wissen, Kultur und Unterhaltung."),
        Provider("rbb", "de", "rbb", "RBB", "Deutschland: verfügbar", "Berlin-Brandenburg mit Nachrichten, regionalen Themen, Kultur und Unterhaltung."),
        Provider("sr", "de", "SR", "SR", "Deutschland: verfügbar", "Saarländischer Rundfunk mit regionalen Nachrichten, Magazinen und Unterhaltung."),
        Provider("arte", "de", "ARTE", "ARTE.DE", "Deutschland: meist verfügbar", "Kultur, Dokumentationen, Filme, Serien, Konzerte und europäische Perspektiven."),
        Provider("dw", "de", "DW", "DW", "International", "Internationale Nachrichten, Hintergrundberichte, Dokumentationen und deutsche Perspektiven."),
        Provider("orf", "at", "ORF", "ORF", "Österreich / titelabhängig", "Nachrichten, Magazine, Unterhaltung, Serien und Dokumentationen des ORF."),
        Provider("srf", "ch", "SRF", "SRF", "Schweiz / titelabhängig", "Schweizer Nachrichten, Magazine, Unterhaltung, Serien und Dokumentationen."),
        Provider("rai", "it", "RaiPlay International · freie Inhalte", availability = "Deutschland: titelabhängig", info = "Rai bleibt als transparenter Verfügbarkeits-Hinweis sichtbar; geschützte oder geo-gesperrte Inhalte werden nicht umgangen.", playable = false),
        Provider("trt", "tr", "TRT / tabii", availability = "International / streamabhängig", info = "TRT und tabii bleiben als Anbieterübersicht sichtbar. Es werden keine geschützten Webplayer umgangen.", playable = false),
        Provider("arte_fr", "fr", "ARTE France", "ARTE.FR", "Deutschland: meist nutzbar", "Französische ARTE-Inhalte mit Kultur, Dokumentation, Film, Serien und Musik."),
        Provider("tv5", "fr", "TV5MONDEplus", availability = "International · kostenlos", info = "Anbieterübersicht; direkte native Wiedergabe wird erst bei einer stabilen offenen Stream-Schnittstelle aktiviert.", playable = false)
    )

    private val artworkCache = ConcurrentHashMap<String, String>()

    fun providers(countryId: String): List<Provider> = providers.filter { it.countryId == countryId }
    fun provider(id: String): Provider? = providers.firstOrNull { it.id == id }

    fun query(provider: Provider, term: String = "", size: Int = 60): List<Item> {
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
            setRequestProperty("Content-Type", "text/plain; charset=utf-8")
            setRequestProperty("Accept", "application/json")
            setRequestProperty("User-Agent", "EpiMediaHub-Android/0.4.2")
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
                val topic = item.optString("topic").trim()
                val desc = item.optString("description").trim()
                val channel = item.optString("channel").trim().ifBlank { provider.label }
                val timestamp = item.optLong("timestamp", 0L)
                val duration = item.optLong("duration", 0L)
                val website = item.optString("url_website").trim()
                val imageHint = sequenceOf("url_image", "url_image_small", "image", "thumbnail")
                    .map { item.optString(it).trim() }
                    .firstOrNull { it.startsWith("http") }
                    .orEmpty()
                val stable = item.optString("id").takeIf { it.isNotBlank() }
                    ?: (stream + title + timestamp).hashCode().toUInt().toString(16)

                val media = MediaEntry(
                    id = "mediathek:${stable.hashCode().toUInt().toString(16)}",
                    name = title,
                    kind = MediaKind.MOVIE,
                    categoryId = provider.id,
                    image = imageHint,
                    plot = desc.ifBlank { topic },
                    streamUrl = stream,
                    extension = if (stream.contains(".m3u8", true)) "m3u8" else "mp4"
                )
                add(Item(media, channel, topic, desc, website, duration, timestamp, imageHint))
            }
        }
    }

    fun resolveArtwork(item: Item): String {
        if (item.imageHint.startsWith("http")) return item.imageHint
        val page = item.websiteUrl
        if (!page.startsWith("http")) return ""
        artworkCache[page]?.let { return it }

        val resolved = runCatching {
            val connection = (URL(page).openConnection() as HttpURLConnection).apply {
                connectTimeout = 7000
                readTimeout = 9000
                instanceFollowRedirects = true
                setRequestProperty("User-Agent", "Mozilla/5.0 (Android) EpiMediaHub/0.4.2")
                setRequestProperty("Accept", "text/html,application/xhtml+xml")
            }
            if (connection.responseCode !in 200..399) return@runCatching ""
            val html = connection.inputStream.bufferedReader().use { reader ->
                val out = StringBuilder()
                val buf = CharArray(8192)
                while (out.length < 450_000) {
                    val n = reader.read(buf)
                    if (n <= 0) break
                    out.append(buf, 0, n)
                }
                out.toString()
            }
            val first = Regex(
                """<meta[^>]+(?:property|name)\\s*=\\s*[\"'](?:og:image(?::secure_url)?|twitter:image)[\"'][^>]+content\\s*=\\s*[\"']([^\"']+)[\"'][^>]*>""",
                RegexOption.IGNORE_CASE
            ).find(html)?.groupValues?.getOrNull(1)
            val second = Regex(
                """<meta[^>]+content\\s*=\\s*[\"']([^\"']+)[\"'][^>]+(?:property|name)\\s*=\\s*[\"'](?:og:image(?::secure_url)?|twitter:image)[\"'][^>]*>""",
                RegexOption.IGNORE_CASE
            ).find(html)?.groupValues?.getOrNull(1)
            val raw = (first ?: second).orEmpty()
                .replace("&amp;", "&")
                .replace("&#38;", "&")
                .trim()
            if (raw.isBlank()) "" else URL(URL(page), raw).toString()
        }.getOrDefault("")

        artworkCache[page] = resolved
        return resolved
    }
}
