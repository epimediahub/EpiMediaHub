package de.epimediahub.app.data

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.*
import java.net.URI
import java.net.URLEncoder
import java.text.Normalizer
import java.util.Locale

internal val radioJson = Json { ignoreUnknownKeys = true; encodeDefaults = true }

@Serializable
internal data class RadioStation(
    val uuid: String,
    val name: String,
    val streamUrl: String,
    val logo: String = "",
    val countryCode: String = "",
    val languages: String = "",
    val tags: String = "",
    val codec: String = "",
    val bitrate: Int = 0,
    val hls: Boolean = false,
    val clicks: Int = 0
) {
    val country: String get() = radioCountryName(countryCode)
    val description: String get() = listOf(country, languages.split(',').take(2).joinToString(" / ") { radioLanguageName(it.trim()) },
        codec.takeIf { it.isNotBlank() }?.let { if (bitrate > 0) "$it · $bitrate kbit/s" else it }.orEmpty())
        .filter { it.isNotBlank() }.joinToString(" · ")
}

internal data class RadioOption(val id: String, val label: String, val count: Int = 0)
internal data class RadioCategory(val id: String, val label: String, val tags: List<String>, val topic: Boolean = false)

internal val radioCategories = listOf(
    RadioCategory("pop", "Pop", listOf("pop")),
    RadioCategory("rock", "Rock & Metal", listOf("rock", "metal")),
    RadioCategory("dance", "Dance & Electronic", listOf("dance", "house", "techno", "electronic")),
    RadioCategory("hiphop", "Hip-Hop & Rap", listOf("hip hop", "hip-hop", "rap")),
    RadioCategory("schlager", "Schlager", listOf("schlager")),
    RadioCategory("jazz", "Jazz & Blues", listOf("jazz", "blues")),
    RadioCategory("classical", "Klassik", listOf("classical", "klassik")),
    RadioCategory("oldies", "Oldies · 70er bis 90er", listOf("oldies", "70s", "80s", "90s")),
    RadioCategory("latin", "Latin & Reggae", listOf("latin", "salsa", "reggae")),
    RadioCategory("country", "Country", listOf("country")),
    RadioCategory("soul", "Soul & R&B", listOf("soul", "rnb", "r&b")),
    RadioCategory("relax", "Entspannung", listOf("ambient", "chillout", "relax")),
    RadioCategory("news", "Nachrichten", listOf("news", "nachrichten", "notizie"), true),
    RadioCategory("sport", "Sport", listOf("sport"), true),
    RadioCategory("talk", "Talk & Kultur", listOf("talk", "culture", "kultur"), true),
    RadioCategory("kids", "Kinder", listOf("kids", "children", "kinder", "bambini"), true)
)

internal data class RadioQuery(
    val name: String = "",
    val countryCode: String = "",
    val language: String = "",
    val categoryId: String = ""
) {
    val category: RadioCategory? get() = radioCategories.firstOrNull { it.id == categoryId }
    fun path(tag: String?, offset: Int, limit: Int): String {
        val values = linkedMapOf("hidebroken" to "true", "order" to "clickcount", "reverse" to "true",
            "limit" to limit.coerceIn(1, 60).toString(), "offset" to offset.coerceAtLeast(0).toString())
        if (name.isNotBlank()) values["name"] = name.trim().take(120)
        if (countryCode.isNotBlank()) values["countrycode"] = countryCode.uppercase(Locale.ROOT)
        if (language.isNotBlank()) values["language"] = language
        if (!tag.isNullOrBlank()) values["tag"] = tag
        return "/json/stations/search?" + values.entries.joinToString("&") { (key, value) ->
            "$key=${URLEncoder.encode(value, "UTF-8")}"
        }
    }
    fun accepts(station: RadioStation): Boolean =
        (name.isBlank() || radioNormalized(station.name).contains(radioNormalized(name))) &&
        (countryCode.isBlank() || station.countryCode.equals(countryCode, true)) &&
        (language.isBlank() || station.languages.split(',').any { it.trim().contains(language, true) }) &&
        (category == null || category!!.tags.any { alias -> station.tags.split(',').any { it.trim().contains(alias, true) } })
}

internal fun radioHttpUrl(value: String): Boolean = runCatching {
    val uri = URI(value)
    uri.scheme?.lowercase(Locale.ROOT) in listOf("http", "https") && !uri.host.isNullOrBlank() && uri.userInfo == null
}.getOrDefault(false)

internal fun radioStationFromApi(value: JsonObject): RadioStation? {
    fun str(key: String) = (value[key] as? JsonPrimitive)?.contentOrNull.orEmpty().trim()
    fun number(key: String) = str(key).toIntOrNull() ?: 0
    val uuid = str("stationuuid")
    val url = str("url_resolved").takeIf(::radioHttpUrl) ?: str("url").takeIf(::radioHttpUrl) ?: return null
    if (!uuid.matches(Regex("[a-zA-Z0-9-]{1,64}")) || str("name").isBlank() || str("lastcheckok") !in listOf("1", "true")) return null
    return RadioStation(uuid, str("name").take(200), url,
        str("favicon").takeIf(::radioHttpUrl).orEmpty(), str("countrycode").uppercase(Locale.ROOT),
        str("language"), str("tags"), str("codec"), number("bitrate"), str("hls") in listOf("1", "true"), number("clickcount"))
}

internal fun radioUniqueStations(values: List<RadioStation>): List<RadioStation> {
    val ids = mutableSetOf<String>(); val urls = mutableSetOf<String>()
    return values.sortedByDescending { it.clicks }.filter {
        val url = runCatching { URI(it.streamUrl).normalize().toASCIIString().trimEnd('/') }.getOrDefault(it.streamUrl)
        if (it.uuid in ids || url in urls) false else { ids += it.uuid; urls += url; true }
    }
}

internal fun radioPlaybackQueue(values: List<RadioStation>, selected: RadioStation): List<RadioStation> {
    val stations = values.distinctBy { it.uuid }.toMutableList()
    if (stations.none { it.uuid == selected.uuid }) stations.add(0, selected)
    val index = stations.indexOfFirst { it.uuid == selected.uuid }
    val first = (index - 100).coerceAtLeast(0).coerceAtMost((stations.size - 200).coerceAtLeast(0))
    return stations.drop(first).take(200)
}

internal fun radioNormalized(value: String): String = Normalizer.normalize(value, Normalizer.Form.NFD)
    .replace(Regex("\\p{M}+"), "").lowercase(Locale.ROOT).trim()

internal fun radioCountryName(code: String): String = if (code.isBlank()) "" else
    Locale("", code).getDisplayCountry(Locale.GERMAN).ifBlank { code }

internal fun radioLanguageName(value: String): String = when (value.lowercase(Locale.ROOT)) {
    "german", "deutsch" -> "Deutsch"; "italian", "italiano" -> "Italienisch"; "english" -> "Englisch"
    "french", "français" -> "Französisch"; "spanish", "español" -> "Spanisch"; "portuguese" -> "Portugiesisch"
    "turkish" -> "Türkisch"; "greek" -> "Griechisch"; "arabic" -> "Arabisch"; "russian" -> "Russisch"
    "polish" -> "Polnisch"; "dutch" -> "Niederländisch"; "chinese" -> "Chinesisch"; "japanese" -> "Japanisch"
    "ukrainian" -> "Ukrainisch"; "hindi" -> "Hindi"; "romanian" -> "Rumänisch"; "persian" -> "Persisch"
    else -> value.replaceFirstChar { it.titlecase(Locale.GERMAN) }
}
