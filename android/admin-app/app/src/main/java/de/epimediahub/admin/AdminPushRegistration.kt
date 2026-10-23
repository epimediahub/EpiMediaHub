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

    fun unregister(context: Context, cookie: String, onDone: (String) -> Unit) {
        val application=context.applicationContext
        val handler=Handler(Looper.getMainLooper())
        thread(name="admin-push-unregister") {
            val prefs=application.getSharedPreferences("admin-push",Context.MODE_PRIVATE)
            val installId=prefs.getString("installation_id",null)
            val outcome=if (installId==null) {
                "Dieses Gerät ist nicht als Push-Gerät registriert."
            } else {
                try {
                    val (status,body)=call("/admin/mobile/bootstrap",cookie)
                    if (status!=200) "Bitte im Admin-Dashboard anmelden."
                    else {
                        val csrf=JSONObject(body).getString("csrf")
                        val data=JSONObject().put("installation_id",installId)
                        val (code,_)=call("/admin/mobile/unregister",cookie,data,csrf)
                        if (code==200) {
                            prefs.edit().putBoolean("registered",false).apply()
                            "Push-Gerät wurde vom Admin-Server abgemeldet."
                        } else "Abmeldung fehlgeschlagen (HTTP $code)."
                    }
                } catch (_:Exception) { "Abmeldung konnte Server nicht sicher erreichen." }
            }
            handler.post { onDone(outcome) }
        }
    }

    fun testPush(context: Context, cookie: String, onDone: (String) -> Unit) {
        val application=context.applicationContext
        val handler=Handler(Looper.getMainLooper())
        thread(name="admin-push-test") {
            val prefs=application.getSharedPreferences("admin-push",Context.MODE_PRIVATE)
            val installation=prefs.getString("installation_id",null)
            val message=if (cookie.isBlank() || installation.isNullOrBlank() ||
                !prefs.getBoolean("registered",false)) {
                "Gerät zuerst für Push registrieren."
            } else try {
                val (bootstrapCode,body)=call("/admin/mobile/bootstrap",cookie)
                if (bootstrapCode!=200) {
                    "Admin-Sitzung abgelaufen. Bitte neu anmelden."
                } else {
                    val metadata=JSONObject(body)
                    if (!metadata.optBoolean("push_sender_configured",false)) {
                        "Der Firebase-Versanddienst auf dem Server ist nicht eingerichtet."
                    } else {
                        val csrf=metadata.getString("csrf")
                        val (status,_)=call("/admin/mobile/test-push",cookie,
                            JSONObject().put("installation_id",installation),csrf)
                        when(status) {
                            200 -> "Firebase hat die Testnachricht angenommen. Bitte Android-Benachrichtigungen prüfen."
                            429 -> "Test bereits angefordert. In zwei Minuten erneut versuchen."
                            404 -> "Gerät nicht auf dem Server registriert. Erneut verbinden."
                            401,403 -> "Admin-Sitzung ungültig. Erneut anmelden."
                            503 -> "Firebase-Zustellung am Server fehlgeschlagen. Server-Konfiguration prüfen."
                            else -> "Test-Push fehlgeschlagen (HTTP $status)."
                        }
                    }
                }
            } catch (_:Exception) {
                "Push-Test konnte den Admin-Server nicht erreichen."
            }
            handler.post { onDone(message) }
        }
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
                    val bootstrap = JSONObject(body)
                    val csrf = bootstrap.getString("csrf")
                    val senderConfigured = bootstrap.optBoolean("push_sender_configured", false)
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
                        prefs.edit().putBoolean("registered", true)
                            .putBoolean("opted_in", true).apply()
                        if (senderConfigured)
                            "Gerät registriert. Mit »Test-Push senden« die Zustellung prüfen."
                        else
                            "Gerät registriert, aber Firebase-Versand ist auf dem Server noch nicht eingerichtet."
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
