package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Computer
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.LockOpen
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
fun V046WebAdminScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    var showRemoteUnlock by remember { mutableStateOf(false) }
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
                            Spacer(Modifier.height(if (compact) 7.dp else 14.dp))

                            Text("LOKALE ADRESSE", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)
                            SelectionContainer {
                                Text(u.webAdminUrl, color = Color.White, fontSize = if (compact) 15.sp else 20.sp, fontWeight = FontWeight.Bold)
                            }
                            Spacer(Modifier.height(if (compact) 5.dp else 10.dp))
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Default.Lock, null, tint = accent, modifier = Modifier.size(19.dp))
                                Spacer(Modifier.width(7.dp))
                                Text("WEBSETUP-PIN", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black)
                                Spacer(Modifier.width(10.dp))
                                Text(u.webAdminPin, color = Color.White, fontSize = if (compact) 25.sp else 36.sp, fontWeight = FontWeight.Black, letterSpacing = 4.sp)
                            }

                            HorizontalDivider(Modifier.padding(vertical = if (compact) 6.dp else 11.dp), color = Color.White.copy(.12f))

                            if (!u.remoteMaintenanceUnlocked) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.Lock, null, tint = Color.White.copy(.74f), modifier = Modifier.size(21.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("RASPBERRY-FERNWARTUNG GESPERRT", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Black)
                                }
                                Spacer(Modifier.height(4.dp))
                                Text(
                                    "Fernzugriff ist deaktiviert. Freischaltung nur mit der speziellen Family-PIN – danach ausschließlich über Tailscale.",
                                    color = Color.White.copy(.80f),
                                    fontSize = 11.sp,
                                    lineHeight = 15.sp
                                )
                                Spacer(Modifier.height(if (compact) 6.dp else 10.dp))
                                Button(
                                    onClick = { showRemoteUnlock = true },
                                    colors = ButtonDefaults.buttonColors(containerColor = accent),
                                    shape = RoundedCornerShape(12.dp)
                                ) {
                                    Icon(Icons.Default.VpnKey, null, tint = Color.Black, modifier = Modifier.size(18.dp))
                                    Spacer(Modifier.width(7.dp))
                                    Text("Mit Family-PIN freischalten", color = Color.Black, fontWeight = FontWeight.Black)
                                }
                            } else {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Icon(Icons.Default.VpnKey, null, tint = accent, modifier = Modifier.size(21.dp))
                                    Spacer(Modifier.width(8.dp))
                                    Text("RASPBERRY-FERNWARTUNG · TAILSCALE", color = accent, fontSize = 13.sp, fontWeight = FontWeight.Black)
                                }
                                Spacer(Modifier.height(4.dp))
                                if (u.webAdminRemoteUrl.isNotBlank()) {
                                    SelectionContainer {
                                        Text(u.webAdminRemoteUrl, color = Color.White, fontSize = if (compact) 15.sp else 18.sp, fontWeight = FontWeight.Bold)
                                    }
                                    Text(
                                        "Freigegeben · nur über das Tailscale-Netz erreichbar. Dein Raspberry kann diese Adresse als Wartungszugang verwenden.",
                                        color = Color.White.copy(.82f),
                                        fontSize = 11.sp,
                                        lineHeight = 15.sp
                                    )
                                } else {
                                    Text("Family-Freigabe aktiv · Tailscale-Verbindung fehlt noch.", color = Color.White, fontSize = 13.sp, fontWeight = FontWeight.Bold)
                                    Text(
                                        "Dieses Gerät in Tailscale mit demselben Tailnet wie deinen Raspberry aufnehmen. Sobald eine 100.64.x.x–100.127.x.x-Adresse vorhanden ist, erscheint sie hier automatisch.",
                                        color = Color.White.copy(.72f),
                                        fontSize = 11.sp,
                                        lineHeight = 15.sp
                                    )
                                }
                                Spacer(Modifier.height(if (compact) 5.dp else 9.dp))
                                OutlinedButton(onClick = { vm.lockRemoteMaintenance() }, shape = RoundedCornerShape(12.dp)) {
                                    Icon(Icons.Default.Lock, null, modifier = Modifier.size(17.dp))
                                    Spacer(Modifier.width(6.dp))
                                    Text("Fernwartung wieder sperren")
                                }
                            }

                            Spacer(Modifier.height(if (compact) 4.dp else 8.dp))
                            Row(horizontalArrangement = Arrangement.spacedBy(9.dp)) {
                                TextButton(onClick = { vm.restartWebAdmin() }) { Text("Websetup neu starten") }
                                TextButton(onClick = { vm.stopWebAdmin() }) { Text("Websetup stoppen") }
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
            title = "Fernwartung freischalten",
            message = "Gib die spezielle Family-PIN ein. Die Freigabe öffnet ausschließlich den Tailscale-Wartungsweg für deinen Raspberry; es wird kein Internet-Port geöffnet.",
            onDismiss = { showRemoteUnlock = false },
            onVerify = { pin ->
                val ok = vm.unlockRemoteMaintenance(pin)
                if (ok) showRemoteUnlock = false
                ok
            }
        )
    }
}
