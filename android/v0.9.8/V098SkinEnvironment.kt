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
import androidx.compose.ui.unit.sp
import kotlin.math.sin

internal enum class V097SkinWorld {
    NEUTRAL,
    STADIUM,
    GARAGE,
    PIT_GARAGE,
    LUXURY,
    STANDARD_DARK,
    STANDARD_BLUE,
    STANDARD_RED
}

internal fun V097SkinWorldFor(themeId: String, label: String, group: String): V097SkinWorld {
    val id = themeId.lowercase()
    val name = label.lowercase()
    val grp = group.lowercase()
    val all = "$id $name $grp"

    when (id) {
        "default" -> return V097SkinWorld.STANDARD_DARK
        "epi_blue" -> return V097SkinWorld.STANDARD_BLUE
        "epi_red" -> return V097SkinWorld.STANDARD_RED
    }

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

    val luxuryHints = listOf(
        "gucci","louis vuitton","louis_vuitton","lv","prada","chanel","dior","versace",
        "armani","burberry","balenciaga","givenchy","hermes","hermès","fendi","valentino",
        "saint laurent","ysl","cartier","rolex","tiffany","bulgari","bvlgari","moncler",
        "bottega","dolce","gabbana","tom ford","brunello","zegna"
    )
    if (luxuryHints.any { all.contains(it) }) return V097SkinWorld.LUXURY

    val carHints = listOf(
        "auto","cars","car_","automobil","ferrari","bmw","mercedes","audi","porsche",
        "lamborghini","maserati","alfa romeo","aston martin","bentley","bugatti",
        "mclaren","volvo","volkswagen","vw","ford","toyota","nissan","honda","lexus",
        "tesla","jaguar","land rover","range rover","rolls royce","rolls-royce"
    )
    if (carHints.any { all.contains(it) }) return V097SkinWorld.GARAGE

    return V097SkinWorld.NEUTRAL
}

internal fun V098EnvironmentAccent(themeId: String, label: String, fallback: Color): Color {
    val all = (themeId + " " + label).lowercase()
    return when {
        "tiffany" in all -> Color(0xFF81D8D0)
        "hermes" in all || "hermès" in all -> Color(0xFFF37021)
        "rolex" in all -> Color(0xFF006039)
        "cartier" in all -> Color(0xFF8B1538)
        "gucci" in all -> Color(0xFF0B5D3B)
        "louis vuitton" in all || "louis_vuitton" in all -> Color(0xFF9A6B3F)
        "burberry" in all -> Color(0xFFC8A97E)
        "dior" in all -> Color(0xFFB7A47A)
        "versace" in all -> Color(0xFFD4AF37)
        "chanel" in all || "prada" in all || "armani" in all -> Color(0xFFE7E7E7)
        else -> fallback
    }
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
            listOf(Color(0xFF04070B), accent.copy(alpha = .34f), Color(0xFF08110B))
        )
        V097SkinWorld.GARAGE -> Brush.verticalGradient(
            listOf(Color(0xFF030506), Color(0xFF10161D), accent.copy(alpha = .24f), Color(0xFF040608))
        )
        V097SkinWorld.PIT_GARAGE -> Brush.verticalGradient(
            listOf(Color(0xFF020305), Color(0xFF0A0D12), accent.copy(alpha = .28f), Color(0xFF030405))
        )
        V097SkinWorld.LUXURY -> Brush.radialGradient(
            listOf(accent.copy(alpha = .40f), Color(0xFF0A0A0D), Color(0xFF020203)),
            radius = 1250f
        )
        V097SkinWorld.STANDARD_BLUE -> Brush.linearGradient(
            listOf(Color(0xFF02111F), Color(0xFF06365B), Color(0xFF07111D))
        )
        V097SkinWorld.STANDARD_RED -> Brush.linearGradient(
            listOf(Color(0xFF190308), Color(0xFF5A0B18), Color(0xFF100308))
        )
        V097SkinWorld.STANDARD_DARK -> Brush.linearGradient(
            listOf(Color(0xFF020407), Color(0xFF17202B), Color(0xFF05070A))
        )
        else -> Brush.verticalGradient(listOf(Color.Black, Color.Black))
    }

    Box(Modifier.fillMaxSize().background(bg)) {
        Canvas(Modifier.fillMaxSize()) {
            val h = size.height
            val w = size.width
            when (world) {
                V097SkinWorld.STADIUM -> {
                    // Roof and floodlight banks.
                    drawRect(Color.Black.copy(alpha = .40f), Offset(0f, 0f), Size(w, h * .20f))
                    for (i in 0..9) {
                        val x = w * (.035f + i * .103f)
                        drawRect(Color.White.copy(alpha = .82f), Offset(x, h * .08f), Size(w * .045f, 5f))
                        drawCircle(accent.copy(alpha = .22f), 34f, Offset(x + w * .022f, h * .085f))
                    }

                    // Curved-look stands built from layered bands.
                    drawRect(Color(0xFF07090E).copy(alpha=.96f), Offset(0f, h*.20f), Size(w, h*.43f))
                    for (i in 0..7) {
                        val y = h * (.25f + i*.048f)
                        drawLine(accent.copy(alpha = if (i % 2 == 0) .24f else .12f), Offset(0f,y), Offset(w,y), strokeWidth=4f)
                    }
                    for (i in 0..72) {
                        val x = w * ((i % 24) / 23f)
                        val row = i / 24
                        val y = h * (.29f + row * .085f + sin(i.toFloat())*.006f)
                        drawCircle(if (i%4==0) accent.copy(.72f) else Color.White.copy(.28f), 2.8f, Offset(x,y))
                    }

                    // Pitch and wet reflections.
                    drawRect(Color(0xFF09291B).copy(alpha=.96f), Offset(0f,h*.63f), Size(w,h*.37f))
                    drawLine(Color.White.copy(.24f), Offset(w*.5f,h*.63f), Offset(w*.5f,h), 2f)
                    drawCircle(Color.White.copy(.22f), w*.065f, Offset(w*.5f,h*.82f))
                    for (i in 0..8) {
                        val x = w * (i/8f)
                        drawLine(accent.copy(.06f), Offset(w*.5f,h*.64f), Offset(x,h), 2f)
                    }
                    drawRect(accent.copy(.12f), Offset(0f,h*.56f), Size(w,h*.08f))
                }

                V097SkinWorld.GARAGE -> {
                    drawRect(Color.Black.copy(.38f), Offset(0f,0f), Size(w,h*.58f))
                    // Ceiling panels.
                    for (i in 0..7) {
                        val x = w*(.035f+i*.13f)
                        drawRect(Color.White.copy(.52f), Offset(x,h*.055f), Size(w*.078f,7f))
                        drawRect(accent.copy(.32f), Offset(x,h*.11f), Size(w*.078f,3f))
                    }
                    // Wall bays.
                    for (i in 0..5) {
                        val x=w*(i/5f)
                        drawRect(Color(0xFF0C1117).copy(.92f),Offset(x,h*.20f),Size(w*.16f,h*.37f))
                        drawLine(accent.copy(.18f),Offset(x,h*.20f),Offset(x,h*.57f),2f)
                    }
                    // Showroom floor.
                    drawRect(Color(0xFF07090C),Offset(0f,h*.58f),Size(w,h*.42f))
                    drawLine(accent.copy(.72f),Offset(0f,h*.66f),Offset(w,h*.66f),4f)
                    for(i in 0..10){
                        val x=w*(i/10f)
                        drawLine(Color.White.copy(.06f),Offset(w*.5f,h*.60f),Offset(x,h),1.6f)
                    }
                    // Vehicle silhouette, deliberately generic.
                    drawRoundRect(
                        Color.Black.copy(.58f),
                        topLeft=Offset(w*.30f,h*.47f),
                        size=Size(w*.40f,h*.16f),
                        cornerRadius=androidx.compose.ui.geometry.CornerRadius(80f,80f)
                    )
                    drawCircle(Color.Black.copy(.72f),w*.035f,Offset(w*.36f,h*.63f))
                    drawCircle(Color.Black.copy(.72f),w*.035f,Offset(w*.64f,h*.63f))
                }

                V097SkinWorld.PIT_GARAGE -> {
                    drawRect(Color.Black.copy(.42f),Offset(0f,0f),Size(w,h*.57f))
                    for(i in 0..8){
                        val x=w*(.02f+i*.12f)
                        drawRect(Color.White.copy(.62f),Offset(x,h*.045f),Size(w*.072f,8f))
                        drawRect(accent.copy(.44f),Offset(x,h*.095f),Size(w*.072f,4f))
                    }
                    // Monitor walls / tool cabinets.
                    for(i in 0..6){
                        val x=w*(.03f+i*.15f)
                        drawRect(Color(0xFF0B1016),Offset(x,h*.20f),Size(w*.11f,h*.28f))
                        drawRect(accent.copy(.20f),Offset(x+w*.012f,h*.225f),Size(w*.086f,h*.10f))
                    }
                    // Pit floor and lane markings.
                    drawRect(Color(0xFF050608),Offset(0f,h*.57f),Size(w,h*.43f))
                    drawLine(accent.copy(.86f),Offset(0f,h*.69f),Offset(w,h*.69f),5f)
                    drawLine(Color.White.copy(.42f),Offset(0f,h*.75f),Offset(w,h*.75f),2.5f)
                    for(i in 0..8){
                        val x=w*(i/8f)
                        drawLine(Color.White.copy(.055f),Offset(w*.5f,h*.58f),Offset(x,h),1.6f)
                    }
                    // Low F1 car silhouette.
                    drawRoundRect(
                        Color.Black.copy(.70f),
                        topLeft=Offset(w*.30f,h*.50f),
                        size=Size(w*.40f,h*.095f),
                        cornerRadius=androidx.compose.ui.geometry.CornerRadius(44f,44f)
                    )
                    drawRect(Color.Black.copy(.74f),Offset(w*.445f,h*.455f),Size(w*.11f,h*.08f))
                    drawCircle(Color.Black.copy(.80f),w*.025f,Offset(w*.34f,h*.60f))
                    drawCircle(Color.Black.copy(.80f),w*.025f,Offset(w*.66f,h*.60f))
                }

                V097SkinWorld.LUXURY -> {
                    // Boutique wall with large illuminated centerpiece.
                    drawRect(Color(0xFF070709).copy(.76f),Offset(0f,0f),Size(w,h))
                    for(i in 0..5){
                        val x=w*(i/5f)
                        drawLine(Color.White.copy(.055f),Offset(x,0f),Offset(x,h),1.3f)
                    }
                    drawRoundRect(
                        accent.copy(.15f),
                        topLeft=Offset(w*.20f,h*.16f),
                        size=Size(w*.60f,h*.58f),
                        cornerRadius=androidx.compose.ui.geometry.CornerRadius(46f,46f)
                    )
                    drawRoundRect(
                        Color.White.copy(.045f),
                        topLeft=Offset(w*.235f,h*.20f),
                        size=Size(w*.53f,h*.50f),
                        cornerRadius=androidx.compose.ui.geometry.CornerRadius(38f,38f)
                    )
                    // Warm floor and light lines.
                    drawRect(Color(0xFF080708),Offset(0f,h*.73f),Size(w,h*.27f))
                    drawLine(accent.copy(.74f),Offset(w*.12f,h*.76f),Offset(w*.88f,h*.76f),3.5f)
                    drawLine(Color.White.copy(.15f),Offset(w*.22f,h*.82f),Offset(w*.78f,h*.82f),2f)
                    drawCircle(accent.copy(.14f),w*.22f,Offset(w*.5f,h*.44f))
                }

                V097SkinWorld.STANDARD_BLUE,
                V097SkinWorld.STANDARD_RED,
                V097SkinWorld.STANDARD_DARK -> {
                    val localAccent = when(world){
                        V097SkinWorld.STANDARD_BLUE -> Color(0xFF21B8FF)
                        V097SkinWorld.STANDARD_RED -> Color(0xFFFF3B53)
                        else -> Color(0xFF8FA7BD)
                    }
                    // Broadcast/control-room environment.
                    drawRect(Color.Black.copy(.36f),Offset(0f,0f),Size(w,h))
                    for(i in 0..6){
                        val x=w*(.05f+i*.15f)
                        drawRect(localAccent.copy(.10f),Offset(x,h*.18f),Size(w*.105f,h*.30f))
                        drawRect(Color.White.copy(.06f),Offset(x+w*.01f,h*.21f),Size(w*.085f,h*.09f))
                    }
                    drawLine(localAccent.copy(.60f),Offset(0f,h*.56f),Offset(w,h*.56f),4f)
                    drawRect(Color(0xFF05080C),Offset(0f,h*.58f),Size(w,h*.42f))
                    for(i in 0..10){
                        val x=w*(i/10f)
                        drawLine(localAccent.copy(.055f),Offset(w*.5f,h*.59f),Offset(x,h),1.5f)
                    }
                    drawCircle(localAccent.copy(.17f),w*.25f,Offset(w*.5f,h*.36f))
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
        Text(
            mark,
            color = Color.White.copy(alpha = if (themeId.startsWith("national_")) .92f else .76f),
            fontSize = if (compact) 34.sp else 76.sp,
            fontWeight = FontWeight.Black
        )
    }
}
