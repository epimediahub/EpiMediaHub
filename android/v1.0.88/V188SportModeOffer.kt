package de.epimediahub.app.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalConfiguration
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.window.Dialog
import androidx.compose.ui.window.DialogProperties
import kotlinx.coroutines.delay

/**
 * Matches EpiMediaHub dark player/Info-dialog theme. Never offers anything
 * without a known PTS-verified 50 fps alternative.
 * Important: the DECLINE button owns the initial Fire TV remote focus.
 */
@Composable
internal fun V187SportModeOffer(onYes: () -> Unit, onNo: () -> Unit) {
    val noFocus = remember { FocusRequester() }
    val television = LocalConfiguration.current.screenWidthDp >= 760
    Dialog(
        onDismissRequest = onNo,
        properties = DialogProperties(usePlatformDefaultWidth = false)
    ) {
        Surface(
            modifier = Modifier
                .fillMaxWidth(if (television) .72f else .95f)
                .widthIn(max = 650.dp)
                .testTag("sportmode-offer"),
            color = Color(0xFF101923),
            shape = RoundedCornerShape(14.dp),
            border = BorderStroke(1.dp, Color(0xFF397792))
        ) {
            Column(
                Modifier.padding(if (television) 24.dp else 16.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp)
            ) {
                Text(
                    "SPORTMODUS",
                    color = Color(0xFF72E8D3),
                    fontWeight = FontWeight.Bold,
                    fontSize = 12.sp,
                    letterSpacing = 2.sp
                )
                Text(
                    "50 fps verfügbar",
                    color = Color.White,
                    fontWeight = FontWeight.Bold,
                    fontSize = if (television) 24.sp else 20.sp
                )
                Text(
                    "Dieser Sender wird mit 25 fps wiedergegeben. " +
                        "Eine flüssigere 50-fps-Variante wurde bereits erkannt – " +
                        "auch über andere Kategorien hinweg. Möchtest du wechseln?",
                    color = Color(0xFFD1DEE9),
                    fontSize = if (television) 17.sp else 14.sp
                )
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(12.dp)
                ) {
                    TextButton(
                        onClick = onNo,
                        modifier = Modifier
                            .weight(1f)
                            .focusRequester(noFocus)
                            .v114FocusRing()
                            .testTag("sportmode-decline")
                    ) {
                        Text("Nein · Sender behalten", color = Color.White)
                    }
                    Button(
                        onClick = onYes,
                        modifier = Modifier.weight(1f)
                            .v114FocusRing()
                            .testTag("sportmode-confirm"),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = Color(0xFF397792),
                            contentColor = Color.White
                        )
                    ) {
                        Text("Ja · 50 fps nutzen")
                    }
                }
            }
        }
    }
    LaunchedEffect(Unit) {
        delay(100L)
        runCatching { noFocus.requestFocus() }
    }
}
