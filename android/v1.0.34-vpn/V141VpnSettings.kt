package de.epimediahub.app.vpn

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.net.VpnService
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Settings-only entry point. Never creates another launcher/back-stack activity. */
@Composable
fun V141VpnSettingsHost(
    context: Context,
    playlistId: String?,
    accent: Color,
    settingsContent: @Composable () -> Unit
) {
    var open by remember { mutableStateOf(false) }
    if (open) {
        V141VpnSettingsScreen(context, playlistId, accent, onBack = { open = false })
    } else {
        Box(Modifier.fillMaxSize()) {
            settingsContent()
            V141FocusButton(
                label = "VPN & Netzwerk",
                accent = accent,
                onClick = { open = true },
                modifier = Modifier.align(Alignment.BottomEnd).padding(28.dp)
            )
        }
    }
}

@Composable
internal fun V141FocusButton(
    label: String,
    accent: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
    enabled: Boolean = true
) {
    var focused by remember { mutableStateOf(false) }
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier
            .onFocusChanged { focused = it.hasFocus }
            .border(
                BorderStroke(if (focused) 4.dp else 1.dp,
                    if (focused) Color.White else accent.copy(alpha = .75f)),
                RoundedCornerShape(16.dp)
            ),
        colors = ButtonDefaults.buttonColors(
            containerColor = if (focused) accent else Color(0xFF26354A),
            contentColor = Color.White
        ),
        shape = RoundedCornerShape(16.dp),
    ) {
        Text(label, fontWeight = FontWeight.Bold, fontSize = 18.sp)
    }
}

/** Explicit route controls, never an implicit switch to a physical connection. */
@Composable
private fun V141VpnSettingsScreen(
    context: Context,
    playlistId: String?,
    accent: Color,
    onBack: () -> Unit
) {
    var speedOpen by remember { mutableStateOf(false) }
    if (speedOpen) {
        V140SpeedTestScreen(context, playlistId, true, accent, onBack = { speedOpen = false })
        return
    }
    val scope = rememberCoroutineScope()
    var busy by remember { mutableStateOf(false) }
    var status by remember { mutableStateOf("Wähle eine Verbindung. Die normale App bleibt dein Startbildschirm.") }
    var vpnUp by remember { mutableStateOf(false) }
    val hasProfile = V134VpnSession.hasProfile(context)

    fun verifyVpn() {
        if (busy) return
        busy = true
        status = "Finnland-Verbindung wird geprüft …"
        scope.launch {
            val result = withContext(Dispatchers.IO) {
                runCatching { V134VpnSession.connectAndVerify(context) }
            }
            busy = false
            result.onSuccess {
                vpnUp = true
                status = "Finnland-VPN bestätigt · Ausgang: $it"
            }.onFailure {
                vpnUp = false
                status = "VPN nicht freigegeben: ${it.message ?: "Verbindung fehlgeschlagen"}. Kein Direkt-Fallback."
            }
        }
    }

    val consent = rememberLauncherForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == Activity.RESULT_OK) verifyVpn()
        else status = "VPN-Zustimmung verweigert. Die Verbindung bleibt gesperrt."
    }

    BackHandler { onBack() }
    Column(
        Modifier.fillMaxSize().background(Color(0xFF07111D))
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 44.dp, vertical = 26.dp),
        verticalArrangement = Arrangement.spacedBy(18.dp)
    ) {
        Text("EINSTELLUNGEN · VPN & NETZWERK",
            fontSize = 27.sp, fontWeight = FontWeight.Black, color = Color.White)
        Text(status, fontSize = 19.sp, color = if (vpnUp) accent else Color.White)
        Text(
            if (hasProfile) "Gespeichertes VPN-Profil vorhanden."
            else "Noch kein VPN-Profil zugewiesen. Diese Beta benötigt vorläufig ein Testprofil.",
            color = Color.LightGray, fontSize = 16.sp
        )
        V141FocusButton("Finnland-VPN verbinden / prüfen", accent, onClick = {
            if (!hasProfile) {
                status = "Noch kein VPN-Profil vorhanden. Erst ein Testprofil über Diagnose importieren."
            } else {
                val request = VpnService.prepare(context)
                if (request == null) verifyVpn() else consent.launch(request)
            }
        }, enabled = !busy)
        V141FocusButton("VPN trennen · Direktverbindung", accent, onClick = {
            if (!busy) {
                busy = true
                status = "Direktverbindung wird ausdrücklich hergestellt und geprüft …"
                scope.launch {
                    val result = withContext(Dispatchers.IO) {
                        runCatching { V134VpnSession.disconnectAndVerify(context) }
                    }
                    busy = false
                    result.onSuccess {
                        vpnUp = false
                        status = "Direktverbindung bestätigt · Ausgang: $it"
                    }.onFailure {
                        status = "Keine Direktfreigabe: ${it.message ?: "Verbindung fehlgeschlagen"}"
                    }
                }
            }
        }, enabled = !busy)
        V141FocusButton("Speedtest", accent, onClick = { speedOpen = true }, enabled = !busy)
        V141FocusButton("Erweitert · VPN-Diagnose (Beta)", accent, onClick = {
            context.startActivity(Intent(context, V134VpnDiagnosticActivity::class.java))
        }, enabled = !busy)
        Text("Bei VPN-Ausfall bleibt die Wiedergabe gesperrt, bis die Verbindung bestätigt ist. " +
            "Ein Wechsel zur Direktverbindung erfolgt nie automatisch.",
            color = Color.White.copy(alpha = .75f), fontSize = 15.sp)
        V141FocusButton("Zurück zu Einstellungen", accent, onClick = onBack)
    }
}
