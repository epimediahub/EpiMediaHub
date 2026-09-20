package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.data.PairingPollResult
import de.epimediahub.app.data.PairingStartResult
import de.epimediahub.app.data.SetupCodeProvisioning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun V047WebAdminScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var connected by remember { mutableStateOf(SetupCodeProvisioning.sessionToken(context) != null) }
    var ticket by remember { mutableStateOf(SetupCodeProvisioning.savedPairing(context)) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var showLegacyCode by remember { mutableStateOf(false) }

    BackHandler { vm.back() }

    LaunchedEffect(Unit) {
        if (!u.webAdminRunning) vm.startWebAdmin()
    }

    val activeTicket = ticket
    LaunchedEffect(activeTicket?.pairingSecret) {
        if (activeTicket == null) return@LaunchedEffect
        while (true) {
            delay(2_500L)
            when (val result = withContext(Dispatchers.IO) {
                SetupCodeProvisioning.pollPairing(context.applicationContext, activeTicket)
            }) {
                PairingPollResult.Pending -> message = "Warte auf Freigabe im Dashboard …"
                is PairingPollResult.Connected -> {
                    connected = true
                    ticket = null
                    message = "Gerät wurde erfolgreich verbunden."
                    vm.refreshProfiles()
                    break
                }
                is PairingPollResult.Error -> {
                    message = result.message
                    if (result.terminal) {
                        ticket = null
                        break
                    }
                }
            }
        }
    }

    fun beginPairing() {
        if (busy) return
        busy = true
        message = ""
        scope.launch {
            when (val result = withContext(Dispatchers.IO) {
                SetupCodeProvisioning.startPairing(context.applicationContext)
            }) {
                is PairingStartResult.Success -> {
                    ticket = result.ticket
                    message = "Diesen Code im EpiMediaHub-Dashboard einem Kunden zuweisen."
                }
                is PairingStartResult.Error -> message = result.message
            }
            busy = false
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("GERÄT & WEBSETUP", R.drawable.brand_header, { vm.back() })
        BoxWithConstraints(
            Modifier.fillMaxSize().padding(
                horizontal = if (isTv) 34.dp else 10.dp,
                vertical = 8.dp
            )
        ) {
            val compact = maxHeight < 520.dp
            GlassPanel(Modifier.fillMaxSize()) {
                Row(
                    Modifier.fillMaxSize().padding(
                        horizontal = if (compact) 16.dp else 28.dp,
                        vertical = if (compact) 10.dp else 22.dp
                    ),
                    horizontalArrangement = Arrangement.spacedBy(if (compact) 18.dp else 34.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(
                        Modifier.weight(1f),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        Text("DASHBOARD", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black)
                        Spacer(Modifier.height(8.dp))
                        if (connected && ticket == null) {
                            Text("VERBUNDEN", color = Color.White, fontSize = if (compact) 27.sp else 38.sp, fontWeight = FontWeight.Black)
                            Text(
                                "Geräte-ID · " + SetupCodeProvisioning.deviceId(context).takeLast(12).uppercase(),
                                color = Color.White.copy(.72f),
                                fontSize = 12.sp
                            )
                            Spacer(Modifier.height(12.dp))
                            Text(
                                "Playlist-Zuweisungen werden beim App-Start und automatisch im Hintergrund aktualisiert.",
                                color = Color.White.copy(.82f),
                                fontSize = 12.sp
                            )
                        } else {
                            Text(
                                ticket?.code ?: "---- ----",
                                color = Color.White,
                                fontSize = if (compact) 30.sp else 46.sp,
                                fontWeight = FontWeight.Black,
                                letterSpacing = 4.sp
                            )
                            Spacer(Modifier.height(8.dp))
                            Text(
                                if (ticket == null) "Einmaligen Kopplungscode erzeugen"
                                else "Code im Dashboard unter „Gerät per Code verbinden“ eingeben",
                                color = Color.White.copy(.82f),
                                fontSize = 12.sp
                            )
                            Button(
                                onClick = { beginPairing() },
                                enabled = !busy,
                                modifier = Modifier.padding(top = 12.dp).v070TvFocus(accent),
                                colors = ButtonDefaults.buttonColors(containerColor = accent),
                                shape = RoundedCornerShape(12.dp)
                            ) {
                                Text(
                                    if (busy) "Wird erzeugt …" else if (ticket == null) "Kopplungscode erzeugen" else "Neuen Code erzeugen",
                                    color = Color.Black,
                                    fontWeight = FontWeight.Black
                                )
                            }
                        }
                        if (message.isNotBlank()) {
                            Text(message, color = Color.White.copy(.78f), fontSize = 11.sp, modifier = Modifier.padding(top = 9.dp))
                        }
                        TextButton(onClick = { showLegacyCode = true }, modifier = Modifier.v070TvFocus(accent)) {
                            Text("12-stelligen Einrichtungscode verwenden")
                        }
                    }

                    VerticalDivider(
                        modifier = Modifier.fillMaxHeight(.72f),
                        color = Color.White.copy(.13f)
                    )

                    Column(
                        Modifier.weight(1f),
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.Center
                    ) {
                        if (u.webAdminRunning) {
                            ParityQrCode(u.webAdminUrl)
                            Spacer(Modifier.height(if (compact) 4.dp else 10.dp))
                            Text("LOKALES WEBSETUP", color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black)
                            SelectionContainer {
                                Text(u.webAdminUrl, color = Color.White, fontSize = if (compact) 14.sp else 18.sp, fontWeight = FontWeight.Bold)
                            }
                            Text("Nur im gleichen Heimnetz erreichbar", color = Color.White.copy(.68f), fontSize = 11.sp)
                            Spacer(Modifier.height(8.dp))
                            Text("PIN  ${u.webAdminPin}", color = Color.White, fontSize = if (compact) 22.sp else 30.sp, fontWeight = FontWeight.Black, letterSpacing = 3.sp)
                        } else {
                            Text("Lokales Websetup wird gestartet …", color = Color.White)
                            Button(onClick = { vm.restartWebAdmin() }, modifier = Modifier.padding(top = 10.dp).v070TvFocus(accent)) {
                                Text("Erneut versuchen")
                            }
                        }
                    }
                }
            }
        }
    }

    if (showLegacyCode) {
        V051DashboardConnectDialog(
            onDismiss = { showLegacyCode = false },
            onProvisioned = {
                showLegacyCode = false
                connected = true
                message = "Gerät wurde erfolgreich verbunden."
                vm.refreshProfiles()
            }
        )
    }
}
