package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import kotlin.concurrent.thread

/**
 * Native metadata-only rename for customer and reseller display names.
 * The backend owns CSRF, optimistic concurrency, audit and transaction.
 */
internal object NativeAdminEdits {
    data class Outcome(val success: Boolean, val message: String)
    private const val BASE = "https://admin.epimediahub.com"
    private val main = Handler(Looper.getMainLooper())
    private val pathKind = setOf("customers", "resellers")

    private fun bootstrap(cookie: String): String {
        val conn = (URL("$BASE/admin/mobile/bootstrap").openConnection()
            as HttpURLConnection).apply {
            requestMethod = "GET"
            instanceFollowRedirects = false
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Cookie", cookie)
            setRequestProperty("Accept", "application/json")
        }
        return try {
            if (conn.responseCode != 200) ""
            else {
                val csrf = JSONObject(conn.inputStream.bufferedReader().use {
                    it.readText().take(16384)
                }).optString("csrf","")
                val cookieJar = CookieManager.getInstance()
                for ((header, values) in conn.headerFields) {
                    if (header?.equals("Set-Cookie", ignoreCase = true) == true
                        && values != null) {
                        for (value in values) {
                            if (value.isNotBlank() && value.length < 8192) {
                                cookieJar.setCookie(BASE, value)
                            }
                        }
                    }
                }
                cookieJar.flush()
                csrf
            }
        } finally {
            conn.disconnect()
        }
    }

    fun rename(kind: String, id: String, oldName: String,
               newName: String, callback: (Outcome) -> Unit) {
        val requestedName = newName.trim()
        if (kind !in pathKind || !Regex("[1-9][0-9]{0,17}").matches(id) ||
            requestedName.isBlank() || requestedName.length > 140 ||
            requestedName == oldName || requestedName.any { it.code < 32 }) {
            main.post { callback(Outcome(false, "Bitte einen neuen gültigen Namen eingeben.")) }
            return
        }
        thread(name="epi-admin-native-rename") {
            val outcome = try {
                val jar=CookieManager.getInstance()
                val cookie=jar.getCookie(BASE) ?: ""
                val csrf=if (cookie.isBlank()) "" else bootstrap(cookie)
                if (csrf.length < 32) {
                    Outcome(false,"Bitte erneut als Administrator anmelden.")
                } else {
                    val path="/admin/mobile/management/$kind/$id/rename"
                    val connection=(URL(BASE+path).openConnection()
                        as HttpURLConnection).apply {
                        requestMethod="POST"
                        instanceFollowRedirects=false
                        doOutput=true
                        connectTimeout=8000
                        readTimeout=12000
                        setRequestProperty("Accept","application/json")
                        setRequestProperty("Content-Type","application/json")
                        setRequestProperty("Cookie",jar.getCookie(BASE) ?: cookie)
                        setRequestProperty("X-Dashboard-CSRF",csrf)
                        setRequestProperty("Cache-Control","no-store")
                    }
                    try {
                        val payload=JSONObject()
                            .put("name",requestedName)
                            .put("expected_name",oldName)
                            .put("request_id",UUID.randomUUID().toString())
                            .toString()
                        connection.outputStream.use {
                            it.write(payload.toByteArray(Charsets.UTF_8))
                        }
                        when (connection.responseCode) {
                            200 -> {
                                val body=JSONObject(connection.inputStream.bufferedReader().use {
                                    it.readText().take(8192)
                                })
                                if (body.optBoolean("applied",false))
                                    Outcome(true,"Name erfolgreich geändert.")
                                else Outcome(false,"Änderung wurde nicht erneut ausgeführt.")
                            }
                            409 -> Outcome(false,
                                "Der Name hat sich inzwischen geändert. Bitte Liste aktualisieren.")
                            401,403 -> Outcome(false,"Admin-Sitzung oder Freigabe ungültig.")
                            400 -> Outcome(false,"Ungültiger Name oder Antrag.")
                            else -> Outcome(false,"Änderung derzeit nicht möglich.")
                        }
                    } finally {
                        connection.disconnect()
                    }
                }
            } catch (_: Exception) {
                Outcome(false,"Ergebnis nicht bestätigt. Bitte zuerst Liste neu laden.")
            }
            main.post { callback(outcome) }
        }
    }
}
