package de.epimediahub.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material.icons.filled.LiveTv
import androidx.compose.material.icons.filled.Movie
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Tv
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind

@Composable
fun CategoryListRow(title: String, accent: Color, modifier: Modifier = Modifier, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(14.dp)
    Surface(
        modifier = modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = if (focused) Color(0xFF17283A) else Color(0xF20A111B),
        contentColor = Color.White,
        shape = shape,
        border = androidx.compose.foundation.BorderStroke(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.08f)),
        shadowElevation = if (focused) 6.dp else 0.dp
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 18.dp, vertical = 14.dp), verticalAlignment = Alignment.CenterVertically) {
            Box(Modifier.size(8.dp).background(accent, RoundedCornerShape(99.dp)))
            Spacer(Modifier.width(13.dp))
            Text(title, fontSize = 17.sp, fontWeight = FontWeight.Bold, modifier = Modifier.weight(1f), maxLines = 2)
            Icon(Icons.Default.ChevronRight, null, tint = Color.White.copy(.55f))
        }
    }
}

@Composable
fun LiveChannelRow(media: MediaEntry, nowText: String, accent: Color, modifier: Modifier = Modifier, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(14.dp)
    Surface(
        modifier = modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = if (focused) Color(0xFF17283A) else Color(0xF50D131C),
        contentColor = Color.White,
        shape = shape,
        border = androidx.compose.foundation.BorderStroke(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.06f)),
        shadowElevation = if (focused) 6.dp else 0.dp
    ) {
        Row(Modifier.fillMaxWidth().padding(horizontal = 13.dp, vertical = 9.dp), verticalAlignment = Alignment.CenterVertically) {
            Surface(shape = RoundedCornerShape(10.dp), color = Color.White.copy(.07f), modifier = Modifier.size(58.dp)) {
                if (media.image.isNotBlank()) AsyncImage(media.image, null, Modifier.fillMaxSize().padding(6.dp), contentScale = ContentScale.Fit)
                else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Icon(Icons.Default.LiveTv, null, tint = accent, modifier = Modifier.size(29.dp)) }
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(media.name, color = Color.White, fontSize = 18.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                Text(if (nowText.isNotBlank()) nowText else "Live TV", color = Color.White.copy(if (nowText.isNotBlank()) .62f else .42f), fontSize = 12.sp, maxLines = 1, modifier = Modifier.padding(top = 3.dp))
            }
            Icon(Icons.Default.PlayArrow, null, tint = if (focused) accent else Color.White.copy(.48f), modifier = Modifier.size(30.dp))
        }
    }
}

@Composable
fun MediaInfoRow(media: MediaEntry, loading: Boolean, accent: Color, isTv: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(16.dp)
    val posterWidth = if (isTv) 112.dp else 94.dp
    val posterHeight = if (isTv) 160.dp else 142.dp
    Surface(
        modifier = modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = if (focused) Color(0xFF17283A) else Color(0xF50D131C),
        contentColor = Color.White,
        shape = shape,
        border = androidx.compose.foundation.BorderStroke(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.07f)),
        shadowElevation = if (focused) 7.dp else 0.dp
    ) {
        Row(Modifier.fillMaxWidth().padding(11.dp), verticalAlignment = Alignment.Top) {
            Surface(shape = RoundedCornerShape(12.dp), color = Color.White.copy(.07f), modifier = Modifier.width(posterWidth).height(posterHeight)) {
                if (media.image.isNotBlank()) AsyncImage(media.image, null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) { Icon(if (media.kind == MediaKind.SERIES) Icons.Default.Tv else Icons.Default.Movie, null, tint = accent, modifier = Modifier.size(40.dp)) }
            }
            Spacer(Modifier.width(15.dp))
            Column(Modifier.weight(1f).heightIn(min = posterHeight).padding(vertical = 2.dp)) {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    Text(media.name, fontSize = if (isTv) 20.sp else 17.sp, fontWeight = FontWeight.ExtraBold, modifier = Modifier.weight(1f), maxLines = 2)
                    if (loading) CircularProgressIndicator(Modifier.size(17.dp), strokeWidth = 2.dp, color = accent)
                }
                val meta = buildList {
                    if (media.year.isNotBlank()) add(media.year)
                    if (media.duration.isNotBlank()) add(media.duration)
                    if (media.genre.isNotBlank()) add(media.genre)
                    if (media.rating.isNotBlank()) add("★ ${media.rating}")
                }.joinToString("  ·  ")
                if (meta.isNotBlank()) Text(meta, color = accent, fontSize = 12.sp, fontWeight = FontWeight.Bold, maxLines = 1, modifier = Modifier.padding(top = 5.dp))
                if (media.cast.isNotBlank()) Text("Schauspieler: ${media.cast}", color = Color.White.copy(.72f), fontSize = 12.sp, maxLines = 1, modifier = Modifier.padding(top = 6.dp))
                if (media.plot.isNotBlank()) Text(media.plot, color = Color.White.copy(.66f), fontSize = 12.sp, maxLines = if (isTv) 4 else 3, modifier = Modifier.padding(top = 7.dp))
                Spacer(Modifier.weight(1f))
                Text(if (media.kind == MediaKind.SERIES) "Öffnen" else "Abspielen", color = if (focused) accent else Color.White.copy(.52f), fontWeight = FontWeight.Bold, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
            }
        }
    }
}
