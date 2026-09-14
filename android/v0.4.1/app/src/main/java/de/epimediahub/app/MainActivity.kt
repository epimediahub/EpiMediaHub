package de.epimediahub.app

import android.app.UiModeManager
import android.content.Context
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val tv = isAndroidTv(this)
        if (!tv) {
            requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE
        }
        enableEdgeToEdge()
        setContent { EpiMediaHubApp(isTv = tv) }
    }
}

fun isAndroidTv(context: Context): Boolean {
    val ui = context.getSystemService(Context.UI_MODE_SERVICE) as UiModeManager
    return ui.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION
}
