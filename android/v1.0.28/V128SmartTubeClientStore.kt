package de.epimediahub.app.ui

import android.content.Context
import java.security.MessageDigest

/** Remember the working client, never a playable URL, cookie or account name. */
internal class V128SmartTubeClientStore(context: Context, private val now: () -> Long = System::currentTimeMillis) {
    private val prefs = context.applicationContext.getSharedPreferences("epi_smarttube_clients_v128", Context.MODE_PRIVATE)
    private fun key(account: String): String = MessageDigest.getInstance("SHA-256")
        .digest(account.toByteArray()).joinToString("") { "%02x".format(it.toInt() and 255) }
    fun load(account: String): String? {
        val key = key(account)
        val age = now() - prefs.getLong("${key}_at", 0L)
        if (age !in 0 until 7L * 24 * 60 * 60 * 1000) return null
        return prefs.getString("${key}_client", null)?.takeIf { it.matches(Regex("[A-Z_]{2,40}")) }
    }
    fun remember(account: String, client: String) {
        if (!client.matches(Regex("[A-Z_]{2,40}"))) return
        val key = key(account)
        prefs.edit().putString("${key}_client", client).putLong("${key}_at", now()).apply()
    }
    fun clear(account: String) {
        val key = key(account)
        prefs.edit().remove("${key}_client").remove("${key}_at").apply()
    }
}
