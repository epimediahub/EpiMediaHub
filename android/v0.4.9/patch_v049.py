#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


# ---------------------------------------------------------------------------
# Version metadata.
# ---------------------------------------------------------------------------
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
require_once(s, 'versionCode = 48', 'v0.4.8 versionCode')
require_once(s, 'versionName = "0.4.8"', 'v0.4.8 versionName')
s = s.replace('versionCode = 48', 'versionCode = 49', 1)
s = s.replace('versionName = "0.4.8"', 'versionName = "0.4.9"', 1)
gradle.write_text(s)

# Visible version labels / HTTP user agents inherited from v0.4.8.
for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        t = p.read_text().replace("0.4.8", "0.4.9")
        p.write_text(t)


# ---------------------------------------------------------------------------
# RemoteTailscaleManager: find the trusted Raspberry even when DHCP changed its
# address. First try mDNS + legacy fallback, then scan every local IPv4 /24 for
# the *actual* EpiMediaHub health signature on port 8787 in parallel.
# ---------------------------------------------------------------------------
remote = java / "RemoteTailscaleManager.kt"
s = remote.read_text()

imports_old = '''import java.net.HttpURLConnection\nimport java.net.URL\nimport java.util.UUID\n'''
imports_new = '''import java.net.HttpURLConnection\nimport java.net.Inet4Address\nimport java.net.NetworkInterface\nimport java.net.URL\nimport java.util.UUID\nimport java.util.concurrent.Callable\nimport java.util.concurrent.ExecutorCompletionService\nimport java.util.concurrent.Executors\n'''
require_once(s, imports_old, 'network imports')
s = s.replace(imports_old, imports_new, 1)

old_discovery = '''    private fun findProvisioner(): String? {\n        for (base in PROVISIONER_BASES) {\n            if (checkProvisioner(base)) return base\n        }\n        return null\n    }\n\n    private fun checkProvisioner(base: String): Boolean = try {\n        val conn = (URL("$base/health").openConnection() as HttpURLConnection).apply {\n            connectTimeout = 2500\n            readTimeout = 2500\n            requestMethod = "GET"\n            useCaches = false\n        }\n        try { conn.responseCode == 200 } finally { conn.disconnect() }\n    } catch (_: Exception) {\n        false\n    }\n'''
new_discovery = '''    private fun findProvisioner(): String? {\n        // Fast paths first: mDNS plus the historical fixed address.\n        for (base in PROVISIONER_BASES) {\n            if (checkProvisioner(base, 700)) return base\n        }\n\n        // DHCP may assign the Raspberry a different address. Discover every\n        // site-local IPv4 /24 that this Android device is actually attached to\n        // and probe port 8787 concurrently. The response body is validated, so\n        // the app's own Websetup on the same port cannot be mistaken for the Pi.\n        val candidates = localProvisionerCandidates()\n        if (candidates.isEmpty()) return null\n\n        val workers = minOf(32, candidates.size)\n        val pool = Executors.newFixedThreadPool(workers)\n        val completion = ExecutorCompletionService<String?>(pool)\n        try {\n            candidates.forEach { base ->\n                completion.submit(Callable {\n                    if (checkProvisioner(base, 450)) base else null\n                })\n            }\n            repeat(candidates.size) {\n                val found = runCatching { completion.take().get() }.getOrNull()\n                if (!found.isNullOrBlank()) return found\n            }\n        } finally {\n            pool.shutdownNow()\n        }\n        return null\n    }\n\n    private fun localProvisionerCandidates(): List<String> {\n        val result = linkedSetOf<String>()\n        runCatching {\n            val interfaces = NetworkInterface.getNetworkInterfaces() ?: return@runCatching\n            while (interfaces.hasMoreElements()) {\n                val iface = interfaces.nextElement()\n                if (!iface.isUp || iface.isLoopback) continue\n                val addresses = iface.inetAddresses\n                while (addresses.hasMoreElements()) {\n                    val address = addresses.nextElement()\n                    if (address !is Inet4Address || !address.isSiteLocalAddress) continue\n                    val ownIp = address.hostAddress.orEmpty()\n                    val parts = ownIp.split('.')\n                    if (parts.size != 4) continue\n                    val prefix = parts.take(3).joinToString(".")\n                    for (host in 1..254) {\n                        val ip = "$prefix.$host"\n                        if (ip != ownIp) result += "http://$ip:8787"\n                    }\n                }\n            }\n        }\n        return result.toList()\n    }\n\n    private fun checkProvisioner(base: String, timeoutMs: Int = 700): Boolean = try {\n        val conn = (URL("$base/health").openConnection() as HttpURLConnection).apply {\n            connectTimeout = timeoutMs\n            readTimeout = timeoutMs\n            requestMethod = "GET"\n            useCaches = false\n            setRequestProperty("Accept", "application/json")\n        }\n        try {\n            if (conn.responseCode != 200) {\n                false\n            } else {\n                val body = conn.inputStream.bufferedReader().use { it.readText() }\n                val json = JSONObject(body.ifBlank { "{}" })\n                json.optBoolean("ok", false) &&\n                    json.optString("service") == "epimediahub-provisioner"\n            }\n        } finally {\n            conn.disconnect()\n        }\n    } catch (_: Exception) {\n        false\n    }\n'''
require_once(s, old_discovery, 'v0.4.8 provisioner discovery')
s = s.replace(old_discovery, new_discovery, 1)

s = s.replace(
    '"Raspberry-Provisioner nicht erreichbar. Ersteinrichtung muss einmal im Heimnetz erfolgen."',
    '"EpiMediaHub-Provisioner im lokalen Netz nicht gefunden (Port 8787). Prüfe, ob der Raspberry-Dienst läuft."',
)
s = s.replace('EpiMediaHub-Android/0.4.8', 'EpiMediaHub-Android/0.4.9')
remote.write_text(s)


# ---------------------------------------------------------------------------
# Player: remove the persistent remote-control cheat-sheet from the picture.
# Key mappings remain unchanged; only the always-visible TV overlay disappears.
# ---------------------------------------------------------------------------
player = java / "ui/PlayerScreen.kt"
s = player.read_text()
old_help = '''\n        if (isTv && controls) {\n            Surface(\n                modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 14.dp),\n                color = Color.Black.copy(alpha = .58f),\n                shape = MaterialTheme.shapes.large\n            ) {\n                Text(\n                    "←/→ Episode oder ±10 s   ·   1/3 Episode   ·   4/6 ±10 s   ·   5 Play/Pause",\n                    color = Color.White.copy(alpha = .80f),\n                    modifier = Modifier.padding(horizontal = 16.dp, vertical = 8.dp)\n                )\n            }\n        }\n'''
require_once(s, old_help, 'persistent TV player help overlay')
s = s.replace(old_help, '\n', 1)
player.write_text(s)

print("Android v0.4.9 LAN discovery + clean player patch applied")
