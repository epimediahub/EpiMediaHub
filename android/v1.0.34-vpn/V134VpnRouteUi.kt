package de.epimediahub.app.vpn

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/** Fail-closed UI: remove the player subtree when the selected route is wrong. */
@Composable
fun v134RouteReady(context: Context, playlistId: String?): Boolean {
    var ready by remember(playlistId) { mutableStateOf(playlistId == null) }
    LaunchedEffect(context, playlistId) {
        if (playlistId == null) { ready = true; return@LaunchedEffect }
        while (true) {
            ready = withContext(Dispatchers.IO) {
                runCatching { V134VpnSession.routeReady(context, playlistId) }.getOrDefault(false)
            }
            delay(750)
        }
    }
    return ready
}

@Composable
fun V134VpnRouteBlockedScreen(
    context: Context, playlistName: String, onPlaylists: () -> Unit
) {
    Box(Modifier.fillMaxSize().background(Color(0xFF07111D)), contentAlignment = Alignment.Center) {
        Column(
            Modifier.fillMaxWidth(.83f),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(18.dp)
        ) {
            Text("VPN-SICHERHEITSSPERRE", color = Color(0xFFF5C15B),
                fontWeight = FontWeight.Black, fontSize = 27.sp)
            Text("Die Netzwerkroute für „" + playlistName + "“ ist noch nicht bestätigt. "
                 + "Wiedergabe bleibt gesperrt, damit der Stream nicht unbemerkt über die falsche Verbindung läuft.",
                 color = Color.White, fontSize = 19.sp)
            Button(onClick = {
                context.startActivity(Intent(context, V134VpnDiagnosticActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
            }) { Text("VPN-Verbindung überprüfen") }
            Button(onClick = onPlaylists) { Text("Playlist-Einstellungen öffnen") }
            Text("Nur für die getrennte EpiMediaHub-VPN-Beta. Kein automatischer Direkt-Fallback.",
                 color = Color.LightGray, fontSize = 13.sp)
        }
    }
}
