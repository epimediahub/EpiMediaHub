package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.Lock
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
import kotlinx.coroutines.delay

@Composable
fun V045WebAdminScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    BackHandler { vm.back() }
    LaunchedEffect(Unit) {
        if (!u.webAdminRunning) vm.startWebAdmin()
        while (true) {
            delay(3000L)
            vm.refreshWebAdminAccess()
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("WEBSETUP & FERNWARTUNG", R.drawable.brand_header, { vm.back() }, actions = {
            Text("PIN-geschützt", color = Color.White.copy(.90f), fontSize = 12.sp, fontWeight = FontWeight.Bold)
        })

        BoxWithConstraints(Modifier.fillMaxSize().padding(horizontal = if (isTv) 34.dp else 10.dp, vertical = 8.dp)) {
            val compact = maxHeight < 520.dp
            GlassPanel(Modifier.fillMaxSize()) {
                if (u.webAdminRunning) {
                    Row(
                        Modifier.fillMaxSize().padding(horizontal = if (compact) 18.dp else 28.dp, vertical = if (compact) 14.dp else 22.dp),
                        horizontalArrangement = Arrangement.spacedBy(if (compact) 22.dp else 34.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Column(
                            modifier = Modifier.width(if (compact) 250.dp else 300.dp),
                            horizontalAlignment = Alignment.CenterHorizontally
                        ) {
                            ParityQrCode(u.webAdminUrl)
                            Spacer(Modifier.height(if (compact) 6.dp else 10.dp))
                            Text("LOKALES WEBSETUP", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black)
                            Text("QR scannen", color = Color.White.copy(.84f), fontSize = 12.sp)
                        }

                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.Center) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Computer, null, tint = accent, modifier = Modifier.size(if (compact) 28.dp else 34.dp))
                                Spacer(Modifier.width(10.dp))
                                Text("Playlist & Zugang verwalten", color = Color.White, fontSize = if (compact) 21.sp else 27.sp, fontWeight = FontWeight.Black)
                            }
                            Spacer(Modifier.height(if (compact) 10.dp else 16.dp))

                            Text("LOKALE ADRESSE", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)
                            SelectionContainer {
                                Text(u.webAdminUrl, color = Color.White, fontSize = if (compact) 16.sp else 20.sp, fontWeight = FontWeight.Bold)
                            }

                            Spacer(Modifier.height(if (compact) 10.dp else 15.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Lock, null, tint = accent, modifier = Modifier.size(22.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("PIN", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black)
                            }
                            Text(
                                u.webAdminPin,
                                color = Color.White,
                                fontSize = if (compact) 30.sp else 42.sp,
                                fontWeight = FontWeight.Black,
                                letterSpacing = 6.sp
                            )

                            Spacer(Modifier.height(if (compact) 8.dp else 13.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.VpnKey, null, tint = if (u.webAdminRemoteUrl.isNotBlank()) accent else Color.White.copy(.55f), modifier = Modifier.size(22.dp))
                                Spacer(Modifier.width(8.dp))
                                Text("FERNWARTUNG ÜBER VPN", color = if (u.webAdminRemoteUrl.isNotBlank()) accent else Color.White.copy(.72f), fontSize = 12.sp, fontWeight = FontWeight.Black)
                            }
                            if (u.webAdminRemoteUrl.isNotBlank()) {
                                SelectionContainer {
                                    Text(u.webAdminRemoteUrl, color = Color.White, fontSize = if (compact) 15.sp else 18.sp, fontWeight = FontWeight.Bold)
                                }
                                Text("WireGuard/Tailscale erkannt · kein öffentlicher Port nötig", color = Color.White.copy(.82f), fontSize = 12.sp)
                            } else {
                                Text("Noch keine WireGuard-/Tailscale-Verbindung erkannt.", color = Color.White.copy(.76f), fontSize = 12.sp)
                                Text("Sobald ein VPN aktiv ist, erscheint hier automatisch die Fernwartungsadresse.", color = Color.White.copy(.62f), fontSize = 11.sp)
                            }

                            Spacer(Modifier.height(if (compact) 8.dp else 14.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                OutlinedButton(onClick = { vm.restartWebAdmin() }, shape = RoundedCornerShape(12.dp)) { Text("Neu starten") }
                                OutlinedButton(onClick = { vm.stopWebAdmin() }, shape = RoundedCornerShape(12.dp)) { Text("Stoppen") }
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
}
