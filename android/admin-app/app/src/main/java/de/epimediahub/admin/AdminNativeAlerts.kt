package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/** Native, admin-session-only incident feed and CSRF-protected acknowledgement. */
object AdminNativeAlerts {
    data class Incident(
        val key: String,
        val kind: String,
        val severity: String,
        val message: String,
        val state: String,
        val lastSeenEpoch: Long
    )
    private const val BASE = "https://admin.epimediahub.com"
    private val main = Handler(Looper.getMainLooper())

    private fun get(path: String, cookie: String): Pair<Int, String> {
        val connection = URL(BASE + path).openConnection() as HttpURLConnection
        connection.instanceFollowRedirects = false
        connection.connectTimeout = 9000
        connection.readTimeout = 9000
        connection.setRequestProperty("Cookie", cookie)
        connection.setRequestProperty("Accept", "application/json")
        connection.setRequestProperty("Cache-Control", "no-store")
        return try {
            val status = connection.responseCode
            val body = if (status == 200) {
                connection.inputStream.bufferedReader().use { it.readText().take(65536) }
            } else ""
            status to body
        } finally { connection.disconnect() }
    }

    fun load(cookie: String, done: (List<Incident>?, String) -> Unit) {
        if (cookie.isBlank()) {
            main.post { done(null, "Bitte im Dashboard anmelden.") }
            return
        }
        thread(name = "epi-admin-alerts") {
            var items: List<Incident>? = null
            val message = try {
                val (status, body) = get("/admin/mobile/alerts.json", cookie)
                if (status != 200) {
                    if (status == 401) "Admin-Anmeldung erforderlich."
                    else "Meldungen derzeit nicht erreichbar (HTTP $status)."
                } else {
                    val rows = JSONObject(body).getJSONArray("incidents")
                    require(rows.length() <= 120)
                    items = (0 until rows.length()).map { index ->
                        val row = rows.getJSONObject(index)
                        val key = row.getString("alert_key")
                        require(key.length in 1..200)
                        val severity = row.getString("severity")
                        require(severity in listOf("critical", "warning", "info"))
                        val state = row.getString("state")
                        require(state in listOf("open", "acknowledged"))
                        Incident(key, row.getString("kind").take(60), severity,
                            row.getString("message").take(300), state,
                            row.getLong("last_seen_epoch"))
                    }
                    ""
                }
            } catch (_: Exception) {
                "Meldungen konnten nicht sicher geladen werden."
            }
            val value = items
            main.post { done(value, message) }
        }
    }

    fun acknowledge(cookie: String, key: String, done: (Boolean, String) -> Unit) {
        if (cookie.isBlank() || key.isBlank() || key.length > 200) {
            main.post { done(false, "Admin-Anmeldung erforderlich.") }
            return
        }
        thread(name = "epi-admin-ack") {
            var success = false
            val result = try {
                val (boot, body) = get("/admin/mobile/bootstrap", cookie)
                if (boot != 200) {
                    "Admin-Anmeldung erforderlich."
                } else {
                    val csrf = JSONObject(body).getString("csrf")
                    val connection =
                        URL(BASE + "/admin/mobile/alerts/ack").openConnection() as HttpURLConnection
                    connection.instanceFollowRedirects = false
                    connection.connectTimeout = 9000
                    connection.readTimeout = 9000
                    connection.requestMethod = "POST"
                    connection.doOutput = true
                    connection.setRequestProperty("Cookie", cookie)
                    connection.setRequestProperty("Content-Type", "application/json")
                    connection.setRequestProperty("Accept", "application/json")
                    connection.setRequestProperty("X-Dashboard-CSRF", csrf)
                    try {
                        val payload = JSONObject().put("alert_key", key).toString()
                        connection.outputStream.use {
                            it.write(payload.toByteArray(Charsets.UTF_8))
                        }
                        success = connection.responseCode == 200
                        if (success) "Meldung bestätigt." else "Bestätigung fehlgeschlagen."
                    } finally { connection.disconnect() }
                }
            } catch (_: Exception) { "Bestätigung derzeit nicht möglich." }
            main.post { done(success, result) }
        }
    }
}
