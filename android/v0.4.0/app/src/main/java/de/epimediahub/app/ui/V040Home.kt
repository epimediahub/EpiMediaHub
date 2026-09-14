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
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
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
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.ParityMediathekHome
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.model.MediaKind

@Composable
fun V040HomeScreen(vm: MainViewModel, isTv: Boolean, accent: Color) {
    val u by vm.ui.collectAsState()
    val columns = if (isTv) 3 else 2
    val markRes = remember(u.themeId) { vm.themeRepo().markRes(u.themeId) }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            u.active?.name ?: "EpiMediaHub",
            R.drawable.brand_header,
            actions = {
                Text(if (isTv) "ANDROID TV · 0.4.0" else "MOBILE · 0.4.0", color = Color.White.copy(.58f), fontWeight = FontWeight.SemiBold)
            }
        )
        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
            LazyVerticalGrid(
                columns = GridCells.Fixed(columns),
                modifier = Modifier.fillMaxWidth(if (isTv) .92f else .97f).padding(horizontal = 18.dp, vertical = 14.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                item { V040HomeTile("LIVE TV", "Sender · Voll-EPG · Catch-up", R.drawable.icon_live, markRes, 0, accent, isTv) { vm.openLibrary(MediaKind.LIVE) } }
                item { V040HomeTile("FILME", "VOD · Details · Resume", R.drawable.icon_movies, markRes, 1, accent, isTv) { vm.openLibrary(MediaKind.MOVIE) } }
                item { V040HomeTile("SERIEN", "Staffeln · Episoden · Resume", R.drawable.icon_series, markRes, 2, accent, isTv) { vm.openLibrary(MediaKind.SERIES) } }
                item { V040HomeTile("MEDIATHEK", "Länder · Sender · Suche", R.drawable.icon_mediathek, markRes, 3, accent, isTv) { vm.navigate(ParityMediathekHome) } }
                item { V040HomeTile("PLAYLISTS", if (u.playlists.size > 1) "${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen", R.drawable.icon_playlist, markRes, 4, accent, isTv) { vm.navigate(Screen.Playlists) } }
                item { V040HomeTile("EINSTELLUNGEN", "Design · QR-Websetup · Update", R.drawable.icon_settings, markRes, 5, accent, isTv) { vm.navigate(Screen.Settings) } }
            }
        }
    }
}

@Composable
private fun V040HomeTile(
    title: String,
    subtitle: String,
    iconRes: Int,
    markRes: Int,
    tileIndex: Int,
    accent: Color,
    isTv: Boolean,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        targetValue = if (focused) 1.045f else 1f,
        animationSpec = spring(dampingRatio = Spring.DampingRatioMediumBouncy, stiffness = Spring.StiffnessMediumLow),
        label = "v040HomeTileScale"
    )
    val shape = RoundedCornerShape(if (isTv) 25.dp else 21.dp)
    val markAlignment = when (tileIndex % 4) {
        0 -> Alignment.TopStart
        1 -> Alignment.TopEnd
        2 -> Alignment.BottomStart
        else -> Alignment.BottomEnd
    }
    Box(
        Modifier
            .heightIn(min = if (isTv) 150.dp else 142.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 22.dp else 9.dp, shape)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(
                Brush.linearGradient(
                    if (focused) listOf(accent.copy(alpha = .34f), Color(0xEC0B1522), Color(0xF20A1019))
                    else listOf(Color(0xD91A2A3B), Color(0xE90C1622), Color(0xF20A1018))
                )
            )
            .border(if (focused) 2.dp else 1.dp, if (focused) accent.copy(.95f) else Color.White.copy(.12f), shape)
            .clickable(onClick = onClick)
    ) {
        if (markRes != 0) {
            Image(
                painter = painterResource(markRes),
                contentDescription = null,
                modifier = Modifier.fillMaxSize().padding(if (isTv) 3.dp else 1.dp).alpha(if (focused) .28f else .20f),
                contentScale = ContentScale.Crop,
                alignment = markAlignment
            )
        }
        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color(0x25000000), Color(0xB8000000)))))
        Column(Modifier.fillMaxSize().padding(horizontal = 18.dp, vertical = 16.dp), verticalArrangement = Arrangement.SpaceBetween) {
            Box(
                Modifier.size(if (isTv) 48.dp else 44.dp).clip(RoundedCornerShape(15.dp)).background(Color.Black.copy(.24f)).border(1.dp, Color.White.copy(.10f), RoundedCornerShape(15.dp)),
                contentAlignment = Alignment.Center
            ) {
                Image(painterResource(iconRes), null, Modifier.size(if (isTv) 31.dp else 28.dp), contentScale = ContentScale.Fit)
            }
            Column {
                Box(Modifier.width(if (focused) 56.dp else 34.dp).height(3.dp).background(accent, RoundedCornerShape(50.dp)))
                Spacer(Modifier.height(8.dp))
                Text(title, color = Color.White, fontSize = if (isTv) 20.sp else 18.sp, fontWeight = FontWeight.Black, maxLines = 1)
                Spacer(Modifier.height(3.dp))
                Text(subtitle, color = Color.White.copy(.66f), fontSize = 12.sp, fontWeight = FontWeight.Medium, maxLines = 1)
            }
        }
    }
}
