package de.epimediahub.app.ui

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
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.ParityMediathekHome
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.model.MediaKind

private data class V041Tile(
    val title: String,
    val subtitle: String,
    val icon: Int,
    val index: Int,
    val open: () -> Unit
)

@Composable
fun V041HomeScreen(vm: MainViewModel, isTv: Boolean, accent: Color) {
    val u by vm.ui.collectAsState()
    val markRes = remember(u.themeId) { vm.themeRepo().markRes(u.themeId) }
    val firstFocus = remember { FocusRequester() }

    val tiles = listOf(
        V041Tile("LIVE TV", "Sender · Voll-EPG · Catch-up", R.drawable.icon_live, 0) { vm.openLibrary(MediaKind.LIVE) },
        V041Tile("FILME", "VOD · Details · Resume", R.drawable.icon_movies, 1) { vm.openLibrary(MediaKind.MOVIE) },
        V041Tile("SERIEN", "Staffeln · Episoden · Resume", R.drawable.icon_series, 2) { vm.openLibrary(MediaKind.SERIES) },
        V041Tile("MEDIATHEK", "Länder · Sender · Suche", R.drawable.icon_mediathek, 3) { vm.navigate(ParityMediathekHome) },
        V041Tile("PLAYLISTS", if (u.playlists.size > 1) "${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen", R.drawable.icon_playlist, 4) { vm.navigate(Screen.Playlists) },
        V041Tile("EINSTELLUNGEN", "Design · QR-Websetup · Update", R.drawable.icon_settings, 5) { vm.navigate(Screen.Settings) }
    )

    LaunchedEffect(isTv) {
        if (isTv) runCatching { firstFocus.requestFocus() }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            u.active?.name ?: "EpiMediaHub",
            R.drawable.brand_header,
            actions = {
                Text(
                    if (isTv) "ANDROID TV · 0.4.1" else "MOBILE LANDSCAPE · 0.4.1",
                    color = Color.White.copy(.58f),
                    fontWeight = FontWeight.SemiBold
                )
            }
        )

        BoxWithConstraints(
            Modifier.fillMaxSize().padding(
                horizontal = if (isTv) 28.dp else 10.dp,
                vertical = if (isTv) 18.dp else 8.dp
            )
        ) {
            val compact = !isTv && maxHeight < 420.dp
            val gap = if (compact) 8.dp else if (isTv) 16.dp else 10.dp

            Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(gap)) {
                for (row in 0..1) {
                    Row(
                        Modifier.fillMaxWidth().weight(1f),
                        horizontalArrangement = Arrangement.spacedBy(gap)
                    ) {
                        for (col in 0..2) {
                            val position = row * 3 + col
                            val tile = tiles[position]
                            V041HomeTile(
                                title = tile.title,
                                subtitle = tile.subtitle,
                                iconRes = tile.icon,
                                markRes = markRes,
                                tileIndex = tile.index,
                                accent = accent,
                                isTv = isTv,
                                compact = compact,
                                modifier = Modifier
                                    .weight(1f)
                                    .fillMaxHeight()
                                    .then(if (position == 0) Modifier.focusRequester(firstFocus) else Modifier),
                                onClick = tile.open
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun V041HomeTile(
    title: String,
    subtitle: String,
    iconRes: Int,
    markRes: Int,
    tileIndex: Int,
    accent: Color,
    isTv: Boolean,
    compact: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (focused) 1.035f else 1f,
        animationSpec = spring(
            dampingRatio = Spring.DampingRatioMediumBouncy,
            stiffness = Spring.StiffnessMediumLow
        ),
        label = "v041TileScale"
    )
    val glow by animateFloatAsState(
        targetValue = if (focused) 1f else 0f,
        animationSpec = spring(stiffness = Spring.StiffnessMedium),
        label = "v041TileGlow"
    )
    val shape = RoundedCornerShape(if (isTv) 24.dp else 18.dp)
    val markAlignment = when (tileIndex % 4) {
        0 -> Alignment.TopStart
        1 -> Alignment.TopEnd
        2 -> Alignment.BottomStart
        else -> Alignment.BottomEnd
    }

    Box(
        modifier
            .graphicsLayer {
                scaleX = scale
                scaleY = scale
                translationY = if (focused) -3f else 0f
            }
            .shadow(if (focused) 22.dp else 7.dp, shape)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(
                Brush.linearGradient(
                    if (focused) listOf(accent.copy(alpha = .36f), Color(0xEC0B1522), Color(0xF20A1019))
                    else listOf(Color(0xD91A2A3B), Color(0xE90C1622), Color(0xF20A1018))
                )
            )
            .border(
                if (focused) 2.dp else 1.dp,
                if (focused) accent.copy(.85f + (.10f * glow)) else Color.White.copy(.12f),
                shape
            )
            .clickable(onClick = onClick)
    ) {
        if (markRes != 0) {
            Image(
                painter = painterResource(markRes),
                contentDescription = null,
                modifier = Modifier.fillMaxSize().padding(if (isTv) 2.dp else 0.dp).alpha(if (focused) .30f else .20f),
                contentScale = ContentScale.Crop,
                alignment = markAlignment
            )
        }

        Box(
            Modifier.fillMaxSize().background(
                Brush.verticalGradient(
                    listOf(Color.Transparent, Color(0x22000000), Color(0xB9000000))
                )
            )
        )

        Column(
            Modifier.fillMaxSize().padding(
                horizontal = if (compact) 12.dp else if (isTv) 18.dp else 14.dp,
                vertical = if (compact) 9.dp else if (isTv) 15.dp else 11.dp
            ),
            verticalArrangement = Arrangement.SpaceBetween
        ) {
            Box(
                Modifier
                    .size(if (compact) 34.dp else if (isTv) 48.dp else 39.dp)
                    .clip(RoundedCornerShape(if (compact) 10.dp else 14.dp))
                    .background(Color.Black.copy(.24f))
                    .border(1.dp, Color.White.copy(.10f), RoundedCornerShape(if (compact) 10.dp else 14.dp)),
                contentAlignment = Alignment.Center
            ) {
                Image(
                    painterResource(iconRes),
                    contentDescription = null,
                    modifier = Modifier.size(if (compact) 22.dp else if (isTv) 31.dp else 26.dp),
                    contentScale = ContentScale.Fit
                )
            }

            Column {
                Box(
                    Modifier
                        .width(if (focused) 52.dp else 30.dp)
                        .height(if (compact) 2.dp else 3.dp)
                        .background(accent, RoundedCornerShape(50.dp))
                )
                Spacer(Modifier.height(if (compact) 5.dp else 7.dp))
                Text(
                    title,
                    color = Color.White,
                    fontSize = if (compact) 14.sp else if (isTv) 20.sp else 16.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 1
                )
                if (!compact) {
                    Spacer(Modifier.height(2.dp))
                    Text(
                        subtitle,
                        color = Color.White.copy(.66f),
                        fontSize = if (isTv) 12.sp else 11.sp,
                        fontWeight = FontWeight.Medium,
                        maxLines = 1
                    )
                }
            }
        }
    }
}
