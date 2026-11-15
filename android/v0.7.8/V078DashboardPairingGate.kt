package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.data.PairingPollResult
import de.epimediahub.app.data.PairingStartResult
import de.epimediahub.app.data.PairingTicket
import de.epimediahub.app.data.SetupCodeProvisioning
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
fun V078DashboardPairingGate(
    vm: MainViewModel,
    accent: Color,
    isTv: Boolean,
    onConnected: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var ticket by remember { mutableStateOf<PairingTicket?>(SetupCodeProvisioning.savedPairing(context)) }
    var busy by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("Verbindung zum Dashboard wird vorbereitet …") }
    var showLegacyCode by remember { mutableStateOf(false) }

    fun startPairing() {
        if (busy) return
        busy = true
        message = "Kopplungscode wird erzeugt …"
        scope.launch {
            when (val result = withContext(Dispatchers.IO) {
                SetupCodeProvisioning.startPairing(context.applicationContext)
            }) {
                is PairingStartResult.Success -> {
                    ticket = result.ticket
                    message = "Diesen Code im Dashboard einem Kunden zuweisen."
                }
                is PairingStartResult.Error -> {
                    ticket = null
                    message = result.message
                }
            }
            busy = false
        }
    }

    LaunchedEffect(Unit) {
        if (ticket == null && SetupCodeProvisioning.sessionToken(context.applicationContext) == null) {
            startPairing()
        }
    }

    val activeTicket = ticket
    LaunchedEffect(activeTicket?.pairingSecret) {
        if (activeTicket == null) return@LaunchedEffect
        while (true) {
            delay(2_000L)
            when (val result = withContext(Dispatchers.IO) {
                SetupCodeProvisioning.pollPairing(context.applicationContext, activeTicket)
            }) {
                PairingPollResult.Pending -> {
                    message = "Warte auf Freigabe im Dashboard …"
                }
                is PairingPollResult.Connected -> {
                    ticket = null
                    message = "Gerät verbunden."
                    vm.refreshProfiles()
                    onConnected()
                    break
                }
                is PairingPollResult.Error -> {
                    message = result.message
                    if (result.terminal) {
                        ticket = null
                        delay(600L)
                        startPairing()
                        break
                    }
                }
            }
        }
    }

    BackHandler(enabled = true) { /* mandatory first-run gate */ }

    Box(
        Modifier.fillMaxSize()
            .background(
                Brush.verticalGradient(
                    listOf(Color(0xFF06111C), Color(0xFF0B1E30), Color(0xFF05090F))
                )
            ),
        contentAlignment = Alignment.Center
    ) {
        Card(
            modifier = Modifier
                .fillMaxWidth(if (isTv) .62f else .92f)
                .wrapContentHeight()
                .padding(12.dp),
            shape = RoundedCornerShape(if (isTv) 28.dp else 22.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xEE0B1520)),
            border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(.55f))
        ) {
            Column(
                Modifier.fillMaxWidth().padding(if (isTv) 34.dp else 22.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                androidx.compose.foundation.Image(
                    painter = androidx.compose.ui.res.painterResource(R.drawable.brand_header),
                    contentDescription = "EpiMediaHub",
                    modifier = Modifier
                        .width(if (isTv) 330.dp else 230.dp)
                        .height(if (isTv) 105.dp else 78.dp)
                )

                Text(
                    "GERÄT MIT DASHBOARD VERBINDEN",
                    color = accent,
                    fontSize = if (isTv) 18.sp else 14.sp,
                    fontWeight = FontWeight.Black,
                    textAlign = TextAlign.Center
                )

                Spacer(Modifier.height(if (isTv) 22.dp else 16.dp))

                Surface(
                    color = Color.White.copy(.06f),
                    shape = RoundedCornerShape(16.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(.10f))
                ) {
                    Text(
                        ticket?.code ?: if (busy) "••••••••" else "--------",
                        modifier = Modifier.padding(
                            horizontal = if (isTv) 36.dp else 22.dp,
                            vertical = if (isTv) 20.dp else 16.dp
                        ),
                        color = Color.White,
                        fontSize = if (isTv) 44.sp else 34.sp,
                        fontWeight = FontWeight.Black,
                        letterSpacing = if (isTv) 6.sp else 4.sp
                    )
                }

                Spacer(Modifier.height(14.dp))

                Text(
                    message,
                    color = Color.White.copy(.82f),
                    fontSize = if (isTv) 15.sp else 13.sp,
                    textAlign = TextAlign.Center
                )

                Spacer(Modifier.height(8.dp))

                Text(
                    "Im EpiMediaHub-Dashboard: Kunde öffnen → Gerät per Code verbinden → diesen 8-stelligen Code eingeben.",
                    color = Color.White.copy(.62f),
                    fontSize = if (isTv) 13.sp else 12.sp,
                    textAlign = TextAlign.Center,
                    lineHeight = if (isTv) 18.sp else 17.sp
                )

                Spacer(Modifier.height(18.dp))

                Button(
                    onClick = {
                        SetupCodeProvisioning.clearPairing(context.applicationContext)
                        ticket = null
                        startPairing()
                    },
                    enabled = !busy,
                    colors = ButtonDefaults.buttonColors(containerColor = accent),
                    shape = RoundedCornerShape(12.dp)
                ) {
                    Text(
                        if (busy) "WIRD ERZEUGT …" else "NEUEN CODE ERZEUGEN",
                        color = Color.Black,
                        fontWeight = FontWeight.Black
                    )
                }

                TextButton(onClick = { showLegacyCode = true }, enabled = !busy) {
                    Text("12-stelligen Einrichtungscode verwenden", color = Color.White.copy(.78f))
                }

                Text(
                    if (isTv) "ANDROID TV · 0.7.8" else "ANDROID MOBILE · 0.7.8",
                    color = Color.White.copy(.36f),
                    fontSize = 10.sp,
                    modifier = Modifier.padding(top = 8.dp)
                )
            }
        }
    }

    if (showLegacyCode) {
        V051DashboardConnectDialog(
            onDismiss = { showLegacyCode = false },
            onProvisioned = {
                showLegacyCode = false
                vm.refreshProfiles()
                onConnected()
            }
        )
    }
}
