package de.epimediahub.app.data

import de.epimediahub.app.model.PlaylistProfile
import fi.iki.elonen.NanoHTTPD
import java.net.Inet4Address
import java.net.NetworkInterface
import java.util.Collections

class LocalWebAdmin(
    port: Int = 8787,
    private val pin: String,
    private val playlistsProvider: () -> List<PlaylistProfile>,
    private val onAddM3u: (name: String, url: String) -> Unit,
    private val onAddXtream: (name: String, portal: String, username: String, password: String) -> Unit
) : NanoHTTPD(port) {

    val address: String
        get() = "http://${localIpv4() ?: "127.0.0.1"}:$listeningPort"

    override fun serve(session: IHTTPSession): Response {
        if (!isPrivateClient(session.remoteIpAddress.orEmpty())) {
            return newFixedLengthResponse(Response.Status.FORBIDDEN, "text/plain; charset=utf-8", "Nur im lokalen Netzwerk verfügbar.")
        }
        return runCatching {
            if (session.method == Method.POST) handlePost(session) else page(message = "")
        }.getOrElse { e ->
            page("Fehler: ${html(e.message ?: "Unbekannter Fehler")}", isError = true)
        }
    }

    private fun handlePost(session: IHTTPSession): Response {
        val files = HashMap<String, String>()
        session.parseBody(files)
        val p = session.parameters.mapValues { it.value.firstOrNull().orEmpty() }
        if (p["pin"].orEmpty().trim() != pin) return page("PIN ist falsch.", isError = true)
        val type = p["type"].orEmpty()
        val name = p["name"].orEmpty().trim()
        when (type) {
            "xtream" -> {
                val portal = p["portal"].orEmpty().trim()
                val username = p["username"].orEmpty().trim()
                val password = p["password"].orEmpty()
                require(portal.isNotBlank() && username.isNotBlank() && password.isNotBlank()) { "Portal, Benutzername und Passwort sind erforderlich." }
                onAddXtream(name, portal, username, password)
                return page("Xtream-Profil wurde an EpiMediaHub übertragen.")
            }
            "m3u" -> {
                val url = p["url"].orEmpty().trim()
                require(url.isNotBlank()) { "M3U-URL fehlt." }
                onAddM3u(name, url)
                return page("Playlist wurde an EpiMediaHub übertragen.")
            }
            else -> return page("Unbekannter Playlist-Typ.", isError = true)
        }
    }

    private fun page(message: String, isError: Boolean = false): Response {
        val profiles = playlistsProvider().joinToString("") { p ->
            "<div class='profile'><strong>${html(p.name)}</strong><span>${html(p.type.name)}</span></div>"
        }
        val notice = if (message.isBlank()) "" else "<div class='notice ${if (isError) "error" else "ok"}'>$message</div>"
        val body = """
<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>EpiMediaHub · Playlist Verwaltung</title><style>
:root{color-scheme:dark;--accent:#35b8ff;--card:rgba(12,24,44,.88);--line:rgba(255,255,255,.12)}
*{box-sizing:border-box}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;background:radial-gradient(circle at 20% 0%,#17385f 0,#09111f 35%,#060a12 78%);color:#fff;min-height:100vh}
.wrap{max-width:980px;margin:auto;padding:32px 18px 64px}.hero{padding:28px 30px;border:1px solid var(--line);border-radius:30px;background:linear-gradient(135deg,rgba(22,48,83,.92),rgba(8,18,34,.82));box-shadow:0 22px 70px rgba(0,0,0,.28)}
h1{margin:0;font-size:clamp(28px,5vw,48px);letter-spacing:-1.4px}.sub{color:#b8c6d8;margin-top:8px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:18px;margin-top:20px}.card{padding:22px;border:1px solid var(--line);border-radius:26px;background:var(--card);backdrop-filter:blur(18px)}
h2{margin:0 0 16px;font-size:21px}.field{margin:11px 0}label{display:block;color:#aebdce;font-size:13px;margin:0 0 6px}input{width:100%;border-radius:16px;border:1px solid var(--line);background:#091525;color:#fff;padding:13px 14px;font-size:16px;outline:none}input:focus{border-color:var(--accent);box-shadow:0 0 0 3px rgba(53,184,255,.14)}
button{width:100%;margin-top:10px;border:0;border-radius:16px;padding:14px;font-weight:800;font-size:15px;background:linear-gradient(135deg,#24a9f5,#5fd1ff);color:#03101b;cursor:pointer}.hint{font-size:12px;color:#8496aa;margin-top:10px}.profile{display:flex;justify-content:space-between;padding:12px 0;border-bottom:1px solid rgba(255,255,255,.07)}.profile span{color:#7fbfe8;font-size:12px}.notice{margin-top:18px;border-radius:16px;padding:13px 15px}.ok{background:rgba(36,196,120,.14);border:1px solid rgba(36,196,120,.32)}.error{background:rgba(255,89,89,.12);border:1px solid rgba(255,89,89,.32)}
</style></head><body><main class="wrap"><section class="hero"><h1>EpiMediaHub</h1><div class="sub">Playlist-Verwaltung im lokalen Netzwerk · Android TV & Mobile</div>$notice</section>
<div class="grid"><section class="card"><h2>Xtream Codes</h2><form method="post"><input type="hidden" name="type" value="xtream"><div class="field"><label>PIN aus der App</label><input name="pin" inputmode="numeric" autocomplete="off" required></div><div class="field"><label>Name</label><input name="name" placeholder="z. B. Wohnzimmer"></div><div class="field"><label>Portal / Domain</label><input name="portal" placeholder="http://server.tld:8080" required></div><div class="field"><label>Username</label><input name="username" autocomplete="off" required></div><div class="field"><label>Passwort</label><input name="password" type="password" autocomplete="off" required></div><button>Xtream hinzufügen</button><div class="hint">EpiMediaHub erstellt API-, Live-, Film- und Serien-URLs automatisch.</div></form></section>
<section class="card"><h2>M3U Playlist</h2><form method="post"><input type="hidden" name="type" value="m3u"><div class="field"><label>PIN aus der App</label><input name="pin" inputmode="numeric" autocomplete="off" required></div><div class="field"><label>Name</label><input name="name" placeholder="z. B. Zweite Liste"></div><div class="field"><label>M3U / get.php URL</label><input name="url" placeholder="https://…" required></div><button>Playlist hinzufügen</button></form><h2 style="margin-top:26px">Gespeichert</h2>${if (profiles.isBlank()) "<div class='sub'>Noch keine Playlist.</div>" else profiles}</section></div>
</main></body></html>
""".trimIndent()
        return newFixedLengthResponse(Response.Status.OK, "text/html; charset=utf-8", body)
    }

    private fun html(value: String): String = value
        .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace("\"", "&quot;").replace("'", "&#39;")

    private fun localIpv4(): String? = runCatching {
        Collections.list(NetworkInterface.getNetworkInterfaces())
            .filter { it.isUp && !it.isLoopback }
            .flatMap { Collections.list(it.inetAddresses) }
            .filterIsInstance<Inet4Address>()
            .firstOrNull { it.isSiteLocalAddress }
            ?.hostAddress
    }.getOrNull()

    private fun isPrivateClient(ip: String): Boolean {
        if (ip.isBlank() || ip == "127.0.0.1" || ip == "::1") return true
        if (ip.startsWith("192.168.") || ip.startsWith("10.") || ip.startsWith("fd") || ip.startsWith("fe80:")) return true
        val parts = ip.split('.')
        if (parts.size == 4 && parts[0] == "172") {
            val second = parts[1].toIntOrNull() ?: return false
            if (second in 16..31) return true
        }
        return false
    }
}
