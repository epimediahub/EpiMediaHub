package de.epimediahub.app.vpn

import android.content.Context
import android.content.Intent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

/** Blocks the player subtree until the configured or explicitly approved route is verified. */
@Composable
fun v134RouteReady(context: Context, playlistId: String?): Boolean {
    var ready by remember(playlistId) { mutableStateOf(playlistId == null) }
    LaunchedEffect(context, playlistId) {
        if (playlistId == null) { ready = true; return@LaunchedEffect }
        // Initial route is always rebuilt after process recreation: the old
        // in-memory Route enum is BLOCKED even when the Android tunnel is still UP.
        // This preserves the saved per-playlist selection, and never allows
        // playback before a fresh verified exit check succeeds.
        ready = withContext(Dispatchers.IO) {
            runCatching { V134VpnSession.routeTo(context, playlistId) }.getOrDefault(false)
        }
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
    context: Context,
    playlistId: String,
    playlistName: String,
    onPlaylists: () -> Unit,
    onDirectApproved: () -> Unit
) {
    val scope = rememberCoroutineScope()
    val declineFocus = remember(playlistId) { FocusRequester() }
    var showConfirmation by remember(playlistId) { mutableStateOf(false) }
    var busy by remember(playlistId) { mutableStateOf(false) }
    var failed by remember(playlistId) { mutableStateOf(false) }
    var initialRouteCheck by remember(playlistId) { mutableStateOf(true) }
    LaunchedEffect(playlistId) {
        delay(5500)
        initialRouteCheck = false
    }
    val canOfferDirect = V134VpnSession.needsDirectFallbackPrompt(context, playlistId)
    // Never default Fire TV D-pad focus to the privacy-exposing confirmation.
    LaunchedEffect(showConfirmation) {
        if (showConfirmation) {
            delay(120)
            runCatching { declineFocus.requestFocus() }
        }
    }
    Box(
        Modifier.fillMaxSize().background(Color(0xFF07111D)),
        contentAlignment = Alignment.Center
    ) {
        Column(
            Modifier.fillMaxWidth(.83f),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.spacedBy(18.dp)
        ) {
            Text(
                if (initialRouteCheck) "NETZWERKVERBINDUNG WIRD GEPRÜFT" else "VPN-VERBINDUNG UNTERBROCHEN",
                color = Color(0xFFF5C15B),
                fontWeight = FontWeight.Black,
                fontSize = 27.sp
            )
            Text(
                "Für „" + playlistName + "“ ist die eingestellte Netzwerkverbindung " +
                    "nicht bestätigt. Die Wiedergabe wurde angehalten.",
                color = Color.White, fontSize = 19.sp
            )
            if (canOfferDirect) {
                Text(
                    "Du kannst einmalig ohne VPN fortfahren. Dein IPTV-Anbieter " +
                        "sieht dann deine normale öffentliche IP-Adresse.",
                    color = Color.White, fontSize = 16.sp
                )
                V141FocusButton(
                    label = "Ohne VPN fortfahren …",
                    accent = Color(0xFFF5C15B),
                    onClick = { showConfirmation = true },
                    enabled = !busy
                )
            }
            if (failed) {
                Text(
                    "Direktverbindung konnte nicht bestätigt werden. " +
                        "Die Wiedergabe bleibt gesperrt.",
                    color = Color(0xFFFFA89D), fontSize = 16.sp
                )
            }
            V141FocusButton(
                label = "VPN-Verbindung überprüfen",
                accent = Color(0xFFF5C15B),
                onClick = { context.startActivity(Intent(context, V134VpnDiagnosticActivity::class.java)) },
                enabled = !busy
            )
            V141FocusButton(
                label = "Playlist-Einstellungen öffnen",
                accent = Color(0xFFF5C15B),
                onClick = onPlaylists,
                enabled = !busy
            )
            Text(
                "Keine automatische Direktverbindung. Entscheidung nur für diese " +
                    "Sitzung; „VPN Finnland“ bleibt für den nächsten Playlist-Wechsel gespeichert.",
                color = Color.LightGray, fontSize = 13.sp
            )
        }
        if (showConfirmation) {
            AlertDialog(
                onDismissRequest = { if (!busy) showConfirmation = false },
                title = { Text("Wirklich ohne VPN fortfahren?") },
                text = {
                    Text(
                        "Finnland-VPN ist nicht verfügbar. Wenn du fortfährst, " +
                            "verbindet sich „" + playlistName + "“ direkt mit deinem " +
                            "Internetprovider. Dein IPTV-Anbieter kann deine normale " +
                            "öffentliche IP-Adresse erkennen. Nur für diese " +
                            "Sitzung, bis die Playlist neu gewählt wird; die Einstellung bleibt VPN Finnland."
                    )
                },
                confirmButton = {
                    TextButton(
                        enabled = !busy,
                        onClick = {
                            if (busy) return@TextButton
                            busy = true
                            failed = false
                            scope.launch {
                                val verified = withContext(Dispatchers.IO) {
                                    V134VpnSession.allowDirectOnce(context, playlistId)
                                }
                                busy = false
                                showConfirmation = false
                                if (verified) {
                                    // Re-prepare and reselect the SAME live channel under the
                                    // verified direct route; no manual channel-zapping needed.
                                    onDirectApproved()
                                } else failed = true
                            }
                        }
                    ) { Text(if (busy) "Verbindung wird geprüft …" else "Ja, einmal direkt") }
                },
                dismissButton = {
                    TextButton(
                        modifier = Modifier.focusRequester(declineFocus),
                        onClick = { showConfirmation = false },
                        enabled = !busy
                    ) { Text("Nein, VPN beibehalten") }
                }
            )
        }
    }
}
