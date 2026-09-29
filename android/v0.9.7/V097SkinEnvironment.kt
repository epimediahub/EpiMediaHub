package de.epimediahub.app.ui

import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

internal enum class V097SkinWorld { NEUTRAL, STADIUM, GARAGE, PIT_GARAGE }

internal fun V097SkinWorldFor(themeId: String, label: String, group: String): V097SkinWorld {
    val id = themeId.lowercase()
    val name = label.lowercase()
    val grp = group.lowercase()
    val all = "$id $name $grp"

    if (id.startsWith("f1_") || grp.contains("formula") || grp.contains("formel")) {
        return V097SkinWorld.PIT_GARAGE
    }
    if (id.startsWith("national_")) return V097SkinWorld.STADIUM

    val footballHints = listOf(
        "football","fussball","fußball","soccer","bundesliga","premier","laliga","la_liga",
        "serie_a","ligue","superlig","süper","champions","nationalmannschaft",
        "köln","koln","liverpool","juventus","galatasaray","fenerbah","besiktas","beşiktaş",
        "bayern","dortmund","schalke","leverkusen","frankfurt","stuttgart","hamburg",
        "madrid","barcelona","arsenal","chelsea","tottenham","united","city","inter",
        "milan","napoli","roma","lazio","paris","psg","marseille","benfica","porto","ajax"
    )
    if (footballHints.any { all.contains(it) }) return V097SkinWorld.STADIUM

    val carHints = listOf(
        "auto","cars","car_","automobil","ferrari","bmw","mercedes","audi","porsche",
        "lamborghini","maserati","alfa romeo","aston martin","bentley","bugatti",
        "mclaren","volvo","volkswagen","vw","ford","toyota","nissan","honda","lexus",
        "tesla","jaguar","land rover","range rover"
    )
    if (carHints.any { all.contains(it) }) return V097SkinWorld.GARAGE

    return V097SkinWorld.NEUTRAL
}

internal fun V097PrivateDisplayLabel(label: String, privateTheme: Boolean): String {
    var cleaned = label
        .replace(Regex("(?i)\\s*[-·|/]?\\s*family\\s*$"), "")
        .replace(Regex("(?i)\\bfamily\\b"), "Privat")
        .trim()
    if (privateTheme) {
        cleaned = cleaned.replace(Regex("(?i)\\s*[-·|/]?\\s*privat\\s*$"), "").trim()
        return "$cleaned · Privat"
    }
    return cleaned
}

internal fun V097GroupDisplayLabel(label: String): String =
    label.replace(Regex("(?i)\\bfamily\\b"), "Privat")

private fun V097FlagFor(themeId: String): String = when (themeId.lowercase()) {
    "national_de" -> "🇩🇪"
    "national_it" -> "🇮🇹"
    "national_fr" -> "🇫🇷"
    "national_es" -> "🇪🇸"
    "national_en" -> "🏴"
    "national_pt" -> "🇵🇹"
    "national_nl" -> "🇳🇱"
    "national_be" -> "🇧🇪"
    "national_hr" -> "🇭🇷"
    "national_ar" -> "🇦🇷"
    "national_br" -> "🇧🇷"
    "national_uy" -> "🇺🇾"
    "national_mx" -> "🇲🇽"
    "national_us" -> "🇺🇸"
    "national_ma" -> "🇲🇦"
    "national_tr" -> "🇹🇷"
    "national_jp" -> "🇯🇵"
    "national_kr" -> "🇰🇷"
    "national_ch" -> "🇨🇭"
    "national_dk" -> "🇩🇰"
    else -> ""
}

private fun V097Initials(themeId: String, label: String): String {
    val flag = V097FlagFor(themeId)
    if (flag.isNotBlank()) return flag
    return label.split(Regex("\\s+"))
        .filter { it.isNotBlank() }
        .take(3)
        .mapNotNull { it.firstOrNull()?.uppercaseChar()?.toString() }
        .joinToString("")
        .ifBlank { "EMH" }
}

@Composable
internal fun V097SkinEnvironment(world: V097SkinWorld, accent: Color) {
    if (world == V097SkinWorld.NEUTRAL) return
    val bg = when (world) {
        V097SkinWorld.STADIUM -> Brush.verticalGradient(
            listOf(Color(0xFF060A11), accent.copy(alpha = .24f), Color(0xFF07130D))
        )
        V097SkinWorld.GARAGE -> Brush.verticalGradient(
            listOf(Color(0xFF05070A), Color(0xFF111820), accent.copy(alpha = .18f), Color(0xFF05070A))
        )
        V097SkinWorld.PIT_GARAGE -> Brush.verticalGradient(
            listOf(Color(0xFF030509), Color(0xFF0A1017), accent.copy(alpha = .22f), Color(0xFF030407))
        )
        else -> Brush.verticalGradient(listOf(Color.Black, Color.Black))
    }

    Box(Modifier.fillMaxSize().background(bg)) {
        Canvas(Modifier.fillMaxSize()) {
            when (world) {
                V097SkinWorld.STADIUM -> {
                    val h = size.height
                    val w = size.width
                    drawRect(Color.Black.copy(alpha = .34f), Offset(0f, h * .27f), Size(w, h * .34f))
                    for (i in 0..6) {
                        val y = h * (.30f + i * .045f)
                        drawLine(accent.copy(alpha = .16f), Offset(0f, y), Offset(w, y), strokeWidth = 2f)
                    }
                    drawRect(Color(0xFF0A2517).copy(alpha = .88f), Offset(0f, h * .63f), Size(w, h * .37f))
                    drawLine(Color.White.copy(alpha = .24f), Offset(w * .5f, h * .63f), Offset(w * .5f, h), strokeWidth = 2f)
                    drawCircle(Color.White.copy(alpha = .20f), radius = w * .07f, center = Offset(w * .5f, h * .83f))
                    for (x in listOf(.07f,.11f,.15f,.85f,.89f,.93f)) {
                        drawCircle(Color.White.copy(alpha = .70f), radius = 6f, center = Offset(w * x, h * .18f))
                        drawCircle(accent.copy(alpha = .25f), radius = 24f, center = Offset(w * x, h * .18f))
                    }
                    drawRect(accent.copy(alpha = .11f), Offset(0f, h * .22f), Size(w, h * .05f))
                }
                V097SkinWorld.GARAGE -> {
                    val h = size.height
                    val w = size.width
                    drawRect(Color.Black.copy(alpha = .28f), Offset(0f, 0f), Size(w, h * .62f))
                    for (i in 0..5) {
                        val x = w * (.08f + i * .17f)
                        drawRect(Color.White.copy(alpha = .34f), Offset(x, h * .08f), Size(w * .09f, 7f))
                    }
                    drawRect(accent.copy(alpha = .12f), Offset(0f, h * .53f), Size(w, h * .12f))
                    drawRect(Color(0xFF080B0F).copy(alpha = .90f), Offset(0f, h * .65f), Size(w, h * .35f))
                    for (i in 0..8) {
                        val startX = w * (i / 8f)
                        drawLine(Color.White.copy(alpha = .07f), Offset(w * .5f, h * .65f), Offset(startX, h), strokeWidth = 1.5f)
                    }
                    drawLine(accent.copy(alpha = .48f), Offset(0f, h * .66f), Offset(w, h * .66f), strokeWidth = 3f)
                    drawRect(Color.Black.copy(alpha = .25f), Offset(0f, h * .20f), Size(w * .18f, h * .42f))
                    drawRect(Color.Black.copy(alpha = .25f), Offset(w * .82f, h * .20f), Size(w * .18f, h * .42f))
                }
                V097SkinWorld.PIT_GARAGE -> {
                    val h = size.height
                    val w = size.width
                    drawRect(Color.Black.copy(alpha = .36f), Offset(0f, 0f), Size(w, h * .60f))
                    for (i in 0..7) {
                        val x = w * (.035f + i * .135f)
                        drawRect(Color.White.copy(alpha = .52f), Offset(x, h * .055f), Size(w * .075f, 8f))
                        drawRect(accent.copy(alpha = .34f), Offset(x, h * .10f), Size(w * .075f, 4f))
                    }
                    drawRect(Color(0xFF070A0E), Offset(0f, h * .61f), Size(w, h * .39f))
                    drawLine(accent.copy(alpha = .75f), Offset(0f, h * .72f), Offset(w, h * .72f), strokeWidth = 5f)
                    drawLine(Color.White.copy(alpha = .32f), Offset(0f, h * .76f), Offset(w, h * .76f), strokeWidth = 2f)
                    for (i in 0..6) {
                        val x = w * (.08f + i * .145f)
                        drawRect(accent.copy(alpha = .13f), Offset(x, h * .22f), Size(w * .09f, h * .28f))
                    }
                    drawRect(Color.Black.copy(alpha = .30f), Offset(0f, h * .20f), Size(w * .16f, h * .40f))
                    drawRect(Color.Black.copy(alpha = .30f), Offset(w * .84f, h * .20f), Size(w * .16f, h * .40f))
                }
                else -> Unit
            }
        }
    }
}

@Composable
internal fun V097FallbackSkinMark(
    themeId: String,
    label: String,
    accent: Color,
    compact: Boolean = false
) {
    val mark = V097Initials(themeId, label)
    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
        Box(
            Modifier
                .fillMaxWidth(if (compact) .46f else .38f)
                .fillMaxHeight(if (compact) .80f else .62f)
                .background(Color.Black.copy(alpha = .18f)),
            contentAlignment = Alignment.Center
        ) {
            Text(
                mark,
                color = Color.White.copy(alpha = .80f),
                fontSize = if (compact) 38.sp else 82.sp,
                fontWeight = FontWeight.Black
            )
        }
    }
}
