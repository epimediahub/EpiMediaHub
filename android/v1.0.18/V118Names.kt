package de.epimediahub.app.ui

/** Presentation only: provider names, stream identifiers and resume keys stay intact. */
internal object V118Names {
    private val extension = Regex("""(?i)\.(?:mkv|mp4|m4v|avi|ts|webm)\s*$""")
    private val technicalSuffix = Regex(
        """(?i)(?:\s+|[._|:/\[\](){}–-]+)(?:""" +
            """(?:2160|1080|720|576|480)[pi]|4k|uhd|fhd|hd|sd|hdr10\+?|hdr|10bit|8bit|""" +
            """web(?:[ ._-]?(?:dl|rip|mux|hd))?|bluray|blu[ ._-]?ray|b[dr]rip|dvdrip|hdtv|h[de]vc|[xh][ ._-]?26[45]|av1|""" +
            """(?:ddp?|dd\+|eac3|ac3|aac|dts(?:[ ._-]?hd)?|truehd|atmos)(?:[ ._-]?[257][ ._-]?[01])?|""" +
            """(?:ita|it|eng|en|ger|deu|de|multi|dual)(?:[ ._-](?:ita|it|eng|en|ger|deu|de))*""" +
            """)[\s\])}]*$"""
    )
    private val trailingDivider = Regex("""[\s|:–-]+$""")

    fun display(raw: String): String {
        var value = raw.trim().replace(extension, "")
        repeat(32) {
            val match = technicalSuffix.find(value) ?: return value
            val trimmed = value.substring(0, match.range.first).replace(trailingDivider, "").trim()
            if (trimmed.isEmpty()) return value
            value = trimmed
        }
        return value
    }

    fun episode(raw: String, series: String, season: Int, episode: Int): String {
        var value = display(raw)
        val title = display(series)
        val code = Regex("""(?i)^(?:s\s*0*$season[ ._-]*e\s*0*$episode|0*$season\s*x\s*0*$episode)(?=\b|[ ._|:–-])""")
        if (title.isNotEmpty() && value.startsWith(title, ignoreCase = true)) {
            val remaining = value.substring(title.length)
            if (remaining.isEmpty()) return ""
            if (remaining.first().isWhitespace() || remaining.first() in "|:–-") {
                val tail = remaining.trimStart(' ', '|', ':', '–', '-')
                if (code.containsMatchIn(tail) || remaining.trimStart().firstOrNull() in listOf('|', ':', '–', '-')) value = tail
            }
        }
        return value.replace(code, "").trimStart(' ', '.', '_', '|', ':', '–', '-')
    }

    fun subtitle(raw: String, series: String, season: Int, episode: Int): String {
        val title = V118Names.episode(raw, series, season, episode)
        return "Staffel $season · Folge $episode" + if (title.isBlank()) "" else " · $title"
    }
}
