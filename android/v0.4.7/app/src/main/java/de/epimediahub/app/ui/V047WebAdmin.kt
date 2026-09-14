package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.VpnKey
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.RemoteTailscaleManager
import de.epimediahub.app.Screen
import kotlinx.coroutines.delay

@Composable
fun V047WebAdminScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val ts by RemoteTailscaleManager.state.collectAsState()
    var showRemoteUnlock by remember { mutableStateOf(false) }
    BackHandler { vm.back() }

    LaunchedEffect(Unit) {
        if (!u.webAdminRunning) vm.startWebAdmin()
        if (u.remoteMaintenanceUnlocked) RemoteTailscaleManager.ensureConnected()
        while (true) {
            delay(2000L)
            vm.refreshWebAdminAccess()
        }
    }

    val port = u.webAdminUrl.substringAfterLast(':', "8765")
    val effectiveRemoteUrl = when {
        u.webAdminRemoteUrl.isNotBlank() -> u.webAdminRemoteUrl
        ts.tailscaleIp.isNotBlank() -> "http://${ts.tailscaleIp}:$port"
        else -> ""
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("WEBSETUP & FERNWARTUNG", R.drawable.brand_header, { vm.back() }, actions = {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    if (u.remoteMaintenanceUnlocked) Icons.Default.LockOpen else Icons.Default.Lock,
                    null,
                    tint = if (u.remoteMaintenanceUnlocked) accent else Color.White.copy(.78f),
                    modifier = Modifier.size(17.dp)
                )
                Spacer(Modifier.width(5.dp))
                Text(
                    if (u.remoteMaintenanceUnlocked) "Fernwartung freigeschaltet" else "Fernwartung gesperrt",
                    color = Color.White,
                    fontSize = 12.sp,
                    fontWeight = FontWeight.Bold
                )
            }
        })

        BoxWithConstraints(Modifier.fillMaxSize().padding(horizontal = if (isTv) 34.dp else 10.dp, vertical = 8.dp)) {
            val compact = maxHeight < 520.dp
            GlassPanel(Modifier.fillMaxSize()) {
                if (u.webAdminRunning) {
                    Row(
                        Modifier.fillMaxSize().padding(horizontal = if (compact) 16.dp else 28.dp, vertical = if (compact) 10.dp else 22.dp),
                        horizontalArrangement = Arrangement.spacedBy(if (compact) 18.dp else 34.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(
                            modifier = Modifier.width(if (compact) 235.dp else 300.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            ParityQrCode(u.webAdminUrl)
                            Spacer(Modifier.height(if (compact) 4.dp else 10.dp))
                            Text("LOKALES WEBSETUP", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black)
                            Text("QR scannen · gleiches lokales Netzwerk", color = Color.White.copy(.82f), fontSize = 11.sp)
                        }

                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.Center) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Computer, null, tint = accent, modifier = Modifier.size(if (compact) 27.dp else 34.dp))
                                Spacer(Modifier.width(9.dp))
                                Text("Playlist & Zugang verwalten", color = Color.White, fontSize = if (compact) 20.sp else 27.sp, fontWeight = FontWeight.Black)
                            }
                            Spacer(Modifier.height(if (compact) 6.dp else 12.dp))

                            Text("LOKALE ADRESSE", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)
                            SelectionContainer { Text(u.webAdminUrl, color = Color.White, fontSize = if (compact) 15.sp else 20.sp, fontWeight = FontWeight.Bold) }
                            Spacer(Modifier.height(if (compact) 4.dp else 8.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Lock, null, tint = accent, modifier = Modifier.size(19.dp))
                                Spacer(Modifier.width(7.dp))
                                Text("WEBSETUP-PIN", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)
                                Spacer(Modifier.width(10.dp))
                                Text(u.webAdminPin, color = Color.White, fontSize = if (compact) 25.sp else 36.sp, fontWeight = FontWeight.Black, letterSpacing = 4.sp)
                            }

                            HorizontalDivider(Modifier.padding(vertical = if (compact) 5.dp else 9.dp), color = Color.White.copy(.12f))

                            if (!u.remoteMaintenanceUnlocked) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.Lock, null, tint = Color.White.copy(.74f), modifier = Modifier.size(21.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("FERNWARTUNG GESPERRT", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Black)
                                }
                                Text(
                                    "Die separate Fernwartungs-PIN startet die automatische Tailscale-Einrichtung über deinen Raspberry. Kein Router-Port wird geöffnet.",
                                    color = Color.White.copy(.80f), fontSize = 11.sp, lineHeight = 15.sp
                                )
                                Spacer(Modifier.height(if (compact) 5.dp else 9.dp))
                                Button(
                                    onClick = { showRemoteUnlock = true },
                                    colors = ButtonDefaults.buttonColors(containerColor = accent),
                                    shape = RoundedCornerShape(12.dp)
                                ) {
                                    Icon(Icons.Default.VpnKey, null, tint = Color.Black, modifier = Modifier.size(18.dp))
                                    Spacer(Modifier.width(7.dp))
                                    Text("Fernwartung automatisch einrichten", color = Color.Black, fontWeight = FontWeight.Black)
                                }
                            } else {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.VpnKey, null, tint = if (ts.phase == RemoteTailscaleManager.Phase.CONNECTED) accent else Color.White.copy(.82f), modifier = Modifier.size(21.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("TAILSCALE · RASPBERRY", color = accent, fontSize = 13.sp, fontWeight = FontWeight.Black)
                                }
                                Spacer(Modifier.height(3.dp))
                                Text(ts.message, color = Color.White, fontSize = 12.sp, fontWeight = FontWeight.Bold)

                                if (effectiveRemoteUrl.isNotBlank()) {
                                    SelectionContainer {
                                        Text(effectiveRemoteUrl, color = Color.White, fontSize = if (compact) 15.sp else 18.sp, fontWeight = FontWeight.Black)
                                    }
                                    Text("Automatisch verbunden · nur im Tailnet erreichbar", color = Color.White.copy(.74f), fontSize = 11.sp)
                                } else if (ts.phase == RemoteTailscaleManager.Phase.VPN_PERMISSION) {
                                    Text("Bitte den einmaligen Android-VPN-Dialog bestätigen. Danach sind keine weiteren Tailscale-Anmeldungen nötig.", color = Color.White.copy(.74f), fontSize = 11.sp, lineHeight = 15.sp)
                                } else if (ts.phase == RemoteTailscaleManager.Phase.ERROR || ts.phase == RemoteTailscaleManager.Phase.PIN_REQUIRED) {
                                    if (ts.lastError.isNotBlank()) Text("Status: ${ts.lastError}", color = MaterialTheme.colorScheme.error, fontSize = 10.sp)
                                    Spacer(Modifier.height(4.dp))
                                    OutlinedButton(onClick = { showRemoteUnlock = true }, shape = RoundedCornerShape(12.dp)) {
                                        Icon(Icons.Default.Refresh, null, modifier = Modifier.size(17.dp))
                                        Spacer(Modifier.width(6.dp))
                                        Text("Einrichtung erneut starten")
                                    }
                                } else {
                                    LinearProgressIndicator(Modifier.fillMaxWidth().padding(top = 5.dp))
                                }

                                Spacer(Modifier.height(if (compact) 4.dp else 7.dp))
                                OutlinedButton(onClick = { vm.lockRemoteMaintenance() }, shape = RoundedCornerShape(12.dp)) {
                                    Icon(Icons.Default.Lock, null, modifier = Modifier.size(17.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text("Fernwartung wieder sperren")
                                }
                            }

                            Spacer(Modifier.height(if (compact) 3.dp else 6.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                if (u.playlists.isEmpty()) TextButton(onClick = { vm.navigate(Screen.AddPlaylist) }) { Text("Playlist am Gerät") }
                                TextButton(onClick = { vm.restartWebAdmin() }) { Text("Websetup neu starten") }
                            }
                        }
                    }
                } else {
                    Column(
                        Modifier.fillMaxSize().padding(24.dp),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Icon(Icons.Default.Computer, null, tint = accent, modifier = Modifier.size(48.dp))
                        Spacer(Modifier.height(10.dp))
                        Text("Websetup konnte nicht gestartet werden", color = Color.White, fontSize = 24.sp, fontWeight = FontWeight.Black)
                        if (u.error.isNotBlank()) Text(u.error, color = MaterialTheme.colorScheme.error, modifier = Modifier.padding(top = 8.dp))
                        Button(onClick = { vm.startWebAdmin() }, colors = ButtonDefaults.buttonColors(containerColor = accent), modifier = Modifier.padding(top = 18.dp)) {
                            Text("Erneut starten", color = Color.Black, fontWeight = FontWeight.Black)
                        }
                    }
                }
            }
        }
    }

    if (showRemoteUnlock) {
        V046FamilyPinDialog(
            title = "Fernwartung einrichten",
            message = "Fernwartungs-PIN eingeben. EpiMediaHub sucht danach automatisch deinen Raspberry, holt einen einmaligen Tailscale-Zugang und verbindet dieses Gerät.",
            pinLabel = "Fernwartungs-PIN",
            errorText = "Fernwartungs-PIN ist falsch.",
            onDismiss = { showRemoteUnlock = false },
            onVerify = { pin ->
                val ok = vm.unlockRemoteMaintenance(pin)
                if (ok) showRemoteUnlock = false
                ok
            }
        )
    }
}
