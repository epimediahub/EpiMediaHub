package de.epimediahub.admin

import android.os.Handler
import android.os.Looper
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/** Authenticated read-only overview of exactly two dedicated EpiScene sources. */
object AdminNativeStatus {
    data class Lane(
        val id: Int,
        val label: String,
        val enabled: Boolean,
        val queued: Int,
        val running: Int,
        val completed: Int,
        val failed: Int,
        val lastCompletionEpoch: Long?
    )
    data class Snapshot(val sampledAtEpoch: Long, val lanes: List<Lane>)
    private const val URL_STATUS = "https://admin.epimediahub.com/admin/mobile/episcene/status"

    fun load(cookie: String, onDone: (Snapshot?, String) -> Unit) {
        val main = Handler(Looper.getMainLooper())
        if (cookie.isBlank()) {
            main.post { onDone(null, "Bitte zuerst im Dashboard anmelden.") }
            return
        }
        thread(name = "epi-admin-status") {
            var snapshot: Snapshot? = null
            val message = try {
                val connection = URL(URL_STATUS).openConnection() as HttpURLConnection
                try {
                    connection.instanceFollowRedirects = false
                    connection.connectTimeout = 9000
                    connection.readTimeout = 9000
                    connection.setRequestProperty("Cookie", cookie)
                    connection.setRequestProperty("Accept", "application/json")
                    connection.setRequestProperty("Cache-Control", "no-store")
                    val code = connection.responseCode
                    if (code != 200) {
                        if (code == 401 || code == 403) {
                            "Admin-Anmeldung erforderlich."
                        } else {
                            "Live-Status derzeit nicht verfügbar (HTTP $code)."
                        }
                    } else {
                        val payload = connection.inputStream.bufferedReader().use {
                            it.readText().take(8192)
                        }
                        val root = JSONObject(payload)
                        require(root.getString("scope") == "independent_analysis_sources_only")
                        val lanesJson = root.getJSONArray("lanes")
                        require(lanesJson.length() == 2)
                        val parsed = (0 until lanesJson.length()).map { index ->
                            val row = lanesJson.getJSONObject(index)
                            val id = row.getInt("id")
                            require(id == 8 || id == 10)
                            Lane(
                                id = id, label = if (id == 8) "4K ANALYSE" else "THE BEST",
                                enabled = row.getBoolean("enabled"),
                                queued = row.getInt("queued").coerceAtLeast(0),
                                running = row.getInt("running").coerceAtLeast(0),
                                completed = row.getInt("completed").coerceAtLeast(0),
                                failed = row.getInt("failed").coerceAtLeast(0),
                                lastCompletionEpoch = if (row.isNull("last_completion_epoch")) null
                                    else row.getLong("last_completion_epoch")
                            )
                        }.sortedBy { it.id }
                        require(parsed.map { it.id } == listOf(8, 10))
                        snapshot = Snapshot(root.getLong("sampled_at_epoch"), parsed)
                        ""
                    }
                } finally {
                    connection.disconnect()
                }
            } catch (_: Exception) {
                "Status konnte nicht sicher vom Admin-Server geladen werden."
            }
            val result = snapshot
            main.post { onDone(result, message) }
        }
    }
}
