package de.epimediahub.admin

import android.content.Context
import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import kotlin.concurrent.thread

/** Register only on explicit admin request, with the current HTTPS dashboard session. */
object AdminPushRegistration {
    private const val BASE = "https://admin.epimediahub.com"
    private fun call(path: String, cookie: String, data: JSONObject? = null, csrf: String = ""): Pair<Int, String> {
        val connection = URL(BASE + path).openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = false
        connection.connectTimeout = 8000
        connection.readTimeout = 8000
        connection.setRequestProperty("Cookie", cookie)
        connection.setRequestProperty("Accept", "application/json")
        if (data != null) {
            connection.requestMethod = "POST"
            connection.doOutput = true
            connection.setRequestProperty("Content-Type", "application/json")
            connection.setRequestProperty("X-Dashboard-CSRF", csrf)
            connection.outputStream.use { it.write(data.toString().toByteArray(Charsets.UTF_8)) }
        }
        return try {
            val status = connection.responseCode
            val body = if (status in 200..299) {
                connection.inputStream.bufferedReader().use { it.readText().take(4096) }
            } else ""
            status to body
        } finally { connection.disconnect() }
    }

    fun register(context: Context, token: String, cookie: String, onDone: (String) -> Unit) {
        val application = context.applicationContext
        val handler = Handler(Looper.getMainLooper())
        thread(name = "admin-push-register") {
            val outcome = try {
                val (status, body) = call("/admin/mobile/bootstrap", cookie)
                if (status != 200) {
                    "Admin-App: Bitte im Dashboard anmelden (oder Server-Modul noch nicht installiert)."
                } else {
                    val csrf = JSONObject(body).getString("csrf")
                    val prefs = application.getSharedPreferences("admin-push", Context.MODE_PRIVATE)
                    val installId = prefs.getString("installation_id", null)
                        ?: UUID.randomUUID().toString().also {
                            prefs.edit().putString("installation_id", it).apply()
                        }
                    val data = JSONObject()
                        .put("installation_id", installId)
                        .put("fcm_token", token)
                        .put("platform", "android-admin")
                    val (registerStatus, _) = call("/admin/mobile/register", cookie, data, csrf)
                    if (registerStatus == 201 || registerStatus == 200) {
                        prefs.edit().putBoolean("registered", true).apply()
                        "Push-Gerät registriert. Alarme erscheinen, sobald die Serverzustellung aktiv ist."
                    } else {
                        "Push konnte nicht registriert werden (HTTP $registerStatus)."
                    }
                }
            } catch (_: Exception) {
                "Push konnte den Admin-Server nicht sicher erreichen."
            }
            handler.post { onDone(outcome) }
        }
    }
}
