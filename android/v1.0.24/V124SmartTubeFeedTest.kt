package de.epimediahub.app.ui

import com.liskovsoft.mediaserviceinterfaces.data.MediaGroup
import com.liskovsoft.mediaserviceinterfaces.data.MediaItem
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.runBlocking
import org.junit.Assert.*
import org.junit.Test
import java.lang.reflect.Proxy

class V124SmartTubeFeedTest {
    private inline fun <reified T> fake(values: Map<String, Any?>): T =
        Proxy.newProxyInstance(T::class.java.classLoader, arrayOf(T::class.java)) { _, method, _ ->
            if (values.containsKey(method.name)) values[method.name] else when (method.returnType) {
                java.lang.Boolean.TYPE -> false
                java.lang.Integer.TYPE -> 0
                java.lang.Long.TYPE -> 0L
                java.lang.Double.TYPE -> 0.0
                else -> null
            }
        } as T
    private fun video(id: String, watched: Int = 0, live: Boolean = false, shorts: Boolean = false) =
        fake<MediaItem>(mapOf("getVideoId" to id, "getTitle" to id, "getPercentWatched" to watched,
            "isLive" to live, "isShorts" to shorts, "getDurationMs" to 100_000L))
    private fun group(title: String, items: List<MediaItem>, next: String? = null) =
        fake<MediaGroup>(mapOf("getTitle" to title, "getMediaItems" to items, "getNextPageKey" to next,
            "getType" to MediaGroup.TYPE_SUGGESTIONS))

    @Test fun relatedFeedExcludesCurrentWatchedShortsAndDuplicatesAcrossShelves() = runBlocking {
        val groups = listOf(group("A", listOf(video("current"),video("local"),video("remote",90),video("first"),video("short",shorts=true))),
            group("B", listOf(video("first"),video("second"),video("live",100,true))))
        var saved = emptySet<String>()
        val result = V124SmartTubeFeed.rows(groups,setOf("local"),setOf("current"),{null},{saved=it})
        assertEquals(listOf("first","second","live"),result.flatMap { it.videos }.map { it.videoId })
        assertEquals(setOf("remote"), saved)
    }

    @Test fun emptyFilteredShelvesRefillFromRealContinuationPagesInProviderOrder() = runBlocking {
        val requested = ArrayList<String>()
        val start = group("Passend",listOf(video("seen",95)),"page1")
        val result = V124SmartTubeFeed.rows(listOf(start),emptySet(),continueGroup={
            requested.add(it.nextPageKey)
            if(it.nextPageKey=="page1") group("Passend",listOf(video("seen",100)),"page2")
            else group("Passend",listOf(video("fresh1"),video("fresh2")))
        })
        assertEquals(listOf("page1","page2"),requested)
        assertEquals(listOf("fresh1","fresh2"),result.single().videos.map { it.videoId })
    }

    @Test fun loopingTokensAndTotalRequestsAreBounded() = runBlocking {
        var calls=0
        val groups=(1..8).map { group("Shelf$it",listOf(video("seen",100)),"same") }
        V124SmartTubeFeed.rows(groups,emptySet(),continueGroup={calls++;it})
        assertEquals(4,calls)
    }

    @Test fun continuationFailureKeepsAlreadyLoadedVideos() = runBlocking {
        val result=V124SmartTubeFeed.rows(listOf(group("A",listOf(video("keep")),"next")),emptySet(),
            continueGroup={throw IllegalStateException("offline")})
        assertEquals("keep",result.single().videos.single().videoId)
    }

    @Test fun cancellationStopsRefillInsteadOfReturningStaleAccountResults() = runBlocking {
        try {
            V124SmartTubeFeed.rows(listOf(group("A",emptyList(),"next")),emptySet(),
                continueGroup={throw CancellationException("account changed")})
            fail("Cancellation must reach the caller")
        } catch (_: CancellationException) { }
    }

    @Test fun explicitHistoryKeepsVideosButRecommendationRowsShareOneDuplicateFilter() {
        val v=V100SmartTubeVideo("same","Video","","","",100L,false)
        val rows=listOf(V100SmartTubeRow("A",listOf(v)),V100SmartTubeRow("B",listOf(v)))
        assertEquals(1,V112SmartTubeSuggestions.visible(rows,emptySet(),true).size)
        assertEquals(2,V112SmartTubeSuggestions.visible(rows,setOf("same"),false).size)
        assertTrue(V112SmartTubeSuggestions.related(rows,"same",emptySet()).isEmpty())
    }
}
