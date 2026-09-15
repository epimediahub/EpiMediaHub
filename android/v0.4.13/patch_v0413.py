#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"

# Version bump.
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
if 'versionCode = 52' not in s or 'versionName = "0.4.12"' not in s:
    raise SystemExit("v0.4.12 version anchors missing")
s = s.replace('versionCode = 52', 'versionCode = 53', 1)
s = s.replace('versionName = "0.4.12"', 'versionName = "0.4.13"', 1)
gradle.write_text(s)

for rel in ["ui/V044Home.kt", "ui/Screens.kt", "data/MediathekClient.kt"]:
    p = java / rel
    if p.exists():
        p.write_text(p.read_text().replace("0.4.12", "0.4.13"))

# Provisioning protocol used by both QR and manual setup-code login.
provision = java / "data/SetupCodeProvisioning.kt"
provision.write_text(r'''package de.epimediahub.app.data

import android.content.Context
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale

sealed class SetupCodeResult {
    data class Success(val payload: JSONObject) : SetupCodeResult()
    data class Error(val message: String) : SetupCodeResult()
}

object SetupCodeProvisioning {
    private const val PREFS = "epimediahub_provisioning"
    private const val KEY_PAYLOAD = "provisioning_payload"

    fun normalize(raw: String): String = raw.trim().uppercase(Locale.ROOT)
        .replace(Regex("[^A-Z0-9]"), "")
        .chunked(4).joinToString("-")

    fun isValid(code: String): Boolean = normalize(code).replace("-", "").length in 8..16

    /**
     * Resolve a setup code. The server URL is intentionally supplied by the caller/config,
     * so no customer credentials are compiled into the APK.
     */
    fun redeem(context: Context, baseUrl: String, rawCode: String): SetupCodeResult {
        val code = normalize(rawCode)
        if (!isValid(code)) return SetupCodeResult.Error("Einrichtungscode ungültig")
        if (!baseUrl.startsWith("https://")) return SetupCodeResult.Error("Provisionierungsserver nicht sicher konfiguriert")
        return try {
            val conn = (URL(baseUrl.trimEnd('/') + "/v1/setup/redeem").openConnection() as HttpURLConnection).apply {
                requestMethod = "POST"
                connectTimeout = 10000
                readTimeout = 15000
                doOutput = true
                setRequestProperty("Content-Type", "application/json; charset=utf-8")
                setRequestProperty("Accept", "application/json")
            }
            conn.outputStream.use { it.write(JSONObject().put("code", code).toString().toByteArray(Charsets.UTF_8)) }
            val status = conn.responseCode
            val body = (if (status in 200..299) conn.inputStream else conn.errorStream)?.bufferedReader()?.use { it.readText() }.orEmpty()
            when (status) {
                in 200..299 -> {
                    val payload = JSONObject(body)
                    context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
                        .putString(KEY_PAYLOAD, payload.toString()).apply()
                    SetupCodeResult.Success(payload)
                }
                404 -> SetupCodeResult.Error("Einrichtungscode ungültig")
                409 -> SetupCodeResult.Error("Einrichtungscode wurde bereits verwendet")
                410 -> SetupCodeResult.Error("Einrichtungscode ist abgelaufen")
                else -> SetupCodeResult.Error("Serverfehler ($status)")
            }
        } catch (_: Exception) {
            SetupCodeResult.Error("Provisionierungsserver nicht erreichbar")
        }
    }

    fun savedPayload(context: Context): JSONObject? = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        .getString(KEY_PAYLOAD, null)?.let { runCatching { JSONObject(it) }.getOrNull() }
}
''')

# Reusable Compose control. It can be placed beneath the existing QR action; QR and manual
# entry both feed the same redeem() protocol.
ui = java / "ui/SetupCodeLogin.kt"
ui.write_text(r'''package de.epimediahub.app.ui

import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import de.epimediahub.app.data.SetupCodeProvisioning
import de.epimediahub.app.data.SetupCodeResult
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.ui.platform.LocalContext

@Composable
fun SetupCodeLogin(
    provisioningBaseUrl: String,
    onProvisioned: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var code by remember { mutableStateOf("") }
    var error by remember { mutableStateOf<String?>(null) }
    var busy by remember { mutableStateOf(false) }

    Column(modifier = modifier.fillMaxWidth(), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text("Oder mit Einrichtungscode anmelden", style = MaterialTheme.typography.titleMedium)
        OutlinedTextField(
            value = code,
            onValueChange = { code = SetupCodeProvisioning.normalize(it); error = null },
            label = { Text("Einrichtungscode") },
            placeholder = { Text("z. B. EPI7-K4M9-2ABC") },
            singleLine = true,
            enabled = !busy,
            modifier = Modifier.fillMaxWidth()
        )
        Button(
            enabled = !busy && SetupCodeProvisioning.isValid(code),
            modifier = Modifier.fillMaxWidth(),
            onClick = {
                busy = true
                error = null
                scope.launch {
                    val result = withContext(Dispatchers.IO) {
                        SetupCodeProvisioning.redeem(context, provisioningBaseUrl, code)
                    }
                    busy = false
                    when (result) {
                        is SetupCodeResult.Success -> onProvisioned()
                        is SetupCodeResult.Error -> error = result.message
                    }
                }
            }
        ) { Text(if (busy) "Wird eingerichtet …" else "Mit Einrichtungscode anmelden") }
        error?.let { Text(it, color = MaterialTheme.colorScheme.error) }
    }
}
''')

print("Android v0.4.13 setup-code provisioning patch installed")
