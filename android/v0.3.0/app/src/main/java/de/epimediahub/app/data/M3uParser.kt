package de.epimediahub.app.data

import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.net.HttpURLConnection
import java.net.URL

object M3uParser {
    data class Result(val entries: List<MediaEntry>, val groups: List<String>, val epgUrl: String = "")

    fun download(url: String): Result {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 12000
            readTimeout = 25000
            setRequestProperty("User-Agent", "EpiMediaHub-Android/0.3")
        }
        return c.inputStream.bufferedReader().use { parse(it.readText()) }
    }

    fun parse(text: String): Result {
        val out = mutableListOf<MediaEntry>()
        var meta = ""
        var idx = 0
        var epgUrl = ""
        fun attr(line: String, key: String) = Regex("$key=\\\"([^\\\"]*)\\\"", RegexOption.IGNORE_CASE)
            .find(line)?.groupValues?.getOrNull(1).orEmpty()
        text.lineSequence().forEach { raw ->
            val line = raw.trim()
            when {
                line.startsWith("#EXTM3U", true) -> epgUrl = attr(line, "url-tvg").ifBlank { attr(line, "x-tvg-url") }
                line.startsWith("#EXTINF", true) -> meta = line
                line.isNotBlank() && !line.startsWith("#") && meta.isNotBlank() -> {
                    val name = meta.substringAfterLast(',', attr(meta, "tvg-name").ifBlank { "Sender ${idx + 1}" }).trim()
                    val group = attr(meta, "group-title").ifBlank { "Andere" }
                    out += MediaEntry(
                        id = "m3u_${idx++}", name = name, kind = MediaKind.LIVE, categoryId = group,
                        image = attr(meta, "tvg-logo"), streamUrl = line,
                        epgId = attr(meta, "tvg-id").ifBlank { attr(meta, "tvg-name") }
                    )
                    meta = ""
                }
            }
        }
        return Result(out, out.map { it.categoryId }.distinct().sorted(), epgUrl)
    }
}
