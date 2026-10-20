package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import android.webkit.CookieManager
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import kotlin.concurrent.thread

/**
 * Native Android login using the EXISTING administrator login protocol.
 *
 * No WebView, browser page, password storage or second administrator credential.
 * The existing Flask session stays the sole authorization authority.
 * No redirects are followed and the resulting session must pass bootstrap.
 */
internal object NativeAdminAuth {
    private const val BASE = "https://admin.epimediahub.com"
    private val main = Handler(Looper.getMainLooper())

    private fun cookie(): String =
        CookieManager.getInstance().getCookie(BASE) ?: ""

    private fun acceptSessionCookies(connection: HttpURLConnection) {
        for ((name, values) in connection.headerFields) {
            if (name?.equals("Set-Cookie", ignoreCase = true) != true || values == null) continue
            for (value in values) {
                if (value.isNotBlank() && value.length < 8192) {
                    CookieManager.getInstance().setCookie(BASE, value)
                }
            }
        }
        CookieManager.getInstance().flush()
    }

    private fun bootstrap(): Boolean {
        val currentCookie = cookie()
        if (currentCookie.isBlank()) return false
        val connection = (URL("$BASE/admin/mobile/bootstrap")
            .openConnection() as HttpURLConnection).apply {
            requestMethod = "GET"
            instanceFollowRedirects = false
            connectTimeout = 8000
            readTimeout = 8000
            setRequestProperty("Cookie", currentCookie)
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-store")
        }
        return try {
            val ok = connection.responseCode == 200 &&
                connection.contentType?.substringBefore(";") == "application/json"
            if (!ok) false
            else {
                val response = connection.inputStream.bufferedReader().use {
                    it.readText().take(16_384)
                }
                val value = JSONObject(response)
                val csrf = value.optString("csrf", "")
                if (csrf.length < 32) false
                else {
                    acceptSessionCookies(connection)
                    cookie().isNotBlank()
                }
            }
        } finally {
            connection.disconnect()
        }
    }

    fun check(done: (Boolean) -> Unit) {
        thread(name = "epi-native-session-check") {
            val active = try { bootstrap() } catch (_: Exception) { false }
            main.post { done(active) }
        }
    }

    fun login(password: String, done: (Boolean, String) -> Unit) {
        if (password.isBlank() || password.length > 1024) {
            main.post { done(false, "Bitte Administratorpasswort eingeben.") }
            return
        }
        thread(name = "epi-native-admin-login") {
            val (loggedIn, message) = try {
                // Legacy /admin/login expects an ordinary form POST. Android never
                // displays or parses its HTML: the session is verified separately.
                val connection = (URL("$BASE/admin/login")
                    .openConnection() as HttpURLConnection).apply {
                    requestMethod = "POST"
                    instanceFollowRedirects = false
                    doOutput = true
                    connectTimeout = 8000
                    readTimeout = 8000
                    setRequestProperty("Content-Type",
                        "application/x-www-form-urlencoded; charset=UTF-8")
                    setRequestProperty("Accept", "text/html")
                    setRequestProperty("Cache-Control", "no-store")
                    val existing = cookie()
                    if (existing.isNotBlank()) setRequestProperty("Cookie", existing)
                }
                try {
                    val form = "password=" + URLEncoder.encode(password, "UTF-8")
                    connection.outputStream.use { stream ->
                        stream.write(form.toByteArray(Charsets.UTF_8))
                    }
                    val code = connection.responseCode
                    if (code == 429) {
                        false to "Zu viele Anmeldeversuche. Bitte später erneut versuchen."
                    } else if (code !in 200..399) {
                        false to "Anmeldung zurzeit nicht möglich."
                    } else {
                        acceptSessionCookies(connection)
                        if (bootstrap()) true to ""
                        else false to "Anmeldung nicht erfolgreich. Zugang bitte prüfen."
                    }
                } finally {
                    connection.disconnect()
                }
            } catch (_: Exception) {
                false to "Keine sichere Verbindung zum Admin-Server."
            }
            main.post { done(loggedIn, message) }
        }
    }

    fun logout(done: () -> Unit) {
        thread(name = "epi-native-admin-logout") {
            try {
                val activeCookie = cookie()
                if (activeCookie.isNotBlank()) {
                    // Existing logout route uses the same authenticated session.
                    val connection = (URL("$BASE/admin/logout")
                        .openConnection() as HttpURLConnection).apply {
                        requestMethod = "POST"
                        instanceFollowRedirects = false
                        connectTimeout = 8000
                        readTimeout = 8000
                        setRequestProperty("Cookie", activeCookie)
                    }
                    try {
                        connection.responseCode
                    } finally {
                        connection.disconnect()
                    }
                }
            } catch (_: Exception) {
                // Local session is cleared even when the network is unavailable.
            } finally {
                CookieManager.getInstance().removeAllCookies {
                    CookieManager.getInstance().flush()
                    main.post { done() }
                }
            }
        }
    }
}
