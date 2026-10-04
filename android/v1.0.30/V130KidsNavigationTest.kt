package de.epimediahub.app.ui

import android.content.Context
import androidx.activity.OnBackPressedDispatcher
import androidx.activity.compose.LocalOnBackPressedDispatcherOwner
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.SideEffect
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createComposeRule
import de.epimediahub.app.data.V128ParentalControl
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import org.robolectric.annotation.LooperMode

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28], qualifiers = "w960dp-h540dp-land")
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@LooperMode(LooperMode.Mode.PAUSED)
class V130KidsNavigationTest {
    @get:Rule val compose = createComposeRule()
    private val app get() = RuntimeEnvironment.getApplication()
    private val store get() = V129KidsStore(app)
    private val parental get() = V128ParentalControl(app)
    private lateinit var back: OnBackPressedDispatcher
    private var closed = 0
    private var verified = 0

    @Before fun reset() {
        app.getSharedPreferences("epi_parental_v128", Context.MODE_PRIVATE).edit().clear().commit()
        app.getSharedPreferences("epi_smarttube_kids_v129", Context.MODE_PRIVATE).edit().clear().commit()
    }
    private fun settle() { compose.waitForIdle(); compose.mainClock.advanceTimeBy(300); compose.waitForIdle() }
    private fun show() {
        val rows = listOf(V100SmartTubeRow("Lernen", listOf(V100SmartTubeVideo("aaaaaaaaaaa", "Die Welt entdecken", "", "", "", 60000, false))))
        compose.setContent {
            val dispatcher = LocalOnBackPressedDispatcherOwner.current!!.onBackPressedDispatcher
            SideEffect { back = dispatcher }
            MaterialTheme {
                V130SmartTubeGateContent(Color.Cyan, true, onBack = { closed++ },
                    onEnterKids = {}, onPinVerified = { verified++ }, loadKids = { Result.success(rows) },
                    prepare = {}, normalContent = { Text("Normaler SmartTube-Bereich") })
            }
        }
        settle()
    }
    private fun pressBack() { compose.runOnIdle { back.onBackPressed() }; settle() }
    private fun enterPin(pin: String) {
        pin.forEach { compose.onNodeWithTag("pin-key-$it").performClick() }
        settle()
        compose.onNodeWithTag("pin-confirm").performClick()
    }

    @Test fun kidsOpensAndClosesWithoutCreatingAPin() {
        show()
        compose.onNodeWithTag("smarttube-kids").performClick(); settle()
        assertTrue(store.active())
        assertFalse(parental.settings().hasPin)
        compose.onNodeWithText("Eltern-PIN festlegen").assertDoesNotExist()
        compose.onNodeWithTag("kids-parents").assertTextContains("Zurück").performClick(); settle()
        assertFalse(store.active())
        assertFalse(parental.settings().hasPin)
        compose.onNodeWithTag("smarttube-normal").assertIsDisplayed()
    }

    @Test fun backLeavesARestoredKidsSessionWithoutPinAndCanCloseTheChooser() {
        store.enter(); show()
        pressBack()
        assertFalse(store.active())
        compose.onNodeWithTag("smarttube-normal").assertIsDisplayed()
        pressBack()
        assertEquals(1, closed)
        assertFalse(parental.settings().hasPin)
    }

    @Test fun existingPinProtectsExitAndWrongPinOrCancelCannotLeaveKids() {
        parental.setPin("1234"); store.enter(); show()
        compose.onNodeWithTag("kids-parents").assertTextContains("Eltern · PIN").performClick(); settle()
        enterPin("1111")
        compose.waitUntil(10_000) { compose.onAllNodesWithTag("pin-error").fetchSemanticsNodes().isNotEmpty() }
        assertTrue(store.active())
        compose.onNodeWithText("Abbrechen").performClick(); settle()
        assertTrue(store.active())
        compose.onNodeWithTag("kids-world").assertIsDisplayed()
        pressBack()
        compose.onNodeWithText("Elternbereich entsperren").assertIsDisplayed()
        enterPin("1234")
        compose.waitUntil(10_000) { !store.active() }; settle()
        assertEquals(1, verified)
        compose.onNodeWithTag("smarttube-normal").assertIsDisplayed()
        assertTrue(parental.settings().hasPin)
    }

    @Test fun anExistingPinDoesNotBlockEnteringKids() {
        parental.setPin("1234"); show()
        compose.onNodeWithTag("smarttube-kids").performClick(); settle()
        assertTrue(store.active())
        compose.onNodeWithText("Elternbereich entsperren").assertDoesNotExist()
        compose.onNodeWithTag("kids-parents").assertTextContains("Eltern · PIN")
    }
}
