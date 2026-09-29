package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.R

/**
 * Stable in-app host for the SmartTube integration.
 *
 * v1.0.0 intentionally starts with a native EpiMediaHub shell instead of
 * launching another APK. The upstream SmartTube core will be connected behind
 * this surface while the rest of EpiMediaHub stays isolated.
 */
@Composable
fun V100SmartTubeShell(
    accent: Color,
    isTv: Boolean,
    onBack: () -> Unit
) {
    BackHandler(onBack = onBack)
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("SMARTTUBE", R.drawable.brand_header, onBack)
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    listOf(Color(0xFF090D13), Color(0xFF05070B))
                )
            ),
            contentAlignment = Alignment.Center
        ) {
            Surface(
                modifier = Modifier
                    .fillMaxWidth(if (isTv) .62f else .88f)
                    .wrapContentHeight(),
                color = Color(0xDC101720),
                shape = RoundedCornerShape(if (isTv) 22.dp else 16.dp),
                border = BorderStroke(1.dp, Color.White.copy(.14f))
            ) {
                Column(
                    Modifier.padding(if (isTv) 34.dp else 22.dp),
                    horizontalAlignment = Alignment.CenterHorizontally
                ) {
                    Text(
                        "SMARTTUBE",
                        color = Color.White,
                        fontSize = if (isTv) 34.sp else 24.sp,
                        fontWeight = FontWeight.Black
                    )
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "Interner EpiMediaHub-Bereich",
                        color = accent,
                        fontSize = if (isTv) 16.sp else 13.sp,
                        fontWeight = FontWeight.Bold
                    )
                    Spacer(Modifier.height(14.dp))
                    Text(
                        "Der Host ist vorbereitet. Die SmartTube-Kernmodule werden auf dem 1.0.0-Entwicklungszweig eingebunden, ohne eine zweite App zu starten.",
                        color = Color.White.copy(.72f),
                        fontSize = if (isTv) 14.sp else 12.sp,
                        lineHeight = if (isTv) 20.sp else 17.sp
                    )
                }
            }
        }
    }
}
