package de.epimediahub.app

import android.app.Activity
import android.app.UiModeManager
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.res.Configuration
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.result.contract.ActivityResultContracts

class MainActivity : ComponentActivity() {
    private val vpnPermissionLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        RemoteTailscaleManager.onVpnPermissionResult(result.resultCode == Activity.RESULT_OK)
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val tv = isAndroidTv(this)
        if (!tv) requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE

        RemoteTailscaleManager.attach(this) { permissionIntent: Intent ->
            vpnPermissionLauncher.launch(permissionIntent)
        }

        enableEdgeToEdge()
        setContent { EpiMediaHubApp(isTv = tv) }
    }

    override fun onResume() {
        super.onResume()
        RemoteTailscaleManager.onHostResumed()
    }

    override fun onDestroy() {
        RemoteTailscaleManager.detach(this)
        super.onDestroy()
    }
}

fun isAndroidTv(context: Context): Boolean {
    val ui = context.getSystemService(Context.UI_MODE_SERVICE) as UiModeManager
    return ui.currentModeType == Configuration.UI_MODE_TYPE_TELEVISION
}
