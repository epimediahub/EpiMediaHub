package de.epimediahub.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import de.epimediahub.app.R

internal enum class V097SkinWorld { NEUTRAL, STADIUM, GARAGE, PIT_GARAGE }

// The scene is a property of the category. Selecting another badge never
// changes the backdrop or applies a colour filter to the photograph.
internal fun V097SkinWorldFor(themeId: String, label: String, group: String): V097SkinWorld = when {
    group == "formula_1" || themeId.startsWith("f1_") -> V097SkinWorld.PIT_GARAGE
    group == "cars" -> V097SkinWorld.GARAGE
    group in setOf("england", "italy", "spain", "germany", "france", "netherlands",
        "turkey", "portugal", "scotland", "national_teams") -> V097SkinWorld.STADIUM
    else -> V097SkinWorld.NEUTRAL
}

internal fun V099WorldImageRes(world: V097SkinWorld): Int = when (world) {
    V097SkinWorld.STADIUM -> R.drawable.skin_world_stadium
    V097SkinWorld.GARAGE -> R.drawable.skin_world_garage
    V097SkinWorld.PIT_GARAGE -> R.drawable.skin_world_pit
    V097SkinWorld.NEUTRAL -> 0
}

// The old function is used by the menu. The accent belongs to focus and
// labels only; it is deliberately absent from the world image renderer.
internal fun V098EnvironmentAccent(themeId: String, label: String, fallback: Color): Color = fallback

internal fun V097PrivateDisplayLabel(label: String, privateTheme: Boolean): String {
    val clean = label.replace(Regex("(?i)\\s*[-·|/]?\\s*(family|privat|inspiriert)\\s*$"), "").trim()
    return if (privateTheme) "$clean · Privat" else clean
}

internal fun V097GroupDisplayLabel(label: String): String =
    label.replace(Regex("(?i)\\bfamily\\b"), "Privat")

@Composable
internal fun V097SkinEnvironment(world: V097SkinWorld, accent: Color) {
    val image = V099WorldImageRes(world)
    if (image == 0) {
        Box(Modifier.fillMaxSize().background(Color(0xFF06090D)))
        return
    }
    Box(Modifier.fillMaxSize()) {
        Image(
            painter = painterResource(image),
            contentDescription = null,
            modifier = Modifier.fillMaxSize(),
            contentScale = ContentScale.Crop
        )
        // A neutral veil supports legibility without repainting the scene.
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    listOf(Color(0x4803070B), Color(0x1403070B), Color(0x6203070B))
                )
            )
        )
    }
}
