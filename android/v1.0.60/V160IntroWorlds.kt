package de.epimediahub.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.foundation.Canvas
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import kotlin.math.sin

/**
 * A lightweight, generic visual story about the built-in features.
 * No skins, streaming preview, third-party assets, decoder or network activity.
 * Timeline is deterministic and synced to the intro sound.
 */
@Composable
internal fun V160IntroWorlds(elapsedMs: Long, accent: Color, unit: Float) {
    val mediaOne = V121IntroTimeline.envelope(elapsedMs, 1600, 480, 3950, 420)
    val mediaTwo = V121IntroTimeline.envelope(elapsedMs, 3830, 400, 5930, 370)
    val vpn = V121IntroTimeline.envelope(elapsedMs, 5750, 420, 7730, 480)
    val converge = V121IntroTimeline.envelope(elapsedMs, 7240, 380, 8960, 520)

    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        if (mediaOne > 0f) {
            V160MediaRow(
                listOf("LIVE TV" to "Sender", "FILME" to "Kino", "SERIEN" to "Episoden"),
                accent, unit,
                Modifier.graphicsLayer {
                    alpha = mediaOne
                    translationX = (1f - mediaOne) * -36f * unit * density
                    rotationY = 7f * (1f - mediaOne)
                }
            )
        }
        if (mediaTwo > 0f) {
            V160MediaRow(
                listOf("RADIO" to "Weltweit", "SMARTTUBE" to "Videos", "EPISCENE" to "Intro überspringen"),
                accent, unit,
                Modifier.graphicsLayer {
                    alpha = mediaTwo
                    translationX = (1f - mediaTwo) * 34f * unit * density
                    rotationY = -7f * (1f - mediaTwo)
                }
            )
        }
        if (vpn > 0f) {
            Canvas(Modifier.fillMaxSize().graphicsLayer { alpha = vpn }) {
                val c = Offset(size.width / 2f, size.height / 2f)
                val v = minOf(size.width / 960f, size.height / 540f)
                val width = 190f * v
                val height = 200f * v
                for (index in -3..3) {
                    val y = c.y + index * 45f * v
                    val flow = ((elapsedMs - 5750L) * .17f * v) % (250f * v)
                    drawLine(
                        color = accent.copy(alpha = .10f + vpn * .27f),
                        start = Offset(0f, y + flow * .08f),
                        end = Offset(size.width, y - flow * .08f),
                        strokeWidth = (1.1f + index.mod(2)) * v
                    )
                }
                val shield = Path().apply {
                    moveTo(c.x, c.y - height * .60f)
                    lineTo(c.x + width * .54f, c.y - height * .32f)
                    lineTo(c.x + width * .47f, c.y + height * .28f)
                    lineTo(c.x, c.y + height * .65f)
                    lineTo(c.x - width * .47f, c.y + height * .28f)
                    lineTo(c.x - width * .54f, c.y - height * .32f)
                    close()
                }
                drawPath(shield, color = accent.copy(alpha = vpn * .82f), style = Stroke(width = 3f * v))
                drawCircle(color = accent.copy(alpha = vpn * .07f), radius = 125f * v, center = c)
                val packetProgress = ((elapsedMs - 5750L) % 1500L) / 1500f
                repeat(5) { i ->
                    val x = size.width * packetProgress + i * 95f * v
                    val y = c.y + sin((elapsedMs / 500f + i)) * 49f * v
                    drawCircle(accent.copy(alpha = vpn * .25f), radius = 4f * v, center = Offset(x % size.width, y))
                }
            }
            Column(
                Modifier.graphicsLayer { alpha = vpn },
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.spacedBy((5f * unit).dp)
            ) {
                Text("VPN", color = Color.White, fontSize = (38f * unit).sp, fontWeight = FontWeight.Bold)
                Text("VERBINDUNG SCHÜTZEN", color = Color(0xFFBFD6E9), fontSize = (12f * unit).sp,
                    letterSpacing = (2f * unit).sp)
            }
        }
        if (converge > 0f) {
            Canvas(Modifier.fillMaxSize().graphicsLayer { alpha = converge }) {
                val c = Offset(size.width / 2f, size.height / 2f)
                val e = V121IntroTimeline.ease((elapsedMs - 7240L) / 1200f)
                val radius = size.width * (.53f - .39f * e)
                repeat(18) { i ->
                    val angle = (i * 20f + elapsedMs * .009f) * (Math.PI / 180.0)
                    val x = c.x + kotlin.math.cos(angle).toFloat() * radius
                    val y = c.y + kotlin.math.sin(angle).toFloat() * radius * .54f
                    drawLine(
                        accent.copy(alpha = .08f + .20f * converge),
                        start = Offset(x, y),
                        end = c,
                        strokeWidth = (1.5f * unit) * density
                    )
                }
            }
        }
    }
}

@Composable
private fun V160MediaRow(items: List<Pair<String, String>>, accent: Color, unit: Float, modifier: Modifier) {
    Row(
        modifier = modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.spacedBy((14f * unit).dp, Alignment.CenterHorizontally),
        verticalAlignment = Alignment.CenterVertically
    ) {
        items.forEachIndexed { index, item ->
            val shape = RoundedCornerShape((13f * unit).dp)
            Column(
                modifier = Modifier.width((227f * unit).dp).height((155f * unit).dp)
                    .background(
                        Brush.linearGradient(
                            listOf(Color(0xFF16283E), if (index % 2 == 0) Color(0xFF182A45) else Color(0xFF102034))
                        ),
                        shape
                    )
                    .border((1f * unit).dp, accent.copy(alpha = .38f), shape)
                    .padding((17f * unit).dp),
                verticalArrangement = Arrangement.SpaceBetween
            ) {
                Text("●  " + item.first, color = Color.White, fontSize = (17f * unit).sp,
                    fontWeight = FontWeight.Bold, maxLines = 1)
                Box(Modifier.fillMaxWidth().height((32f * unit).dp)
                    .background(accent.copy(alpha = .17f), RoundedCornerShape((5f * unit).dp)),
                    contentAlignment = Alignment.CenterStart
                ) {
                    Text(item.second, color = Color(0xFFD8E8F6), fontSize = (12f * unit).sp,
                        modifier = Modifier.padding(horizontal = (10f * unit).dp),
                        textAlign = TextAlign.Start)
                }
            }
        }
    }
}
