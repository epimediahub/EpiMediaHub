package de.epimediahub.app.data
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

/** Card identity only. Per-episode saved positions are never changed. */
internal object V167HistoryIdentity {
    fun key(item: MediaEntry): String {
        val profile = item.sourceProfileId
        if (item.kind != MediaKind.EPISODE) return "$profile|${item.kind}|${item.resumeKey}"
        val series = item.seriesId.trim()
        if (series.isNotBlank() && series != "0") return "$profile|series-id|$series"
        // M3U fallback only when a title explicitly includes S01E10 or 1x10.
        val title = Regex("""(?i)^(.+?)[\s._-]+(?:s\d{1,2}[ ._-]*e\d{1,3}|\d{1,2}x\d{1,3})(?:\b|$)""")
            .find(item.name)?.groupValues?.getOrNull(1)?.trim(' ', '-', '.', '_')?.lowercase().orEmpty()
        if (title.length >= 3) return "$profile|series-title|$title"
        return "$profile|episode|${item.resumeKey}"
    }
}
