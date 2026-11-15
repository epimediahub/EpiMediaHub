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

fun color(hex: String) = runCatching { Color(AColor.parseColor(hex)) }
    .getOrDefault(Color(0xFF28A7F2))

@Composable
fun ThemeBackdrop(
    repo: ThemeRepository,
    theme: ThemeInfo?,
    themeId: String,
    content: @Composable BoxScope.() -> Unit
) {
    key(themeId) {
        val accent = remember(themeId) { color(theme?.accent ?: "#28A7F2") }
        val bg = remember(themeId) { repo.backgroundRes(themeId) }
        val center = remember(themeId) {
            repo.centerMarkRes(themeId).takeIf { it != 0 } ?: repo.markRes(themeId)
        }
        val banner = remember(themeId) {
            repo.bannerMarkRes(themeId).takeIf { it != 0 } ?: repo.markRes(themeId)
        }

        Box(Modifier.fillMaxSize().background(Color(0xFF05080D))) {
            if (bg != 0) {
                Image(
                    painterResource(bg),
                    null,
                    Modifier.fillMaxSize().graphicsLayer { alpha = .30f },
                    contentScale = ContentScale.Crop
                )
            }

            Box(
                Modifier.fillMaxSize().background(
                    Brush.verticalGradient(
                        listOf(
                            Color(0xC904080D),
                            Color(0xE9080D14),
                            Color(0xFA05080D)
                        )
                    )
                )
            )

            Box(
                Modifier.fillMaxSize().background(
                    Brush.radialGradient(
                        listOf(accent.copy(.10f), Color.Transparent),
                        radius = 950f
                    )
                )
            )

            if (center != 0) {
                Image(
                    painterResource(center),
                    null,
                    Modifier.align(Alignment.CenterEnd)
                        .fillMaxHeight(.76f)
                        .fillMaxWidth(.45f)
                        .graphicsLayer { alpha = .075f },
                    contentScale = ContentScale.Fit
                )
            }

            if (banner != 0) {
                Image(
                    painterResource(banner),
                    null,
                    Modifier.align(Alignment.TopEnd)
                        .fillMaxWidth(.32f)
                        .heightIn(max = 150.dp)
                        .graphicsLayer { alpha = .035f },
                    contentScale = ContentScale.Fit
                )
            }

            content()
        }
    }
}

@Composable
fun GlassPanel(
    modifier: Modifier = Modifier,
    content: @Composable BoxScope.() -> Unit
) {
    val shape = RoundedCornerShape(20.dp)
    Box(
        modifier
            .clip(shape)
            .background(
                Brush.linearGradient(
                    listOf(Color(0xEE111821), Color(0xEA0A1017))
                )
            )
            .border(1.dp, Color.White.copy(.085f), shape),
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
        targetValue = if (focused) 1.035f else 1f,
        animationSpec = spring(
            dampingRatio = Spring.DampingRatioNoBouncy,
            stiffness = Spring.StiffnessMediumLow
        ),
        label = "focusScale"
    )
    val shape = RoundedCornerShape(18.dp)

    Box(
        modifier
            .heightIn(min = 100.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 24.dp else 2.dp, shape)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(
                Brush.linearGradient(
                    if (focused) {
                        listOf(Color(0xF2232C37), Color(0xF20D141C))
                    } else {
                        listOf(Color(0xE9141B24), Color(0xE70A1017))
                    }
                )
            )
            .border(
                if (focused) 3.dp else 1.dp,
                if (focused) Color.White else Color.White.copy(.09f),
                shape
            )
            .clickable(onClick = onClick)
    ) {
        Box(
            Modifier.align(Alignment.CenterStart)
                .fillMaxHeight()
                .width(if (focused) 7.dp else 3.dp)
                .background(if (focused) accent else accent.copy(.50f))
        )

        Row(
            Modifier.fillMaxSize().padding(horizontal = 20.dp, vertical = 15.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (imageRes != 0) {
                Box(
                    Modifier.size(58.dp)
                        .clip(RoundedCornerShape(15.dp))
                        .background(Color.White.copy(if (focused) .085f else .045f)),
                    contentAlignment = Alignment.Center
                ) {
                    Image(
                        painterResource(imageRes),
                        null,
                        Modifier.size(42.dp)
                            .graphicsLayer { alpha = if (focused) 1f else .82f }
                    )
                }
                Spacer(Modifier.width(16.dp))
            }

            Column(Modifier.weight(1f)) {
                Text(
                    title,
                    color = Color.White,
                    fontSize = 18.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 2
                )
                if (subtitle.isNotBlank()) {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        subtitle,
                        color = Color.White.copy(if (focused) .72f else .55f),
                        fontSize = 12.sp,
                        maxLines = 2
                    )
                }
            }
        }
    }
}

@Composable
fun EpiTopBar(
    title: String,
    brandRes: Int,
    onBack: (() -> Unit)? = null,
    actions: @Composable RowScope.() -> Unit = {}
) {
    Surface(
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 9.dp),
        color = Color(0xE90A1017),
        contentColor = Color.White,
        shape = RoundedCornerShape(18.dp),
        tonalElevation = 0.dp,
        shadowElevation = 3.dp,
        border = androidx.compose.foundation.BorderStroke(1.dp, Color.White.copy(.07f))
    ) {
        Row(
            Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (onBack != null) {
                TextButton(onClick = onBack, shape = RoundedCornerShape(11.dp)) {
                    Text("‹  Zurück", color = Color.White.copy(.88f))
                }
            }
            Image(
                painterResource(brandRes),
                null,
                Modifier.width(136.dp).height(42.dp),
                contentScale = ContentScale.Fit
            )
            Spacer(Modifier.weight(1f))
            Text(
                title,
                color = Color.White,
                fontSize = 20.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1
            )
            Spacer(Modifier.width(12.dp))
            actions()
        }
    }
}
