package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.util.UUID
import kotlin.concurrent.thread

/**
 * Native controls backed by existing dashboard business handlers.
 * Form data never enters a WebView. The dedicated server bridge requires
 * administrator session, CSRF, explicit confirmation and replay protection.
 */
internal object NativeLegacyActions {
    private const val BASE = "https://admin.epimediahub.com"
    private val main = Handler(Looper.getMainLooper())
    private val expected = mapOf(
        "create-customer" to setOf("name"),
        "create-reseller" to setOf("name", "username", "password",
            "branding_name", "customer_limit", "device_limit"),
        "rename-device" to setOf("name"),
        "sync-device" to emptySet(),
        "move-device" to setOf("customer_id"),
        "assign-reseller" to setOf("reseller_id"),
        "delete-playlist" to emptySet(),
        "add-playlist" to setOf("playlist_name","playlist_type","playlist_url",
            "xtream_server","xtream_username","xtream_password","xtream_output"),
        "edit-playlist" to setOf("playlist_name","playlist_type","playlist_url",
            "xtream_server","xtream_username","xtream_password","xtream_output"),
        "delete-customer" to emptySet(),
        "delete-reseller" to emptySet(),
        "delete-device" to emptySet()
    )
    data class Outcome(val applied: Boolean, val message: String, val newId: String = "")

    private fun csrf(jar: CookieManager, existing: String): String {
        val conn = (URL("$BASE/admin/mobile/bootstrap")
            .openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            instanceFollowRedirects = false
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Cookie", existing)
            setRequestProperty("Accept", "application/json")
        }
        return try {
            if (conn.responseCode != 200) ""
            else {
                val token = JSONObject(conn.inputStream.bufferedReader().use {
                    it.readText().take(16384)
                }).optString("csrf", "")
                for ((header, values) in conn.headerFields) {
                    if (header?.equals("Set-Cookie", ignoreCase = true) == true
                            && values != null) {
                        for (value in values) {
                            if (value.isNotBlank() && value.length < 8192) {
                                jar.setCookie(BASE, value)
                            }
                        }
                    }
                }
                jar.flush()
                token
            }
        } finally {
            conn.disconnect()
        }
    }

    /** Lookup the exact phrase from the trusted existing server handler.
     *  A delete is never offered when the backend safety gate is disabled.
     */
    fun confirmDeletion(action: String, id: String, done: (String?, String) -> Unit) {
        if (action !in setOf("delete-customer","delete-reseller","delete-device") ||
            !Regex("[1-9][0-9]{0,17}").matches(id)) {
            main.post { done(null, "Ungültige Aktion.") }
            return
        }
        thread(name = "epi-admin-typed-delete") {
            val result = try {
                val cookie = CookieManager.getInstance().getCookie(BASE) ?: ""
                if (cookie.isBlank()) throw IllegalStateException("Admin-Sitzung fehlt.")
                val conn = (URL(
                    "$BASE/admin/mobile/management/delete-confirm/$action/$id"
                ).openConnection() as HttpURLConnection).apply {
                    requestMethod = "GET"
                    instanceFollowRedirects = false
                    connectTimeout = 8000
                    readTimeout = 10000
                    setRequestProperty("Cookie", cookie)
                    setRequestProperty("Accept", "application/json")
                    setRequestProperty("Cache-Control", "no-store")
                }
                try {
                    if (conn.responseCode != 200)
                        throw IllegalStateException("Löschen serverseitig noch nicht freigegeben.")
                    val data = JSONObject(conn.inputStream.bufferedReader().use {
                        it.readText().take(1000)
                    })
                    val phrase = data.optString("required_confirmation", "")
                    if (phrase.length !in 2..100)
                        throw IllegalStateException("Bestätigung nicht verfügbar.")
                    phrase to ""
                } finally {
                    conn.disconnect()
                }
            } catch (e: Exception) {
                null to (e.message?.take(100) ?: "Löschfunktion nicht verfügbar.")
            }
            main.post { done(result.first, result.second) }
        }
    }

    fun execute(action: String, entityId: String, fields: Map<String, String>,
                typedConfirmation: String? = null, done: (Outcome) -> Unit) {
        val idValid = if (action.startsWith("create-")) entityId == "0"
            else Regex("[1-9][0-9]{0,17}").matches(entityId)
        val deleting = action in setOf("delete-customer","delete-reseller","delete-device")
        if (!idValid || fields.keys != expected[action]
                || (deleting && (typedConfirmation == null || typedConfirmation.isBlank()
                    || typedConfirmation.length > 100))
                || fields.values.any { it.length > 1600 || it.contains('\u0000') }) {
            main.post { done(Outcome(false, "Ungültige Eingaben für diese Aktion.")) }
            return
        }
        thread(name = "epi-admin-native-business-action") {
            val result = try {
                val jar = CookieManager.getInstance()
                val existing = jar.getCookie(BASE) ?: ""
                val token = if (existing.isBlank()) "" else csrf(jar, existing)
                if (token.length < 32) {
                    Outcome(false, "Bitte erneut als Administrator anmelden.")
                } else {
                    val path = "/admin/mobile/management/actions/$action/$entityId"
                    val values = fields + mapOf(
                        "confirm" to (if (deleting) typedConfirmation!! else "true"),
                        "request_id" to UUID.randomUUID().toString()
                    )
                    val encoded = values.entries.joinToString("&") { (k, v) ->
                        URLEncoder.encode(k, "UTF-8") + "=" +
                            URLEncoder.encode(v, "UTF-8")
                    }
                    val conn = (URL(BASE + path)
                        .openConnection() as HttpURLConnection).apply {
                        requestMethod = "POST"
                        instanceFollowRedirects = false
                        doOutput = true
                        connectTimeout = 8000
                        readTimeout = 15000
                        setRequestProperty("Cookie", jar.getCookie(BASE) ?: existing)
                        setRequestProperty("X-Dashboard-CSRF", token)
                        setRequestProperty("Content-Type",
                            "application/x-www-form-urlencoded; charset=utf-8")
                        setRequestProperty("Accept", "application/json")
                        setRequestProperty("Cache-Control", "no-store")
                    }
                    try {
                        conn.outputStream.use {
                            it.write(encoded.toByteArray(Charsets.UTF_8))
                        }
                        when (conn.responseCode) {
                            200 -> {
                                val body = JSONObject(conn.inputStream.bufferedReader().use {
                                    it.readText().take(8192)
                                })
                                if (body.optBoolean("applied", false))
                                    Outcome(true, "Aktion bestätigt und gespeichert.",
                                        body.optString("id", ""))
                                else Outcome(false, "Aktion nicht bestätigt.")
                            }
                            400 -> Outcome(false,
                                "Eingabe ungültig oder Ziel wurde inzwischen geändert.")
                            401, 403 -> Outcome(false,
                                "Admin-Sitzung abgelaufen oder Berechtigung fehlt.")
                            404, 503 -> Outcome(false,
                                "Die native Verwaltungsfunktion ist noch nicht freigeschaltet.")
                            409 -> Outcome(false,
                                "Ergebnis unklar oder Aktion bereits ausgeführt. "
                                + "Bitte Status prüfen, nicht sofort wiederholen.")
                            else -> Outcome(false,
                                "Aktion nicht bestätigt (HTTP ${conn.responseCode}).")
                        }
                    } finally {
                        conn.disconnect()
                    }
                }
            } catch (_: Exception) {
                Outcome(false,
                    "Ergebnis nicht bestätigt. Bitte Liste aktualisieren, "
                    + "nicht sofort erneut ausführen.")
            }
            main.post { done(result) }
        }
    }
}
