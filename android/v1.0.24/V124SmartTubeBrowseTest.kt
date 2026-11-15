package de.epimediahub.app.ui

import android.graphics.Bitmap
import android.graphics.Canvas
import androidx.activity.OnBackPressedDispatcher
import androidx.activity.compose.LocalOnBackPressedDispatcherOwner
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import org.junit.Assert.*
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode
import java.io.File

@OptIn(ExperimentalTestApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V124SmartTubeBrowseTest {
    @get:Rule val compose=createComposeRule()
    private fun video(id:String)=V100SmartTubeVideo(id,"Video $id","Testkanal","","",120_000,false)
    private var videos by mutableStateOf(listOf(video("one"),video("two"),video("three")))
    private var loading by mutableStateOf(false)
    private var error by mutableStateOf("")
    private var current by mutableStateOf("playing")
    private var selected=""
    private var toggled=0
    private var seeked=0L
    private var exited=0
    private var mounts=0
    private var unmounts=0
    private lateinit var back:OnBackPressedDispatcher
    private lateinit var view:android.view.View
    private fun settle(){compose.waitForIdle();compose.mainClock.advanceTimeBy(250);compose.waitForIdle()}
    private fun launch(){
        compose.setContent {
            back=LocalOnBackPressedDispatcherOwner.current!!.onBackPressedDispatcher
            view=LocalView.current
            MaterialTheme {
                V124SmartTubeBrowseLayer(current,true,Color(0xFF6DD6F5),videos,loading,error,null,
                    onVideo={selected=it.videoId},onRetry={},onTogglePlayback={toggled++},onSeek={seeked+=it},
                    onShowControls={},onExit={exited++}) {
                    DisposableEffect(Unit){mounts++;onDispose{unmounts++}}
                    Box(Modifier.fillMaxSize().background(Color(0xFF304253)).testTag("continuing-video"))
                }
            }
        };settle()
    }
    private fun press(key:Key){compose.onNodeWithTag("smarttube-player-remote").performKeyInput{keyDown(key);keyUp(key)};settle()}

    @Test fun downBrowsesWhileVideoStaysMountedAndCardKeysNeverSeekOrPause(){
        launch();press(Key.DirectionDown)
        compose.onNodeWithTag("smarttube-video-shelf").assertIsDisplayed()
        compose.onNodeWithTag("smarttube-suggestion-one").assertIsFocused()
        press(Key.DirectionRight)
        compose.onNodeWithTag("smarttube-suggestion-two").assertIsFocused()
        press(Key.Enter)
        assertEquals("two",selected);assertEquals(0,toggled);assertEquals(0L,seeked)
        assertEquals(1,mounts);assertEquals(0,unmounts)
        compose.runOnIdle {
            val bitmap=Bitmap.createBitmap(view.width,view.height,Bitmap.Config.ARGB_8888)
            view.draw(Canvas(bitmap));val dir=File("build/reports/ui").apply{mkdirs()}
            File(dir,"v124-smarttube-video-shelf-tv.png").outputStream().use{bitmap.compress(Bitmap.CompressFormat.PNG,100,it)}
            bitmap.recycle()
        }
    }

    @Test fun upRestoresPlaybackKeysAndBackClosesTheShelfBeforeLeavingPlayer(){
        launch();press(Key.DirectionDown);press(Key.DirectionUp)
        compose.onNodeWithTag("smarttube-video-shelf").assertDoesNotExist()
        compose.onNodeWithTag("smarttube-player-remote").assertIsFocused()
        press(Key.DirectionRight);press(Key.Enter)
        assertEquals(10_000L,seeked);assertEquals(1,toggled)
        press(Key.DirectionDown)
        compose.runOnIdle{back.onBackPressed()};settle()
        assertEquals(0,exited)
        compose.onNodeWithTag("smarttube-video-shelf").assertDoesNotExist()
        compose.runOnIdle{back.onBackPressed()};settle();assertEquals(1,exited)
    }

    @Test fun asyncResultsTakeFocusAfterEmptyLoadingStateAndNewVideoClosesShelf(){
        videos=emptyList();loading=true;launch();press(Key.DirectionDown)
        compose.onNodeWithTag("smarttube-shelf-close").assertIsFocused()
        compose.runOnIdle{videos=listOf(video("loaded"));loading=false};settle()
        compose.onNodeWithTag("smarttube-suggestion-loaded").assertIsFocused()
        compose.runOnIdle{current="loaded"};settle()
        compose.onNodeWithTag("smarttube-video-shelf").assertDoesNotExist()
        assertEquals(0,unmounts)
    }

    @Test @Config(qualifiers="w640dp-h360dp-land")
    fun smallTvShowsSelectableCardsAndKeepsFocusOnRefresh(){
        launch();press(Key.DirectionDown);press(Key.DirectionRight)
        compose.onNodeWithTag("smarttube-suggestion-two").assertIsDisplayed().assertIsFocused()
        compose.runOnIdle{videos=videos+video("four")};settle()
        compose.onNodeWithTag("smarttube-suggestion-two").assertIsFocused()
    }

    @Test fun failedRecommendationRequestLeavesPlaybackAndCloseActionAvailable(){
        videos=emptyList();error="Passende Videos konnten nicht geladen werden.";launch();press(Key.DirectionDown)
        compose.onNodeWithText(error).assertIsDisplayed()
        compose.onNodeWithTag("smarttube-shelf-retry").assertIsDisplayed()
        compose.onNodeWithTag("smarttube-shelf-close").assertIsFocused()
        press(Key.Enter);compose.onNodeWithTag("smarttube-video-shelf").assertDoesNotExist()
        assertEquals(0,exited);assertEquals(0,toggled);assertEquals(0,unmounts)
    }
}
