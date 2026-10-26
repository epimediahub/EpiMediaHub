package de.epimediahub.app.data

import android.content.Context
import androidx.media3.common.Metadata
import androidx.media3.extractor.metadata.id3.ChapterFrame
import androidx.media3.extractor.metadata.id3.Id3Frame
import androidx.media3.extractor.metadata.id3.TextInformationFrame
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V116SkipPolicyTest {
    private val context: Context get() = RuntimeEnvironment.getApplication()
    private val item = MediaEntry("81", "Folge 1", MediaKind.EPISODE, "Dark", streamUrl = "https://provider.example/series/account/secret/81.mkv", seriesId = "24", season = 1, episode = 1)
    private val duration = 2_400_000L
    @Before fun clear() { context.getSharedPreferences("v116_own_skip", Context.MODE_PRIVATE).edit().clear().commit() }

    @Test fun normalizesNestedCountryAndQualityLabelsWithoutChangingMeaningfulTitles() {
        assertEquals("Dark", V116Names.clean("[DE] GER | Dark (2017) FHD HEVC"))
        assertEquals("Doctor Who", V116Names.clean("[IT] Doctor Who [HD]"))
        assertEquals("The End", V116Names.clean("The End"))
    }
    @Test fun providerFileKeyIsIndependentOfCredentialsButNeverOfHostOrFile() {
        assertEquals(V116SkipKeys.asset(item), V116SkipKeys.asset(item.copy(streamUrl = "https://provider.example/series/other-user/other-secret/81.mkv")))
        assertNotEquals(V116SkipKeys.asset(item), V116SkipKeys.asset(item.copy(streamUrl = "https://other.example/series/account/secret/81.mkv")))
        assertNotEquals(V116SkipKeys.asset(item), V116SkipKeys.asset(item.copy(streamUrl = "https://provider.example/series/account/secret/82.mkv")))
        assertFalse(V116SkipKeys.asset(item).contains("secret"))
    }
    @Test fun arbitraryM3uPathsDoNotGetCollapsedIntoOneSharedFile() {
        val a = item.copy(streamUrl = "https://provider.example/a/episode.mkv")
        assertNotEquals(V116SkipKeys.asset(a), V116SkipKeys.asset(a.copy(streamUrl = "https://provider.example/b/episode.mkv")))
    }
    @Test fun aManualMarkSurvivesRecreationAndOverridesTheSameKind() {
        val repo = V116SkipRepository(context)
        assertTrue(repo.save(item, duration, V115SegmentKind.INTRO, 30_000L, 90_000L))
        val public = V115Segment(V115SegmentKind.INTRO, 150_000, 180_000, "Public", true, 1.0)
        val merged = V116SkipRepository(context).merge(item, duration, listOf(public))
        assertEquals(1, merged.size); assertEquals(30_000L, merged.single().startMs); assertEquals(90_000L, merged.single().endMs)
    }
    @Test fun explicitlyMissingIntroDoesNotDisableOtherKinds() {
        val repo = V116SkipRepository(context)
        assertTrue(repo.save(item, duration, V115SegmentKind.INTRO, null, null, disabled = true))
        val markers = listOf(V115Segment(V115SegmentKind.INTRO, 30_000, 90_000, "Public", true, 1.0), V115Segment(V115SegmentKind.OUTRO, 2_300_000, duration, "Public", true, 1.0))
        assertEquals(listOf(V115SegmentKind.OUTRO), repo.merge(item, duration, markers).map { it.kind })
    }
    @Test fun aChangedRuntimeOrFileDoesNotReuseAManualMark() {
        val repo = V116SkipRepository(context)
        repo.save(item, duration, V115SegmentKind.INTRO, 30_000, 90_000)
        assertTrue(repo.merge(item, duration + 10_000, emptyList()).isEmpty())
        assertTrue(repo.merge(item.copy(streamUrl = "https://provider.example/series/a/b/82.mkv"), duration, emptyList()).isEmpty())
    }
    @Test fun rejectsNegativeReversedAndOutOfBoundsMarks() {
        val repo = V116SkipRepository(context)
        assertFalse(repo.save(item, duration, V115SegmentKind.INTRO, -1, 10_000))
        assertFalse(repo.save(item, duration, V115SegmentKind.INTRO, 90_000, 30_000))
        assertFalse(repo.save(item, duration, V115SegmentKind.OUTRO, duration - 10_000, duration + 1))
        assertTrue(repo.overrides(item, duration).isEmpty())
    }
    @Test fun centralDisableSuppressesChapterFallbackButOwnCorrectionWins() {
        val repo = V116SkipRepository(context)
        val chapter = V115Segment(V115SegmentKind.INTRO, 30_000, 90_000, "Videokapitel", true, 1.0)
        assertTrue(repo.merge(item, duration, listOf(chapter), setOf(V115SegmentKind.INTRO)).isEmpty())
        repo.save(item, duration, V115SegmentKind.INTRO, 40_000, 80_000)
        assertEquals(40_000L, repo.merge(item, duration, listOf(chapter), setOf(V115SegmentKind.INTRO)).single().startMs)
    }
    @Test fun onlyExplicitAndBoundedChapterNamesBecomeSkipActions() {
        fun chapter(name: String, start: Int, end: Int) = ChapterFrame("chapter", start, end, -1, -1, arrayOf<Id3Frame>(TextInformationFrame("TIT2", null, listOf(name))))
        val metadata = Metadata(chapter("Intro", 30_000, 90_000), chapter("Kapitel 1", 90_000, 180_000), chapter("Intro", 0, -1), chapter("Post credits scene", 2_300_000, 2_350_000))
        assertEquals(1, V116Chapters.read(metadata, duration).size)
        assertEquals(V115SegmentKind.INTRO, V116Chapters.read(metadata, duration).single().kind)
        assertNull(V116Chapters.kind("The end")); assertNull(V116Chapters.kind("Final scene"))
    }
}
