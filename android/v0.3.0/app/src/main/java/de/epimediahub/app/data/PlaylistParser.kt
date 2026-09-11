package de.epimediahub.app.data

import android.net.Uri
import de.epimediahub.app.model.PlaylistProfile
import de.epimediahub.app.model.PlaylistType
import java.net.URLEncoder
import java.util.UUID

object PlaylistParser {
    fun parse(name: String, rawUrl: String): PlaylistProfile {
        val url = rawUrl.trim()
        val uri = runCatching { Uri.parse(url) }.getOrNull()
        val user = uri?.getQueryParameter("username").orEmpty()
        val pass = uri?.getQueryParameter("password").orEmpty()
        val isXtream = user.isNotBlank() && pass.isNotBlank() &&
            (url.contains("get.php", true) || url.contains("player_api.php", true))
        if (isXtream && uri != null) {
            val path = uri.path.orEmpty()
            val suffix = when {
                path.endsWith("/get.php") -> "/get.php"
                path.endsWith("/player_api.php") -> "/player_api.php"
                else -> ""
            }
            val prefixPath = path.removeSuffix(suffix).trimEnd('/')
            val base = buildString {
                append(uri.scheme ?: "http").append("://").append(uri.encodedAuthority)
                if (prefixPath.isNotBlank()) append(prefixPath)
            }
            return PlaylistProfile(
                id = UUID.randomUUID().toString(),
                name = name.ifBlank { "IPTV" },
                originalUrl = url,
                type = PlaylistType.XTREAM,
                server = base,
                username = user,
                password = pass,
                output = uri.getQueryParameter("output") ?: "ts"
            )
        }
        return PlaylistProfile(
            id = UUID.randomUUID().toString(),
            name = name.ifBlank { "M3U" },
            originalUrl = url,
            type = PlaylistType.M3U
        )
    }

    fun fromXtream(name: String, rawServer: String, username: String, password: String, output: String = "ts"): PlaylistProfile {
        val server = normalizeServer(rawServer)
        require(server.isNotBlank()) { "Portal / Domain fehlt." }
        require(username.isNotBlank()) { "Username fehlt." }
        require(password.isNotBlank()) { "Passwort fehlt." }
        val encUser = URLEncoder.encode(username.trim(), "UTF-8")
        val encPass = URLEncoder.encode(password, "UTF-8")
        val getUrl = "$server/get.php?username=$encUser&password=$encPass&type=m3u_plus&output=$output"
        return PlaylistProfile(
            id = UUID.randomUUID().toString(),
            name = name.ifBlank { "Xtream" },
            originalUrl = getUrl,
            type = PlaylistType.XTREAM,
            server = server,
            username = username.trim(),
            password = password,
            output = output
        )
    }

    private fun normalizeServer(raw: String): String {
        var value = raw.trim().trimEnd('/')
        if (value.isBlank()) return ""
        if (!value.startsWith("http://", true) && !value.startsWith("https://", true)) value = "http://$value"
        val uri = Uri.parse(value)
        require(!uri.host.isNullOrBlank()) { "Portal / Domain ist ungültig." }
        return value
    }
}
