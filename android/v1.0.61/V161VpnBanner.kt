package de.epimediahub.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.*
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.vpn.V134VpnSession
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.withContext

/** Read only the verified session state; never initiate a route or an exit probe. */
@Composable
internal fun V161VpnBanner(playlistId: String?) {
    val context = LocalContext.current.applicationContext
    var active by remember(playlistId) { mutableStateOf(false) }
    LaunchedEffect(context, playlistId) {
        if (playlistId == null) return@LaunchedEffect
        while (true) {
            active = withContext(Dispatchers.IO) {
                runCatching { V134VpnSession.verifiedFinlandActive(context, playlistId) }
                    .getOrDefault(false)
            }
            delay(750L)
        }
    }
    val foreground = if (active) Color(0xFF80E8B0) else Color(0xFF9299A4)
    val label = if (active) "Aktiv" else "Inaktiv"
    Surface(color = foreground.copy(alpha = .10f), shape = MaterialTheme.shapes.small,
        modifier = Modifier.semantics(mergeDescendants = true) {
            contentDescription = "VPN Finnland $label"
        }) {
        Row(Modifier.padding(horizontal = 8.dp, vertical = 4.dp),
            verticalAlignment = Alignment.CenterVertically,
            horizontalArrangement = Arrangement.spacedBy(5.dp)) {
            Text("VPN", color = foreground, fontWeight = FontWeight.Bold, fontSize = 11.sp)
            // A drawn Nordic cross works on TV firmware without country-flag emoji fonts.
            Canvas(Modifier.width(22.dp).height(13.dp)) {
                drawRect(if (active) Color.White else Color(0xFF878D96))
                val cross = if (active) Color(0xFF003580) else Color(0xFF5E6570)
                drawRect(cross, Offset(size.width * .29f, 0f),
                    Size(size.width * .18f, size.height))
                drawRect(cross, Offset(0f, size.height * .37f),
                    Size(size.width, size.height * .26f))
            }
            Text(label, color = foreground, fontWeight = FontWeight.Bold, fontSize = 11.sp)
        }
    }
}
