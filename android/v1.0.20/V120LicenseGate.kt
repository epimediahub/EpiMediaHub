package de.epimediahub.app.ui

import android.content.Context
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.data.V120LicenseKind
import de.epimediahub.app.data.V120LicenseManager
import de.epimediahub.app.data.V120LicenseState
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

@Composable
fun v120RememberLicenseState(context: Context, refreshKey: Int): V120LicenseState {
    var state by remember(context) {
        mutableStateOf(V120LicenseManager.cached(context) ?: V120LicenseState(V120LicenseKind.CHECKING))
    }
    LaunchedEffect(context, refreshKey) {
        while (true) {
            state = withContext(Dispatchers.IO) { V120LicenseManager.check(context) }
            val delayMs = when (state.kind) {
                V120LicenseKind.TRIAL_ACTIVE -> {
                    val untilExpiryMs = ((state.remainingSeconds ?: 0L) + 1L) * 1000L
                    minOf(15L * 60L * 1000L, maxOf(5_000L, untilExpiryMs))
                }
                V120LicenseKind.ERROR -> 60_000L
                else -> 15L * 60L * 1000L
            }
            delay(delayMs)
        }
    }
    return state
}

@Composable
fun V120LicenseGate(
    state: V120LicenseState,
    accent: Color,
    isTv: Boolean,
    deviceId: String,
    onRetry: () -> Unit
) {
    val expired = state.kind == V120LicenseKind.TRIAL_EXPIRED
    Box(
        Modifier.fillMaxSize().background(
            Brush.verticalGradient(listOf(Color(0xFF06111C), Color(0xFF0B1E30), Color(0xFF05090F)))
        ),
        contentAlignment = Alignment.Center
    ) {
        Card(
            modifier = Modifier.fillMaxWidth(if (isTv) .62f else .92f).padding(12.dp),
            shape = RoundedCornerShape(if (isTv) 28.dp else 22.dp),
            colors = CardDefaults.cardColors(containerColor = Color(0xF20B1520)),
            border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(.55f))
        ) {
            Column(
                Modifier.fillMaxWidth().padding(if (isTv) 36.dp else 24.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    when (state.kind) {
                        V120LicenseKind.CHECKING -> "LIZENZ WIRD GEPRÜFT"
                        V120LicenseKind.TRIAL_EXPIRED -> "TESTPHASE BEENDET"
                        else -> "LIZENZPRÜFUNG"
                    },
                    color = accent, fontWeight = FontWeight.Black,
                    fontSize = if (isTv) 20.sp else 16.sp
                )
                Spacer(Modifier.height(18.dp))
                Text(
                    if (expired) "Deine 7-tägige Testphase ist beendet."
                    else state.message.ifBlank { "EpiMediaHub benötigt eine Verbindung zum Lizenzserver." },
                    color = Color.White, fontWeight = FontWeight.Bold,
                    fontSize = if (isTv) 26.sp else 20.sp, textAlign = TextAlign.Center
                )
                Spacer(Modifier.height(12.dp))
                Text(
                    if (expired) "Dauerhaft aktivieren für einmalig 10 € pro Gerät. Bitte wende dich an deinen Anbieter."
                    else "Bitte Internetverbindung prüfen und erneut versuchen.",
                    color = Color.White.copy(.72f), fontSize = if (isTv) 16.sp else 14.sp,
                    textAlign = TextAlign.Center, lineHeight = if (isTv) 23.sp else 20.sp
                )
                Spacer(Modifier.height(20.dp))
                Surface(color = Color.White.copy(.06f), shape = RoundedCornerShape(14.dp)) {
                    Text(
                        "Geräte-ID · " + deviceId.takeLast(12).uppercase(),
                        modifier = Modifier.padding(horizontal = 18.dp, vertical = 12.dp),
                        color = Color.White.copy(.82f), fontWeight = FontWeight.Bold
                    )
                }
                Spacer(Modifier.height(22.dp))
                Button(onClick = onRetry, colors = ButtonDefaults.buttonColors(containerColor = accent)) {
                    Text("STATUS ERNEUT PRÜFEN", color = Color.Black, fontWeight = FontWeight.Black)
                }
            }
        }
    }
}


@Composable
fun V120TrialBadge(
    state: V120LicenseState?,
    accent: Color,
    isTv: Boolean,
    modifier: Modifier = Modifier
) {
    if (state?.kind != V120LicenseKind.TRIAL_ACTIVE) return
    val days = state.remainingDays ?: return
    Surface(
        modifier = modifier,
        color = Color(0xE6111B26),
        shape = RoundedCornerShape(999.dp),
        border = androidx.compose.foundation.BorderStroke(1.dp, accent.copy(.55f))
    ) {
        Text(
            text = if (days == 1L) "TESTVERSION · NOCH 1 TAG" else "TESTVERSION · NOCH $days TAGE",
            modifier = Modifier.padding(
                horizontal = if (isTv) 16.dp else 11.dp,
                vertical = if (isTv) 8.dp else 6.dp
            ),
            color = Color.White.copy(.88f),
            fontSize = if (isTv) 13.sp else 10.sp,
            fontWeight = FontWeight.Bold
        )
    }
}
