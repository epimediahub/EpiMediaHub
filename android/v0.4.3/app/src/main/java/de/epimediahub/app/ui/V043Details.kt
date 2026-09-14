package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Favorite
import androidx.compose.material.icons.filled.FavoriteBorder
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.data.MediathekClient
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun V043MediaDetailScreen(vm: MainViewModel, item: MediaEntry, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val detail = u.details[item.resumeKey] ?: item
    val loading = u.detailLoading.contains(item.resumeKey)
    val markRes = remember(u.themeId) {
        vm.themeRepo().centerMarkRes(u.themeId).takeIf { it != 0 } ?: vm.themeRepo().markRes(u.themeId)
    }
    BackHandler { vm.back() }
    LaunchedEffect(item.resumeKey) { vm.ensureDetails(item) }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            if (detail.kind == MediaKind.SERIES) "SERIEN · DETAILS" else "FILME · DETAILS",
            R.drawable.brand_header,
            { vm.back() }
        )
        Box(Modifier.fillMaxSize().padding(horizontal = if (isTv) 52.dp else 12.dp, vertical = 8.dp)) {
            if (markRes != 0) {
                Image(
                    painterResource(markRes),
                    contentDescription = null,
                    modifier = Modifier.align(Alignment.CenterEnd).fillMaxHeight(.88f).fillMaxWidth(.48f).alpha(.10f),
                    contentScale = ContentScale.Fit
                )
            }
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(if (isTv) 28.dp else 14.dp)) {
                V043Poster(
                    image = detail.image,
                    title = detail.name,
                    accent = accent,
                    modifier = Modifier.width(if (isTv) 330.dp else 215.dp).fillMaxHeight()
                )

                LazyColumn(
                    Modifier.weight(1f).fillMaxHeight(),
                    contentPadding = PaddingValues(bottom = 26.dp)
                ) {
                    item {
                        Text(
                            detail.name,
                            color = Color.White,
                            fontSize = if (isTv) 34.sp else 24.sp,
                            lineHeight = if (isTv) 39.sp else 28.sp,
                            fontWeight = FontWeight.Black,
                            maxLines = 3,
                            overflow = TextOverflow.Ellipsis
                        )
                        Spacer(Modifier.height(10.dp))
                        V043MediaMeta(detail, accent, isTv)
                        if (loading) {
                            Row(Modifier.padding(top = 12.dp), verticalAlignment = Alignment.CenterVertically) {
                                CircularProgressIndicator(Modifier.size(18.dp), strokeWidth = 2.dp, color = accent)
                                Spacer(Modifier.width(8.dp))
                                Text("Weitere Informationen werden geladen …", color = Color.White.copy(.82f), fontSize = 13.sp)
                            }
                        }
                        if (detail.plot.isNotBlank()) {
                            Spacer(Modifier.height(if (isTv) 18.dp else 12.dp))
                            Text("INHALT", color = accent, fontSize = 13.sp, fontWeight = FontWeight.Black)
                            Spacer(Modifier.height(5.dp))
                            Text(
                                detail.plot,
                                color = Color.White.copy(.94f),
                                fontSize = if (isTv) 17.sp else 14.sp,
                                lineHeight = if (isTv) 24.sp else 20.sp
                            )
                        }
                        if (detail.cast.isNotBlank()) {
                            Spacer(Modifier.height(14.dp))
                            V043InfoLine("DARSTELLER", detail.cast, accent, isTv)
                        }
                        if (detail.director.isNotBlank()) {
                            Spacer(Modifier.height(10.dp))
                            V043InfoLine("REGIE", detail.director, accent, isTv)
                        }
                        Spacer(Modifier.height(if (isTv) 24.dp else 15.dp))
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Button(
                                onClick = {
                                    if (detail.kind == MediaKind.SERIES) vm.navigate(Screen.Episodes(detail)) else vm.play(detail)
                                },
                                colors = ButtonDefaults.buttonColors(containerColor = accent),
                                shape = RoundedCornerShape(13.dp),
                                modifier = Modifier.height(if (isTv) 54.dp else 46.dp)
                            ) {
                                Icon(if (detail.kind == MediaKind.SERIES) Icons.Default.List else Icons.Default.PlayArrow, null, tint = Color.Black)
                                Spacer(Modifier.width(8.dp))
                                Text(
                                    if (detail.kind == MediaKind.SERIES) "Staffeln & Episoden" else "Abspielen",
                                    color = Color.Black,
                                    fontWeight = FontWeight.Black,
                                    fontSize = if (isTv) 16.sp else 14.sp
                                )
                            }
                            val favorite = vm.isFavorite(detail)
                            OutlinedButton(
                                onClick = { vm.toggleFavorite(detail) },
                                shape = RoundedCornerShape(13.dp),
                                modifier = Modifier.height(if (isTv) 54.dp else 46.dp)
                            ) {
                                Icon(if (favorite) Icons.Default.Favorite else Icons.Default.FavoriteBorder, null, tint = if (favorite) accent else Color.White)
                                Spacer(Modifier.width(7.dp))
                                Text(if (favorite) "Favorit" else "Zu Favoriten", color = Color.White, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
fun V043MediathekDetailScreen(vm: MainViewModel, item: MediathekClient.Item, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val markRes = remember(u.themeId) {
        vm.themeRepo().centerMarkRes(u.themeId).takeIf { it != 0 } ?: vm.themeRepo().markRes(u.themeId)
    }
    var artwork by remember(item.id) { mutableStateOf(item.imageHint) }
    BackHandler { vm.back() }

    LaunchedEffect(item.id) {
        if (artwork.isBlank() && item.websiteUrl.isNotBlank()) {
            artwork = withContext(Dispatchers.IO) { MediathekClient.resolveArtwork(item) }
        }
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("MEDIATHEK · DETAILS", R.drawable.brand_header, { vm.back() }, actions = {
            Text(item.channel, color = accent, fontWeight = FontWeight.Black, fontSize = 14.sp)
        })
        Box(Modifier.fillMaxSize().padding(horizontal = if (isTv) 52.dp else 12.dp, vertical = 8.dp)) {
            if (markRes != 0) {
                Image(
                    painterResource(markRes),
                    contentDescription = null,
                    modifier = Modifier.align(Alignment.CenterEnd).fillMaxHeight(.88f).fillMaxWidth(.48f).alpha(.10f),
                    contentScale = ContentScale.Fit
                )
            }
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(if (isTv) 28.dp else 14.dp)) {
                Box(
                    Modifier.width(if (isTv) 410.dp else 245.dp).fillMaxHeight()
                        .clip(RoundedCornerShape(20.dp))
                        .background(Color(0xE80A1420))
                        .border(1.dp, Color.White.copy(.14f), RoundedCornerShape(20.dp))
                ) {
                    if (artwork.isNotBlank()) {
                        AsyncImage(
                            model = artwork,
                            contentDescription = item.media.name,
                            modifier = Modifier.fillMaxSize(),
                            contentScale = ContentScale.Crop
                        )
                        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Black.copy(.08f), Color.Black.copy(.68f)))))
                    } else {
                        V043SenderHero(item.channel, item.topic, accent)
                    }
                    Text(
                        item.channel.uppercase(),
                        color = Color.White,
                        fontSize = if (isTv) 16.sp else 12.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier.align(Alignment.TopStart).padding(14.dp)
                            .background(Color.Black.copy(.74f), RoundedCornerShape(9.dp)).padding(horizontal = 10.dp, vertical = 6.dp)
                    )
                }

                LazyColumn(Modifier.weight(1f).fillMaxHeight(), contentPadding = PaddingValues(bottom = 26.dp)) {
                    item {
                        if (item.topic.isNotBlank() && !item.media.name.contains(item.topic, true)) {
                            Text(item.topic, color = accent, fontSize = if (isTv) 17.sp else 14.sp, fontWeight = FontWeight.Black)
                            Spacer(Modifier.height(6.dp))
                        }
                        Text(
                            item.media.name,
                            color = Color.White,
                            fontSize = if (isTv) 34.sp else 24.sp,
                            lineHeight = if (isTv) 39.sp else 28.sp,
                            fontWeight = FontWeight.Black
                        )
                        Spacer(Modifier.height(9.dp))
                        Text(
                            v043MediathekMeta(item),
                            color = Color.White.copy(.88f),
                            fontSize = if (isTv) 15.sp else 13.sp,
                            fontWeight = FontWeight.SemiBold
                        )
                        if (item.description.isNotBlank()) {
                            Spacer(Modifier.height(if (isTv) 20.dp else 13.dp))
                            Text("SENDUNGSINFO", color = accent, fontSize = 13.sp, fontWeight = FontWeight.Black)
                            Spacer(Modifier.height(5.dp))
                            Text(
                                item.description,
                                color = Color.White.copy(.95f),
                                fontSize = if (isTv) 17.sp else 14.sp,
                                lineHeight = if (isTv) 24.sp else 20.sp
                            )
                        }
                        Spacer(Modifier.height(if (isTv) 24.dp else 15.dp))
                        Button(
                            onClick = { vm.play(item.media) },
                            colors = ButtonDefaults.buttonColors(containerColor = accent),
                            shape = RoundedCornerShape(13.dp),
                            modifier = Modifier.height(if (isTv) 54.dp else 46.dp)
                        ) {
                            Icon(Icons.Default.PlayArrow, null, tint = Color.Black)
                            Spacer(Modifier.width(8.dp))
                            Text("Abspielen", color = Color.Black, fontWeight = FontWeight.Black, fontSize = if (isTv) 16.sp else 14.sp)
                        }
                        if (item.websiteUrl.isNotBlank()) {
                            Spacer(Modifier.height(12.dp))
                            Text("Quelle: Original-Mediathek des Senders", color = Color.White.copy(.72f), fontSize = 12.sp)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun V043Poster(image: String, title: String, accent: Color, modifier: Modifier = Modifier) {
    val shape = RoundedCornerShape(20.dp)
    Box(modifier.clip(shape).background(Color(0xE80A1420)).border(1.dp, Color.White.copy(.14f), shape)) {
        if (image.isNotBlank()) {
            AsyncImage(model = image, contentDescription = title, modifier = Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent, Color.Transparent, Color.Black.copy(.55f)))))
        } else {
            Box(
                Modifier.fillMaxSize().background(Brush.linearGradient(listOf(accent.copy(.42f), Color(0xFF13243A), Color(0xFF07111D)))),
                contentAlignment = Alignment.Center
            ) {
                Text(title, color = Color.White, fontSize = 22.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(20.dp), maxLines = 4)
            }
        }
    }
}

@Composable
private fun V043MediaMeta(media: MediaEntry, accent: Color, isTv: Boolean) {
    val values = buildList {
        if (media.year.isNotBlank()) add(media.year)
        if (media.duration.isNotBlank()) add(media.duration)
        if (media.genre.isNotBlank()) add(media.genre)
        if (media.rating.isNotBlank()) add("★ ${media.rating}")
    }
    if (values.isEmpty()) return
    Row(horizontalArrangement = Arrangement.spacedBy(7.dp)) {
        values.take(4).forEach { V043MetaChip(it, accent, isTv) }
    }
}

@Composable
private fun V043MetaChip(text: String, accent: Color, isTv: Boolean) {
    Text(
        text,
        color = Color.White,
        fontSize = if (isTv) 13.sp else 11.sp,
        fontWeight = FontWeight.Bold,
        modifier = Modifier.background(accent.copy(.20f), RoundedCornerShape(9.dp))
            .border(1.dp, accent.copy(.48f), RoundedCornerShape(9.dp))
            .padding(horizontal = if (isTv) 10.dp else 7.dp, vertical = if (isTv) 6.dp else 4.dp)
    )
}

@Composable
private fun V043InfoLine(label: String, value: String, accent: Color, isTv: Boolean) {
    Text(label, color = accent, fontSize = 12.sp, fontWeight = FontWeight.Black)
    Spacer(Modifier.height(3.dp))
    Text(value, color = Color.White.copy(.91f), fontSize = if (isTv) 15.sp else 13.sp, lineHeight = if (isTv) 20.sp else 18.sp)
}

@Composable
private fun V043SenderHero(channel: String, topic: String, accent: Color) {
    Box(
        Modifier.fillMaxSize().background(Brush.linearGradient(listOf(accent.copy(.48f), Color(0xFF152A43), Color(0xFF07111D)))),
        contentAlignment = Alignment.Center
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.padding(20.dp)) {
            Text(channel.ifBlank { "MEDIATHEK" }.uppercase(), color = Color.White, fontSize = 30.sp, fontWeight = FontWeight.Black, maxLines = 1)
            if (topic.isNotBlank()) {
                Spacer(Modifier.height(7.dp))
                Text(topic, color = Color.White.copy(.88f), fontSize = 15.sp, fontWeight = FontWeight.SemiBold, maxLines = 3, overflow = TextOverflow.Ellipsis)
            }
        }
    }
}

private fun v043MediathekMeta(item: MediathekClient.Item): String {
    val parts = mutableListOf<String>()
    if (item.channel.isNotBlank()) parts += item.channel
    if (item.timestamp > 0L) parts += SimpleDateFormat("dd.MM.yyyy · HH:mm", Locale.GERMANY).format(Date(item.timestamp * 1000L))
    if (item.durationSeconds > 0L) {
        val minutes = item.durationSeconds / 60L
        parts += if (minutes >= 60L) "${minutes / 60L} Std ${minutes % 60L} Min" else "$minutes Min"
    }
    return parts.joinToString("  ·  ")
}
