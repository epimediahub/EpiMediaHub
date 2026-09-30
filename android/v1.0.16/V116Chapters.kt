package de.epimediahub.app.data

import androidx.media3.common.Metadata
import androidx.media3.common.Tracks
import androidx.media3.common.util.UnstableApi
import androidx.media3.extractor.metadata.id3.ChapterFrame
import androidx.media3.extractor.metadata.id3.TextInformationFrame

@androidx.annotation.OptIn(UnstableApi::class)
internal object V116Chapters {
    fun kind(title: String): V115SegmentKind? = when (title.trim().lowercase().replace(Regex("\\s+"), " ")) {
        "intro", "opening", "opening credits", "title sequence", "vorspann", "titelsequenz" -> V115SegmentKind.INTRO
        "recap", "previously on", "rückblick", "zusammenfassung", "previously" -> V115SegmentKind.RECAP
        "outro", "credits", "end credits", "ending credits", "abspann" -> V115SegmentKind.OUTRO
        else -> null
    }
    fun read(metadata: Metadata?, duration: Long): List<V115Segment> {
        if (metadata == null || duration <= 0) return emptyList()
        return (0 until metadata.length()).mapNotNull { index ->
            val frame = metadata[index] as? ChapterFrame ?: return@mapNotNull null
            val title = (0 until frame.subFrameCount).mapNotNull { frame.getSubFrame(it) as? TextInformationFrame }
                .firstOrNull { it.id == "TIT2" }?.values?.firstOrNull().orEmpty()
            val type = kind(title) ?: return@mapNotNull null
            V115Segment(type, frame.startTimeMs.toLong(), frame.endTimeMs.toLong(), "Videokapitel", true, 1.0)
                .takeIf { V115SkipPolicy.valid(it, duration) }
        }
    }
    fun read(tracks: Tracks, duration: Long): List<V115Segment> = tracks.groups.flatMap { group ->
        (0 until group.length).flatMap { read(group.getTrackFormat(it).metadata, duration) }
    }.distinctBy { Triple(it.kind, it.startMs, it.endMs) }
}
