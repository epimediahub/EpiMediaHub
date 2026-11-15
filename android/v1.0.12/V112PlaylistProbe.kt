package de.epimediahub.app.data

import java.io.File
import java.io.IOException
import java.net.InetSocketAddress
import java.net.Socket
import java.net.URI

/** Same lightweight server reachability check as the Enigma playlist chooser. */
internal object V112PlaylistProbe {
    fun online(rawUrl: String): Boolean {
        val uri = runCatching { URI(rawUrl.trim()) }.getOrNull() ?: return false
        if (uri.scheme.equals("file", true)) {
            return runCatching { File(uri).let { it.isFile && it.length() > 0L } }.getOrDefault(false)
        }
        val scheme = uri.scheme?.lowercase() ?: return false
        if (scheme != "http" && scheme != "https") return false
        val host = uri.host?.takeIf { it.isNotBlank() } ?: return false
        val port = if (uri.port == -1) { if (scheme == "https") 443 else 80 } else uri.port
        if (port !in 1..65535) return false
        return try {
            Socket().use { it.connect(InetSocketAddress(host, port), 1_350) }
            true
        } catch (_: IOException) {
            false
        } catch (_: IllegalArgumentException) {
            false
        }
    }
}
