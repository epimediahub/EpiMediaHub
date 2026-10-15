package de.epimediahub.app.data
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test

class V167HistoryIdentityTest {
    private fun episode(id: String, series: String, profile: String = "4k", title: String = "MobLand") =
        MediaEntry(id = id, name = title, kind = MediaKind.EPISODE, seriesId = series, sourceProfileId = profile)

    @Test fun sameSeriesUsesOneHistoryCard() {
        assertEquals(V167HistoryIdentity.key(episode("9","mobland")),
                     V167HistoryIdentity.key(episode("10","mobland")))
    }
    @Test fun playlistsAndSeriesRemainSeparate() {
        assertNotEquals(V167HistoryIdentity.key(episode("9","mobland")),
                        V167HistoryIdentity.key(episode("9","chicago")))
        assertNotEquals(V167HistoryIdentity.key(episode("9","mobland")),
                        V167HistoryIdentity.key(episode("9","mobland","the-best")))
    }
    @Test fun m3uNeedsExplicitSeriesName() {
        assertEquals(V167HistoryIdentity.key(episode("9","",title="MobLand S01E09")),
                     V167HistoryIdentity.key(episode("10","",title="MobLand S01E10")))
        assertNotEquals(V167HistoryIdentity.key(episode("9","",title="Folge 9")),
                        V167HistoryIdentity.key(episode("10","",title="Folge 10")))
    }
}
