package de.epimediahub.app.ui

import androidx.media3.common.C
import androidx.media3.common.Player
import androidx.media3.common.TrackGroup
import androidx.media3.common.TrackSelectionOverride
import androidx.media3.common.Tracks
import androidx.media3.common.util.UnstableApi
import java.util.Locale

internal data class V115TrackChoice(
    val group: TrackGroup, val index: Int, val label: String, val language: String,
    val type: Int, val selected: Boolean
)

@androidx.annotation.OptIn(UnstableApi::class)
internal object V115Tracks {
    fun language(code: String?): String = when (code?.lowercase(Locale.ROOT)) {
        "deu", "ger" -> "de"; "eng" -> "en"; "ita" -> "it"; "fra", "fre" -> "fr"
        "spa" -> "es"; "tur" -> "tr"; "por" -> "pt"; "jpn" -> "ja"; "rus" -> "ru"
        "und", "", null -> ""; else -> code.orEmpty()
    }

    fun choices(tracks: Tracks, type: Int): List<V115TrackChoice> = tracks.groups.filter { it.type == type }.flatMap { group ->
        (0 until group.length).mapNotNull { index ->
            if (!group.isTrackSupported(index)) return@mapNotNull null
            val f = group.getTrackFormat(index)
            val code = language(f.language)
            val display = if (code.isBlank()) "Sprache nicht angegeben" else Locale.forLanguageTag(code).getDisplayLanguage(Locale.GERMAN).ifBlank { code }
            val extras = buildList {
                f.label?.takeIf { it.isNotBlank() && !it.equals(display, true) }?.let(::add)
                if (type == C.TRACK_TYPE_AUDIO) {
                    if (f.channelCount > 0) add(when (f.channelCount) { 1 -> "Mono"; 2 -> "Stereo"; 6 -> "5.1"; 8 -> "7.1"; else -> "${f.channelCount} Kanäle" })
                    when (f.sampleMimeType) { "audio/ac3" -> add("Dolby Digital"); "audio/eac3", "audio/eac3-joc" -> add("Dolby Digital Plus"); "audio/vnd.dts" -> add("DTS") }
                    if (f.roleFlags and C.ROLE_FLAG_DESCRIBES_VIDEO != 0) add("Audiodeskription")
                } else {
                    if (f.selectionFlags and C.SELECTION_FLAG_FORCED != 0) add("Erzwungen")
                    if (f.roleFlags and C.ROLE_FLAG_CAPTION != 0) add("Hörgeschädigte")
                }
            }
            V115TrackChoice(group.mediaTrackGroup, index, (listOf(display) + extras).joinToString(" · "), code, type, group.isTrackSelected(index))
        }
    }

    fun select(player: Player, choice: V115TrackChoice) {
        player.trackSelectionParameters = player.trackSelectionParameters.buildUpon()
            .clearOverridesOfType(choice.type).setTrackTypeDisabled(choice.type, false)
            .setOverrideForType(TrackSelectionOverride(choice.group, listOf(choice.index))).build()
    }

    fun subtitlesOff(player: Player) {
        player.trackSelectionParameters = player.trackSelectionParameters.buildUpon()
            .clearOverridesOfType(C.TRACK_TYPE_TEXT).setTrackTypeDisabled(C.TRACK_TYPE_TEXT, true).build()
    }
}
