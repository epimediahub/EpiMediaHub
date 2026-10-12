package de.epimediahub.app.ui

import android.content.Context
import android.os.Process
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import de.epimediahub.app.data.SetupCodeProvisioning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

/**
 * Explicitly opt-in, category-only crash metrics.
 * Never stores stack traces, URLs, channel names, location, IP or credentials.
 * Defers network I/O to a future healthy app start and delegates the crash to
 * Android's original uncaught exception handler without delaying it.
 */
internal object V164Diagnostics {
    private const val PREFS = "v164_privacy_diagnostics"
    private const val OPT_IN = "explicit_opt_in"
    private const val PENDING_CRASH = "pending_crash"

    fun enabled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getBoolean(OPT_IN, false)

    fun setEnabled(context: Context, consent: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putBoolean(OPT_IN, consent)
            .apply()
        if (!consent) context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .remove(PENDING_CRASH).apply()
    }

    fun installCrashMarker(context: Context) {
        val app = context.applicationContext
        val old = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            try {
                if (enabled(app)) {
                    app.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                        .putBoolean(PENDING_CRASH, true).commit()
                }
            } catch (_: Throwable) { /* Never interfere with default crash handling. */ }
            if (old != null) old.uncaughtException(thread, error)
            else Process.killProcess(Process.myPid())
        }
    }

    suspend fun uploadPending(context: Context) = withContext(Dispatchers.IO) {
        val app = context.applicationContext
        val prefs = app.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (!enabled(app) || !prefs.getBoolean(PENDING_CRASH, false)) return@withContext
        val token = SetupCodeProvisioning.sessionToken(app) ?: return@withContext
        var conn: HttpURLConnection? = null
        try {
            conn = (URL("https://api.epimediahub.com/v1/device/error-report").openConnection()
                    as HttpURLConnection).apply {
                requestMethod = "POST"
                doOutput = true
                connectTimeout = 5_000
                readTimeout = 5_000
                setRequestProperty("Authorization", "Bearer $token")
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
            }
            val body = JSONObject()
                .put("consent", true)
                .put("component", "OTHER")
                .put("code", "CRASH")
                .put("app_version", "1.0.64")
                .toString()
            conn.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode in 200..299) prefs.edit().remove(PENDING_CRASH).apply()
        } catch (_: Exception) { /* No retries on the UI thread and no error text logged. */ }
        finally { conn?.disconnect() }
    }
}

@Composable
internal fun V164DiagnosticsCard(accent: Color) {
    val context = LocalContext.current
    var enabled by remember(context) { mutableStateOf(V164Diagnostics.enabled(context)) }
    FocusCard(
        title = "Anonyme Fehlerberichte",
        subtitle = (if (enabled) "Ein" else "Aus") +
            " · Nur auf Wunsch: Absturzhäufigkeit und Fehlerkategorie. Keine Inhalte oder Zugangsdaten.",
        accent = accent,
        onClick = {
            enabled = !enabled
            V164Diagnostics.setEnabled(context, enabled)
        },
        modifier = Modifier.fillMaxWidth().testTag("diagnostics-opt-in-toggle")
    )
}
