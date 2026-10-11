package de.epimediahub.app.ui

import android.content.Context
import android.content.Intent
import androidx.test.core.app.ApplicationProvider
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner

@RunWith(RobolectricTestRunner::class)
class V159BootAutostartTest {
    private val context = ApplicationProvider.getApplicationContext<Context>()

    @Test fun optInIsOffByDefaultAndSurvivesPreferenceReload() {
        context.getSharedPreferences("epimediahub_boot_settings", Context.MODE_PRIVATE).edit().clear().commit()
        assertFalse(V159BootAutostart.enabled(context))
        V159BootAutostart.setEnabled(context, true)
        assertTrue(V159BootAutostart.enabled(context))
        V159BootAutostart.setEnabled(context, false)
        assertFalse(V159BootAutostart.enabled(context))
    }

    @Test fun receiverIgnoresOtherBroadcastActions() {
        V159BootAutostart.setEnabled(context, true)
        V159BootReceiver().onReceive(context, Intent(Intent.ACTION_SCREEN_ON))
        assertTrue(V159BootAutostart.enabled(context))
        V159BootAutostart.setEnabled(context, false)
    }
}
