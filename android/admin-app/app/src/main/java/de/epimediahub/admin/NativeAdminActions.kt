package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.UUID
import kotlin.concurrent.thread

/** Admin-only, explicitly confirmed annual app license and 7-day VPN trial grants. */
internal object NativeAdminActions {
    private const val BASE = "https://admin.epimediahub.com"
    private val main = Handler(Looper.getMainLooper())

    data class Outcome(val applied: Boolean, val message: String)

    fun grant(deviceRowId: String, action: String, done: (Outcome) -> Unit) {
        if (action !in listOf("grant-year", "vpn-trial7") ||
            !Regex("[1-9][0-9]{0,17}").matches(deviceRowId)) {
            main.post { done(Outcome(false, "Ungültiges Gerät oder ungültige Aktion.")) }
            return
        }
        thread(name = "epi-native-admin-grant") {
            val result = try {
                val cookies = CookieManager.getInstance()
                val existing = cookies.getCookie(BASE) ?: ""
                if (existing.isBlank()) {
                    Outcome(false, "Admin-Anmeldung erforderlich.")
                } else {
                    val bootstrap = (URL("$BASE/admin/mobile/bootstrap")
                        .openConnection() as HttpURLConnection).apply {
                        requestMethod = "GET"
                        instanceFollowRedirects = false
                        connectTimeout = 8000
                        readTimeout = 8000
                        setRequestProperty("Cookie", existing)
                        setRequestProperty("Accept", "application/json")
                    }
                    val csrf = try {
                        if (bootstrap.responseCode != 200) ""
                        else {
                            val result = JSONObject(bootstrap.inputStream.bufferedReader().use {
                                it.readText().take(16_384)
                            }).optString("csrf", "")
                            for ((name, values) in bootstrap.headerFields) {
                                if (name?.equals("Set-Cookie",ignoreCase = true) == true &&
                                    values != null) {
                                    for (value in values) {
                                        if (value.isNotBlank() && value.length < 8192) {
                                            cookies.setCookie(BASE, value)
                                        }
                                    }
                                }
                            }
                            cookies.flush()
                            result
                        }
                    } finally {
                        bootstrap.disconnect()
                    }
                    if (csrf.length < 32) Outcome(false, "Admin-Sitzung abgelaufen.")
                    else {
                        val path = "/admin/mobile/management/devices/$deviceRowId/$action"
                        val conn = (URL(BASE + path)
                            .openConnection() as HttpURLConnection).apply {
                            requestMethod = "POST"
                            instanceFollowRedirects = false
                            doOutput = true
                            connectTimeout = 8000
                            readTimeout = 15000
                            setRequestProperty("Content-Type", "application/json")
                            setRequestProperty("Accept", "application/json")
                            setRequestProperty("Cookie",
                                cookies.getCookie(BASE) ?: existing)
                            setRequestProperty("X-Dashboard-CSRF", csrf)
                            setRequestProperty("Cache-Control", "no-store")
                        }
                        try {
                            // Each confirmation receives its own UUID. The business
                            // backend prevents repeated entitlements on the same device.
                            val payload = JSONObject()
                                .put("confirm", true)
                                .put("request_id", UUID.randomUUID().toString())
                                .toString()
                            conn.outputStream.use {
                                it.write(payload.toByteArray(Charsets.UTF_8))
                            }
                            val status = conn.responseCode
                            when (status) {
                                200 -> {
                                    val body = JSONObject(
                                        conn.inputStream.bufferedReader().use {
                                            it.readText().take(8192)
                                        })
                                    if (body.optBoolean("applied", false))
                                        Outcome(true, if (action == "grant-year")
                                            "1-Jahres-App-Lizenz erfolgreich aktiviert."
                                            else "7-Tage-VPN-Test erfolgreich freigegeben.")
                                    else Outcome(false, "Freigabe nicht bestätigt.")
                                }
                                409 -> Outcome(false,
                                    "Aktion nicht durchgeführt: bereits aktiv oder nicht berechtigt.")
                                401, 403 -> Outcome(false, "Admin-Sitzung oder Freigabe ungültig.")
                                400 -> Outcome(false, "Ungültige Anfrage.")
                                else -> Outcome(false, "Aktion nicht verfügbar (HTTP $status).")
                            }
                        } finally {
                            conn.disconnect()
                        }
                    }
                }
            } catch (_: Exception) {
                // A timeout cannot prove whether the server applied a write.
                Outcome(false, "Ergebnis nicht bestätigt. Bitte Geräte-Status prüfen, nicht sofort wiederholen.")
            }
            main.post { done(result) }
        }
    }
}
