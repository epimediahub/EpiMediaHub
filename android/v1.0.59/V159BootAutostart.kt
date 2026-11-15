package de.epimediahub.app.ui

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Switch
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.unit.dp

/** Opt-in only. Android/Fire OS may deny background activity launches after BOOT_COMPLETED. */
internal object V159BootAutostart {
    private const val PREFERENCES = "epimediahub_boot_settings"
    private const val KEY = "launch_on_boot"

    fun enabled(context: Context): Boolean =
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).getBoolean(KEY, false)

    fun setEnabled(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFERENCES, Context.MODE_PRIVATE).edit()
            .putBoolean(KEY, enabled).apply()
    }
}

class V159BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Intent.ACTION_BOOT_COMPLETED || !V159BootAutostart.enabled(context)) return
        // Single best-effort launch, without starting a background service or bypassing Android policy.
        val launch = context.packageManager.getLaunchIntentForPackage(context.packageName) ?: return
        launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        runCatching { context.startActivity(launch) }
    }
}

@Composable
internal fun V159BootSettingsToggle() {
    val context = LocalContext.current
    var launchAtBoot by remember(context) { mutableStateOf(V159BootAutostart.enabled(context)) }
    Row(Modifier.fillMaxWidth().padding(vertical = 10.dp), horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Column(Modifier.weight(1f)) {
            Text("App beim Gerätestart automatisch öffnen")
            Text("Nur nach einem Neustart. Auf manchen Android- und Fire-TV-Geräten verhindert das System den automatischen Start.")
        }
        Switch(
            checked = launchAtBoot,
            onCheckedChange = {
                V159BootAutostart.setEnabled(context, it)
                launchAtBoot = it
            },
            modifier = Modifier.testTag("boot-autostart-toggle")
        )
    }
}
