package de.epimediahub.app.ui

import android.graphics.Color as AColor
import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.data.ThemeRepository
import de.epimediahub.app.model.ThemeInfo

fun color(hex: String) = runCatching { Color(AColor.parseColor(hex)) }.getOrDefault(Color(0xFF28A7F2))

@Composable
fun ThemeBackdrop(repo: ThemeRepository, theme: ThemeInfo?, themeId: String, content: @Composable BoxScope.() -> Unit) {
    val bg = repo.backgroundRes(themeId)
    Box(Modifier.fillMaxSize().background(Color(0xFF05080E))) {
        if (bg != 0) Image(painterResource(bg), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    listOf(Color.Black.copy(alpha = .18f), Color(0xFF07101D).copy(alpha = .42f), Color.Black.copy(alpha = .66f))
                )
            )
        )
        content()
    }
}

@Composable
fun GlassPanel(modifier: Modifier = Modifier, content: @Composable BoxScope.() -> Unit) {
    val shape = RoundedCornerShape(26.dp)
    Box(
        modifier
            .clip(shape)
            .background(
                Brush.linearGradient(
                    listOf(Color(0xE815263C), Color(0xDA091522))
                )
            )
            .border(1.dp, Color.White.copy(.11f), shape),
        content = content
    )
}

@Composable
fun FocusCard(
    title: String,
    subtitle: String = "",
    imageRes: Int = 0,
    imageUrl: String = "",
    accent: Color,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (focused) 1.045f else 1f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMediumLow),
        label = "focusScale"
    )
    val shape = RoundedCornerShape(24.dp)
    Box(
        modifier
            .heightIn(min = 104.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 18.dp else 7.dp, shape)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(
                Brush.linearGradient(
                    if (focused) listOf(accent.copy(.31f), Color(0xEE10243D))
                    else listOf(Color(0xE8172A43), Color(0xDE0B1727))
                )
            )
            .border(if (focused) 2.dp else 1.dp, if (focused) accent.copy(.9f) else Color.White.copy(.10f), shape)
            .clickable(onClick = onClick)
            .padding(horizontal = 18.dp, vertical = 16.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            if (imageRes != 0) {
                Box(
                    Modifier.size(62.dp).clip(RoundedCornerShape(19.dp))
                        .background(Color.White.copy(.065f)),
                    contentAlignment = Alignment.Center
                ) {
                    Image(painterResource(imageRes), null, Modifier.size(46.dp))
                }
                Spacer(Modifier.width(15.dp))
            }
            Column(Modifier.weight(1f)) {
                Text(title, color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.ExtraBold, maxLines = 2)
                if (subtitle.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(subtitle, color = Color.White.copy(.66f), fontSize = 13.sp, maxLines = 2)
                }
            }
        }
    }
}

@Composable
fun EpiTopBar(title: String, brandRes: Int, onBack: (() -> Unit)? = null, actions: @Composable RowScope.() -> Unit = {}) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 10.dp),
        color = Color(0xB5091422),
        contentColor = Color.White,
        shape = RoundedCornerShape(24.dp),
        tonalElevation = 0.dp,
        shadowElevation = 8.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(.08f))
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (onBack != null) {
                TextButton(onClick = onBack, shape = RoundedCornerShape(14.dp)) { Text("‹  Zurück", color = Color.White) }
            }
            Image(painterResource(brandRes), null, Modifier.width(142.dp).height(46.dp), contentScale = ContentScale.Fit)
            Spacer(Modifier.weight(1f))
            Text(title, color = Color.White, fontSize = 21.sp, fontWeight = FontWeight.ExtraBold, maxLines = 1)
            Spacer(Modifier.width(12.dp))
            actions()
        }
    }
}
