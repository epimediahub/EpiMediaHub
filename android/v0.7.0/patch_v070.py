#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


def function_span(text: str, signature: str):
    start = text.find(signature)
    if start < 0:
        raise SystemExit(f"function not found: {signature}")
    brace = text.find("{", start)
    if brace < 0:
        raise SystemExit(f"opening brace missing: {signature}")
    depth = 0
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1
    raise SystemExit(f"closing brace missing: {signature}")


def replace_function(path: Path, signature: str, replacement: str):
    text = path.read_text()
    start, end = function_span(text, signature)
    path.write_text(text[:start] + replacement.rstrip() + text[end:])


# ---------------------------------------------------------------------------
# Version and update channel.
# ---------------------------------------------------------------------------
build = root / "app/build.gradle.kts"
s = build.read_text()
require_once(s, 'versionCode = 618', 'v0.6.4.15 versionCode')
require_once(s, 'versionName = "0.6.4.15"', 'v0.6.4.15 versionName')
build.write_text(s.replace('versionCode = 618', 'versionCode = 700', 1).replace('versionName = "0.6.4.15"', 'versionName = "0.7.0"', 1))

updates = java / "data/UpdateManager.kt"
s = updates.read_text()
s = s.replace('releases/tags/v0.6.4-test', 'releases/tags/v0.7.0-test')
s = s.replace('EpiMediaHub_Android_v0.6.4-test.apk', 'EpiMediaHub_Android_v0.7.0-test.apk')
s = s.replace('releases/download/v0.6.4-test/', 'releases/download/v0.7.0-test/')
updates.write_text(s)


# ---------------------------------------------------------------------------
# Every standard design uses the real EpiMediaHub brand instead of the old
# EPI text badge. This central implementation applies to every screen.
# ---------------------------------------------------------------------------
repo = java / "data/ThemeRepository.kt"
s = repo.read_text()
old = '''    fun markRes(id: String) = drawable("mark_${safe(id)}")
    fun homeMotifRes(id: String) = drawable("home_motif_${safe(id)}")
    fun centerMarkRes(id: String) = drawable("center_mark_${safe(id)}")
    fun bannerMarkRes(id: String) = drawable("banner_mark_${safe(id)}")'''
require_once(s, old, "theme resource helpers")
new = '''    private fun isStandard(id: String) = id == "default" || id == "epi_blue" || id == "epi_red"

    fun markRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("mark_${safe(id)}")
    fun homeMotifRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("home_motif_${safe(id)}")
    fun centerMarkRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("center_mark_${safe(id)}")
    fun bannerMarkRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("banner_mark_${safe(id)}")'''
repo.write_text(s.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Location-dependent weather, inferred from the TV's public network location.
# The last successful reading is cached, so the header does not flicker when
# wttr.in is temporarily unavailable.
# ---------------------------------------------------------------------------
(java / "data/V070WeatherClient.kt").write_text(r'''package de.epimediahub.app.data

import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class V070WeatherSnapshot(
    val temperatureC: Int,
    val description: String,
    val code: Int
)

object V070WeatherClient {
    private const val CACHE = "v070_weather"
    private const val CACHE_MAX_AGE = 30L * 60L * 1000L

    fun cached(context: Context): V070WeatherSnapshot? {
        val prefs = context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
        val json = prefs.getString("payload", null) ?: return null
        return parse(json)
    }

    suspend fun refresh(context: Context): V070WeatherSnapshot? = withContext(Dispatchers.IO) {
        val prefs = context.getSharedPreferences(CACHE, Context.MODE_PRIVATE)
        val age = System.currentTimeMillis() - prefs.getLong("time", 0L)
        if (age in 0 until CACHE_MAX_AGE) return@withContext cached(context)
        runCatching {
            val connection = (URL("https://wttr.in/?format=j1").openConnection() as HttpURLConnection).apply {
                connectTimeout = 7000
                readTimeout = 7000
                useCaches = true
                setRequestProperty("Accept", "application/json")
                setRequestProperty("User-Agent", "EpiMediaHub-Android/0.7.0")
            }
            try {
                if (connection.responseCode !in 200..299) error("weather HTTP ${connection.responseCode}")
                val body = connection.inputStream.bufferedReader().use { it.readText() }
                parse(body) ?: error("weather response incomplete")
                prefs.edit().putString("payload", body).putLong("time", System.currentTimeMillis()).apply()
                parse(body)!!
            } finally {
                connection.disconnect()
            }
        }.getOrNull() ?: cached(context)
    }

    private fun parse(body: String): V070WeatherSnapshot? = runCatching {
        val current = JSONObject(body).getJSONArray("current_condition").getJSONObject(0)
        val description = current.optJSONArray("weatherDesc")
            ?.optJSONObject(0)?.optString("value").orEmpty().trim()
        V070WeatherSnapshot(
            temperatureC = current.getString("temp_C").toInt(),
            description = description.ifBlank { "Wetter" },
            code = current.optString("weatherCode", "0").toIntOrNull() ?: 0
        )
    }.getOrNull()
}
''')


# ---------------------------------------------------------------------------
# Strong, reusable TV focus treatment.
# ---------------------------------------------------------------------------
(java / "ui/V070Focus.kt").write_text(r'''package de.epimediahub.app.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp

fun Modifier.v070TvFocus(accent: Color, radius: Int = 12): Modifier = composed {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(radius.dp)
    this
        .onFocusChanged { focused = it.hasFocus }
        .graphicsLayer {
            scaleX = if (focused) 1.055f else 1f
            scaleY = if (focused) 1.055f else 1f
        }
        .shadow(if (focused) 22.dp else 0.dp, shape)
        .border(if (focused) 4.dp else 0.dp, if (focused) Color.White else Color.Transparent, shape)
}
''')


# ---------------------------------------------------------------------------
# Clean tile-first home: the selected skin's compact transparent mark is
# clipped inside each tile. Large home_motif artwork is intentionally never
# laid across several tiles.
# ---------------------------------------------------------------------------
(java / "ui/V070Home.kt").write_text(r'''package de.epimediahub.app.ui

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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.ParityMediathekHome
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.data.V070WeatherClient
import de.epimediahub.app.data.V070WeatherSnapshot
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private data class V070Tile(val title: String, val subtitle: String, val icon: Int, val open: () -> Unit)

@Composable
fun V070HomeScreen(vm: MainViewModel, isTv: Boolean, accent: Color) {
    val u by vm.ui.collectAsState()
    val context = LocalContext.current
    val firstFocus = remember { FocusRequester() }
    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    var weather by remember { mutableStateOf<V070WeatherSnapshot?>(V070WeatherClient.cached(context)) }
    val skinMark = remember(u.themeId) { vm.themeRepo().markRes(u.themeId) }

    LaunchedEffect(Unit) {
        while (true) {
            now = System.currentTimeMillis()
            delay(1000L)
        }
    }
    LaunchedEffect(Unit) { weather = V070WeatherClient.refresh(context) ?: weather }
    LaunchedEffect(isTv) { if (isTv) runCatching { firstFocus.requestFocus() } }

    val tiles = listOf(
        V070Tile("LIVE TV", "Sender · Voll-EPG · Catch-up", R.drawable.icon_live) { vm.openLibrary(MediaKind.LIVE) },
        V070Tile("FILME", "Kategorien · Details · Resume", R.drawable.icon_movies) { vm.openLibrary(MediaKind.MOVIE) },
        V070Tile("SERIEN", "Kategorien · Staffeln · Episoden", R.drawable.icon_series) { vm.openLibrary(MediaKind.SERIES) },
        V070Tile("MEDIATHEK", "Sender · Sendungen · Details", R.drawable.icon_mediathek) { vm.navigate(ParityMediathekHome) },
        V070Tile("PLAYLISTS", if (u.playlists.size > 1) "${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen", R.drawable.icon_playlist) { vm.navigate(Screen.Playlists) },
        V070Tile("EINSTELLUNGEN", "Design · QR-Websetup · Update", R.drawable.icon_settings) { vm.navigate(Screen.Settings) }
    )

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val compact = !isTv && maxHeight < 430.dp
        val headerHeight = when { isTv -> 184.dp; compact -> 82.dp; else -> 106.dp }
        val columns = if (isTv) 2 else 3
        val rows = if (isTv) 3 else 2
        val gap = if (isTv) 13.dp else if (compact) 6.dp else 9.dp
        Column(Modifier.fillMaxSize()) {
            V070Header(u.active?.name ?: "EpiMediaHub", isTv, compact, accent, now, weather, Modifier.fillMaxWidth().height(headerHeight))
            Box(Modifier.weight(1f).fillMaxWidth().padding(start = if (isTv) 48.dp else 8.dp, end = if (isTv) 48.dp else 8.dp, top = 2.dp, bottom = if (isTv) 18.dp else 7.dp)) {
                Column(Modifier.fillMaxSize(), verticalArrangement = Arrangement.spacedBy(gap)) {
                    for (row in 0 until rows) {
                        Row(Modifier.fillMaxWidth().weight(1f), horizontalArrangement = Arrangement.spacedBy(gap)) {
                            for (column in 0 until columns) {
                                val index = row * columns + column
                                val tile = tiles[index]
                                V070TileCard(
                                    tile.title, tile.subtitle, tile.icon, skinMark, accent, isTv, compact,
                                    Modifier.weight(1f).fillMaxHeight().then(if (index == 0) Modifier.focusRequester(firstFocus) else Modifier),
                                    tile.open
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun V070Header(playlist: String, isTv: Boolean, compact: Boolean, accent: Color, now: Long, weather: V070WeatherSnapshot?, modifier: Modifier = Modifier) {
    val time = remember(now / 1000L) { SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(now)) }
    val date = remember(now / 60000L) { SimpleDateFormat("EEE, dd.MM.yyyy", Locale.GERMANY).format(Date(now)) }
    val isNight = remember(now / 60000L) { SimpleDateFormat("HH", Locale.getDefault()).format(Date(now)).toIntOrNull()?.let { it < 7 || it >= 20 } == true }
    Box(modifier.padding(horizontal = if (isTv) 36.dp else 9.dp, vertical = if (compact) 3.dp else 7.dp)) {
        Image(painterResource(R.drawable.brand_header), "EpiMediaHub", Modifier.align(Alignment.TopStart).width(if (isTv) 340.dp else if (compact) 174.dp else 216.dp).height(if (isTv) 118.dp else if (compact) 62.dp else 76.dp), contentScale = ContentScale.Fit)
        Column(Modifier.align(Alignment.TopEnd).padding(top = if (compact) 3.dp else 7.dp), horizontalAlignment = Alignment.End) {
            Text(playlist, color = Color.White, fontSize = if (isTv) 22.sp else if (compact) 14.sp else 16.sp, fontWeight = FontWeight.Black, maxLines = 1)
            Text(if (isTv) "ANDROID TV · 0.7.0" else "MOBILE · 0.7.0", color = Color.White.copy(.92f), fontSize = if (isTv) 14.sp else 11.sp, fontWeight = FontWeight.SemiBold)
        }
        if (!compact || isTv) {
            Column(Modifier.align(Alignment.BottomCenter).padding(bottom = if (isTv) 9.dp else 3.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                weather?.let {
                    Text("${V070WeatherIcon(it.code, isNight)}  ${it.temperatureC}° · ${it.description}", color = Color.White.copy(.94f), fontSize = if (isTv) 15.sp else 11.sp, fontWeight = FontWeight.Bold, maxLines = 1)
                    Spacer(Modifier.height(if (isTv) 1.dp else 0.dp))
                }
                Text(time, color = Color.White, fontSize = if (isTv) 34.sp else 20.sp, fontWeight = FontWeight.Black)
                Text(date, color = Color.White.copy(.90f), fontSize = if (isTv) 14.sp else 11.sp, fontWeight = FontWeight.Medium)
            }
        }
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(2.dp).background(Brush.horizontalGradient(listOf(Color.Transparent, accent.copy(.92f), Color.Transparent))))
    }
}

private fun V070WeatherIcon(code: Int, night: Boolean): String = when (code) {
    113 -> if (night) "☾" else "☀"
    116 -> if (night) "☾☁" else "☀☁"
    119, 122 -> "☁"
    143, 248, 260 -> if (night) "☾≋" else "≋"
    in 176..377 -> if (code in setOf(227, 230, 323, 326, 329, 332, 335, 338, 368, 371)) "❄" else "☂"
    else -> if (night) "☾" else "◌"
}

@Composable
private fun V070TileCard(title: String, subtitle: String, iconRes: Int, skinMark: Int, accent: Color, isTv: Boolean, compact: Boolean, modifier: Modifier = Modifier, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.052f else 1f, spring(dampingRatio = Spring.DampingRatioNoBouncy, stiffness = Spring.StiffnessLow), label = "v070TileScale")
    val shape = RoundedCornerShape(if (isTv) 18.dp else 13.dp)
    Box(
        modifier.graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 30.dp else 3.dp, shape)
            .onFocusChanged { focused = it.isFocused }.focusable().clip(shape)
            .background(Brush.linearGradient(if (focused) listOf(Color(0xF22A3443), Color(0xEC101722)) else listOf(Color(0xC70D1722), Color(0xB9070D15))))
            .border(if (focused) 4.dp else 1.dp, if (focused) Color.White else Color.White.copy(.16f), shape)
            .clickable(onClick = onClick)
    ) {
        if (skinMark != 0 && !compact) {
            Box(
                Modifier.align(Alignment.CenterEnd).padding(end = if (isTv) 20.dp else 8.dp)
                    .width(if (isTv) 128.dp else 74.dp).height(if (isTv) 62.dp else 38.dp)
                    .clip(RoundedCornerShape(12.dp)).background(Color.Black.copy(.16f)),
                contentAlignment = Alignment.Center
            ) {
                Image(painterResource(skinMark), null, Modifier.fillMaxSize().padding(if (isTv) 7.dp else 4.dp).alpha(if (focused) .82f else .45f), contentScale = ContentScale.Fit)
            }
        }
        Box(Modifier.align(Alignment.CenterStart).fillMaxHeight().width(if (focused) 10.dp else 4.dp).background(if (focused) accent else accent.copy(.62f)))
        Image(painterResource(iconRes), null, Modifier.align(Alignment.CenterStart).padding(start = if (compact) 11.dp else if (isTv) 27.dp else 14.dp).size(if (compact) 34.dp else if (isTv) 62.dp else 43.dp), contentScale = ContentScale.Fit)
        Column(
            Modifier.align(Alignment.Center).fillMaxWidth().padding(start = if (isTv) 102.dp else if (compact) 55.dp else 66.dp, end = if (isTv) 142.dp else if (compact) 7.dp else 84.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            Text(title, color = Color.White, fontSize = if (compact) 14.sp else if (isTv) 25.sp else 17.sp, fontWeight = FontWeight.Black, textAlign = TextAlign.Center, maxLines = 1)
            if (!compact) {
                Spacer(Modifier.height(if (isTv) 5.dp else 2.dp))
                Text(subtitle, color = Color.White.copy(.92f), fontSize = if (isTv) 13.sp else 11.sp, fontWeight = FontWeight.SemiBold, textAlign = TextAlign.Center, maxLines = 2)
            }
        }
        if (focused) Text("OK", Modifier.align(Alignment.BottomEnd).padding(end = 13.dp, bottom = 8.dp), color = Color.White, fontSize = 10.sp, fontWeight = FontWeight.Black)
    }
}
''')


# ---------------------------------------------------------------------------
# Playlist selector with readable names and unmistakable focused/active state.
# ---------------------------------------------------------------------------
(java / "ui/V070Playlists.kt").write_text(r'''package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.PlaylistPlay
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import kotlinx.coroutines.delay

@Composable
fun V070PlaylistsScreen(vm: MainViewModel, accent: Color) {
    val u by vm.ui.collectAsState()
    val firstFocus = remember { FocusRequester() }
    BackHandler { vm.back() }
    LaunchedEffect(u.playlists.size) {
        if (u.playlists.isNotEmpty()) { delay(90); runCatching { firstFocus.requestFocus() } }
    }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("PLAYLISTS", R.drawable.brand_header, { vm.back() }, actions = {
            Button(
                onClick = { vm.navigate(Screen.AddPlaylist) },
                modifier = Modifier.v070TvFocus(accent),
                colors = ButtonDefaults.buttonColors(containerColor = accent)
            ) { Text("+ HINZUFÜGEN", color = Color.Black, fontWeight = FontWeight.Black) }
        })
        if (u.playlists.isEmpty()) {
            EmptyState("Keine Playlist", "Über + Hinzufügen oder das Websetup einrichten.")
        } else {
            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal = 42.dp, vertical = 14.dp),
                contentPadding = PaddingValues(bottom = 30.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp)
            ) {
                itemsIndexed(u.playlists, key = { _, playlist -> playlist.id }) { index, playlist ->
                    val active = playlist.id == u.active?.id
                    V070PlaylistCard(
                        name = playlist.name,
                        type = playlist.type.name,
                        active = active,
                        accent = accent,
                        modifier = if (index == 0) Modifier.focusRequester(firstFocus) else Modifier,
                        onSelect = { vm.selectPlaylist(playlist.id) },
                        onDelete = { vm.removePlaylist(playlist.id) }
                    )
                }
            }
        }
    }
}

@Composable
private fun V070PlaylistCard(name: String, type: String, active: Boolean, accent: Color, modifier: Modifier, onSelect: () -> Unit, onDelete: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.025f else 1f, label = "playlistFocus")
    val shape = RoundedCornerShape(20.dp)
    Row(
        modifier.fillMaxWidth().heightIn(min = 104.dp)
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 26.dp else 3.dp, shape)
            .onFocusChanged { focused = it.isFocused }.focusable()
            .background(Brush.horizontalGradient(if (focused) listOf(accent.copy(.48f), Color(0xF31A2533), Color(0xF10A1018)) else listOf(Color(0xE6162638), Color(0xE309111B))), shape)
            .border(if (focused) 4.dp else if (active) 2.dp else 1.dp, if (focused) Color.White else if (active) accent else Color.White.copy(.14f), shape)
            .clickable(onClick = onSelect).padding(horizontal = 20.dp, vertical = 15.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(62.dp).background(if (active) accent else Color.White.copy(.09f), RoundedCornerShape(16.dp)), contentAlignment = Alignment.Center) {
            Icon(if (active) Icons.Default.CheckCircle else Icons.Default.PlaylistPlay, null, tint = if (active) Color.Black else accent, modifier = Modifier.size(36.dp))
        }
        Spacer(Modifier.width(18.dp))
        Column(Modifier.weight(1f)) {
            Text(name.ifBlank { "Unbenannte Playlist" }, color = Color.White, fontSize = 23.sp, fontWeight = FontWeight.Black, maxLines = 1)
            Spacer(Modifier.height(5.dp))
            Text(type.replace('_', ' '), color = Color.White.copy(.88f), fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
        }
        Surface(shape = RoundedCornerShape(99.dp), color = if (active) accent else if (focused) Color.White else Color.White.copy(.10f)) {
            Text(if (active) "AKTIV" else if (focused) "OK · AUSWÄHLEN" else "AUSWÄHLEN", color = if (active || focused) Color.Black else Color.White.copy(.82f), fontSize = 12.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(horizontal = 16.dp, vertical = 9.dp))
        }
        Spacer(Modifier.width(10.dp))
        TextButton(onClick = onDelete, modifier = Modifier.v070TvFocus(Color(0xFFFF7070))) {
            Text("LÖSCHEN", color = Color(0xFFFF9292), fontWeight = FontWeight.Bold)
        }
    }
}
''')


# ---------------------------------------------------------------------------
# Compact receiver-style Live TV row.
# ---------------------------------------------------------------------------
rows = java / "ui/BrowserRows.kt"
compact_live = r'''@Composable
fun LiveChannelRow(
    media: MediaEntry,
    nowText: String,
    accent: Color,
    modifier: Modifier = Modifier,
    isTv: Boolean = false,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.018f else 1f, spring(stiffness = 430f), label = "liveReceiverFocus")
    val shape = RoundedCornerShape(if (isTv) 12.dp else 13.dp)
    val initials = remember(media.name) {
        media.name.split(Regex("\\s+")).filter { it.isNotBlank() }.take(2)
            .joinToString("") { it.take(1).uppercase() }.ifBlank { "TV" }
    }
    Surface(
        modifier = modifier.fillMaxWidth().graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 18.dp else 1.dp, shape)
            .onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = Color.Transparent,
        contentColor = Color.White,
        shape = shape,
        border = androidx.compose.foundation.BorderStroke(if (focused) 4.dp else 1.dp, if (focused) Color.White else Color.White.copy(.12f))
    ) {
        Box(
            Modifier.fillMaxWidth().height(if (isTv) 68.dp else 78.dp)
                .background(Brush.horizontalGradient(listOf(accent.copy(if (focused) .42f else .16f), Color(0xF20B1420), Color(0xFA070B12))))
        ) {
            Box(Modifier.align(Alignment.CenterStart).fillMaxHeight().width(if (focused) 9.dp else 4.dp).background(accent))
            Row(Modifier.fillMaxSize().padding(start = if (isTv) 15.dp else 13.dp, end = 15.dp, top = 7.dp, bottom = 7.dp), verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    shape = RoundedCornerShape(9.dp), color = Color.White.copy(.95f),
                    modifier = Modifier.width(if (isTv) 84.dp else 102.dp).fillMaxHeight()
                ) {
                    if (media.image.isNotBlank()) {
                        SubcomposeAsyncImage(model = media.image, contentDescription = media.name, modifier = Modifier.fillMaxSize().padding(6.dp), contentScale = ContentScale.Fit) {
                            if (painter.state is AsyncImagePainter.State.Success) SubcomposeAsyncImageContent()
                            else Box(Modifier.fillMaxSize().background(accent.copy(.13f)), contentAlignment = Alignment.Center) { Text(initials, color = accent, fontSize = 17.sp, fontWeight = FontWeight.Black) }
                        }
                    } else Box(Modifier.fillMaxSize().background(accent.copy(.13f)), contentAlignment = Alignment.Center) { Text(initials, color = accent, fontSize = 17.sp, fontWeight = FontWeight.Black) }
                }
                Spacer(Modifier.width(if (isTv) 15.dp else 13.dp))
                Column(Modifier.weight(1f), verticalArrangement = Arrangement.Center) {
                    Text(media.name, color = Color.White, fontSize = if (isTv) 18.sp else 17.sp, fontWeight = FontWeight.Black, maxLines = 1)
                    Text(if (nowText.isNotBlank()) nowText else "Jetzt live", color = Color.White.copy(if (focused) .96f else .72f), fontSize = if (isTv) 12.sp else 11.sp, maxLines = 1, modifier = Modifier.padding(top = 2.dp))
                }
                Text(if (focused) "OK · ÖFFNEN" else "LIVE", color = if (focused) Color.White else accent, fontSize = 11.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.width(5.dp))
                Icon(Icons.Default.PlayArrow, null, tint = if (focused) Color.White else Color.White.copy(.52f), modifier = Modifier.size(23.dp))
            }
        }
    }
}'''
replace_function(rows, '@Composable\nfun LiveChannelRow(', compact_live)


# ---------------------------------------------------------------------------
# Screen routes, denser Live TV layout and stronger sidebar selection.
# ---------------------------------------------------------------------------
screens = java / "ui/Screens.kt"
s = screens.read_text()
require_once(s, '    V044HomeScreen(vm,isTv,accent)', 'home delegate')
s = s.replace('    V044HomeScreen(vm,isTv,accent)', '    V070HomeScreen(vm,isTv,accent)', 1)
s = s.replace('Modifier.width(265.dp).fillMaxHeight()', 'Modifier.width(if(kind==MediaKind.LIVE)230.dp else 265.dp).fillMaxHeight()', 1)
s = s.replace('Modifier.fillMaxSize().padding(10.dp),contentPadding=PaddingValues(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(if(kind==MediaKind.LIVE)7.dp else 11.dp)', 'Modifier.fillMaxSize().padding(if(kind==MediaKind.LIVE)7.dp else 10.dp),contentPadding=PaddingValues(bottom=18.dp),verticalArrangement=Arrangement.spacedBy(if(kind==MediaKind.LIVE)4.dp else 11.dp)', 1)
old_sidebar = 'padding(horizontal=11.dp,vertical=11.dp),verticalAlignment=Alignment.CenterVertically){\n        Icon(icon,null,tint=if(selected||focused)accent else Color.White.copy(.84f),modifier=Modifier.size(20.dp));Spacer(Modifier.width(9.dp));Text(title,color=Color.White,fontWeight=if(selected||focused)FontWeight.Bold else FontWeight.Medium,fontSize=14.sp,maxLines=2)'
new_sidebar = 'padding(horizontal=10.dp,vertical=7.dp),verticalAlignment=Alignment.CenterVertically){\n        Icon(icon,null,tint=if(selected||focused)if(focused)Color.White else accent else Color.White.copy(.84f),modifier=Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text(title,color=Color.White,fontWeight=if(selected||focused)FontWeight.Black else FontWeight.Medium,fontSize=13.sp,maxLines=1)'
require_once(s, old_sidebar, 'compact sidebar')
s = s.replace(old_sidebar, new_sidebar, 1)
s = s.replace('Text("Android v0.6.0",fontWeight=FontWeight.Bold)', 'Text("Android v0.7.0",fontWeight=FontWeight.Bold)')
screens.write_text(s)


# ---------------------------------------------------------------------------
# Skin selection previews: compact transparent mark, centered in a contained
# right-hand area. No more full-width white family motif strips.
# ---------------------------------------------------------------------------
themes = java / "ui/V046Themes.kt"
s = themes.read_text()
s = s.replace('vm.themeRepo().homeMotifRes(theme.id).takeIf { it != 0 } ?: vm.themeRepo().markRes(theme.id)', 'vm.themeRepo().markRes(theme.id)')
old_image = 'if (motifRes != 0) Image(painterResource(motifRes), null, Modifier.align(Alignment.CenterEnd).fillMaxHeight().fillMaxWidth(.64f), contentScale = ContentScale.Fit)'
new_image = '''if (motifRes != 0) {
            Box(Modifier.align(Alignment.CenterEnd).padding(end = 24.dp).width(190.dp).height(86.dp).clip(RoundedCornerShape(15.dp)).background(Color.Black.copy(.20f)), contentAlignment = Alignment.Center) {
                Image(painterResource(motifRes), null, Modifier.fillMaxSize().padding(10.dp), contentScale = ContentScale.Fit)
            }
        }'''
require_once(s, old_image, 'theme preview motif')
s = s.replace(old_image, new_image, 1)
s = s.replace('.border(if (active || focused) 2.dp else 1.dp, if (active || focused) accent else Color.White.copy(.14f), shape)', '.border(if (focused) 4.dp else if (active) 2.dp else 1.dp, if (focused) Color.White else if (active) accent else Color.White.copy(.14f), shape)', 1)
themes.write_text(s)


# ---------------------------------------------------------------------------
# Websetup/Tailscale buttons get an explicit TV focus frame.
# ---------------------------------------------------------------------------
web = java / "ui/V047WebAdmin.kt"
s = web.read_text()
replacements = {
    'TextButton(onClick = { showDashboardPin = true })': 'TextButton(onClick = { showDashboardPin = true }, modifier = Modifier.v070TvFocus(accent))',
    'TextButton(onClick = { vm.navigate(Screen.AddPlaylist) })': 'TextButton(onClick = { vm.navigate(Screen.AddPlaylist) }, modifier = Modifier.v070TvFocus(accent))',
    'TextButton(onClick = { vm.restartWebAdmin() })': 'TextButton(onClick = { vm.restartWebAdmin() }, modifier = Modifier.v070TvFocus(accent))',
    'OutlinedButton(onClick = { showRemoteUnlock = true }, shape = RoundedCornerShape(12.dp))': 'OutlinedButton(onClick = { showRemoteUnlock = true }, modifier = Modifier.v070TvFocus(accent), shape = RoundedCornerShape(12.dp))',
    'OutlinedButton(onClick = { vm.lockRemoteMaintenance() }, shape = RoundedCornerShape(12.dp))': 'OutlinedButton(onClick = { vm.lockRemoteMaintenance() }, modifier = Modifier.v070TvFocus(accent), shape = RoundedCornerShape(12.dp))',
    'modifier = Modifier.padding(top = 18.dp))': 'modifier = Modifier.padding(top = 18.dp).v070TvFocus(accent))'
}
for old, new in replacements.items():
    if old not in s:
        raise SystemExit(f"web focus anchor missing: {old}")
    s = s.replace(old, new)

# The three primary filled actions have no modifier yet.
for anchor in [
    'onClick = { showDashboardPin = true },\n                                    colors',
    'onClick = { showRemoteUnlock = true },\n                                    colors'
]:
    if anchor not in s:
        raise SystemExit(f"primary web action anchor missing: {anchor}")
    s = s.replace(anchor, anchor.replace(',\n                                    colors', ',\n                                    modifier = Modifier.v070TvFocus(accent),\n                                    colors'))
web.write_text(s)


# ---------------------------------------------------------------------------
# A short Android-native intro with an optional synthesized cinematic chime.
# It is cancellable and never blocks navigation or startup work.
# ---------------------------------------------------------------------------
(java / "ui/V070Intro.kt").write_text(r'''package de.epimediahub.app.ui

import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioTrack
import androidx.activity.compose.BackHandler
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.R
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import kotlin.math.PI
import kotlin.math.sin

@Composable
fun V070IntroScreen(accent: Color, onFinished: () -> Unit) {
    var visible by remember { mutableStateOf(false) }
    var finished by remember { mutableStateOf(false) }
    val focusRequester = remember { FocusRequester() }
    val scale by animateFloatAsState(if (visible) 1f else .78f, label = "introScale")
    val introAlpha by animateFloatAsState(if (visible) 1f else 0f, label = "introAlpha")
    val scope = rememberCoroutineScope()

    fun finish() {
        if (!finished) { finished = true; onFinished() }
    }

    BackHandler { finish() }
    LaunchedEffect(Unit) {
        visible = true
        runCatching { focusRequester.requestFocus() }
        launch { V070IntroSound.play() }
        delay(2850L)
        finish()
    }

    Box(
        Modifier.fillMaxSize()
            .background(Brush.radialGradient(listOf(accent.copy(.30f), Color(0xFF07111E), Color.Black), radius = 980f))
            .focusRequester(focusRequester).focusable()
            .onPreviewKeyEvent {
                if (it.type == KeyEventType.KeyDown) { finish(); true } else false
            },
        contentAlignment = Alignment.Center
    ) {
        Box(Modifier.fillMaxWidth(.58f).height(2.dp).align(Alignment.Center).background(Brush.horizontalGradient(listOf(Color.Transparent, accent, Color.Transparent))))
        Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.graphicsLayer { scaleX = scale; scaleY = scale; alpha = introAlpha }) {
            Image(painterResource(R.drawable.brand_header), "EpiMediaHub", Modifier.width(520.dp).height(174.dp), contentScale = ContentScale.Fit)
            Spacer(Modifier.height(10.dp))
            androidx.compose.material3.Text("DEIN ENTERTAINMENT. KLARER. SCHNELLER.", color = Color.White.copy(.90f), fontSize = 15.sp, fontWeight = FontWeight.Black, letterSpacing = 2.sp)
        }
        androidx.compose.material3.Text("OK / ZURÜCK · INTRO ÜBERSPRINGEN", color = Color.White.copy(.55f), fontSize = 10.sp, fontWeight = FontWeight.Bold, modifier = Modifier.align(Alignment.BottomCenter).padding(bottom = 28.dp))
    }
}

private object V070IntroSound {
    suspend fun play() = withContext(Dispatchers.IO) {
        val rate = 22050
        val duration = 1.75
        val count = (rate * duration).toInt()
        val data = ShortArray(count)
        val notes = listOf(0.00 to 220.0, 0.38 to 329.63, 0.76 to 440.0, 1.08 to 659.25)
        for (i in data.indices) {
            val t = i.toDouble() / rate
            var sample = 0.0
            notes.forEach { (start, frequency) ->
                val local = t - start
                if (local in 0.0..0.72) {
                    val attack = (local / 0.05).coerceIn(0.0, 1.0)
                    val release = ((0.72 - local) / 0.48).coerceIn(0.0, 1.0)
                    val envelope = attack * release * release
                    sample += sin(2.0 * PI * frequency * local) * envelope
                    sample += sin(2.0 * PI * frequency * 2.0 * local) * envelope * 0.17
                }
            }
            data[i] = (sample.coerceIn(-1.0, 1.0) * Short.MAX_VALUE * 0.15).toInt().toShort()
        }
        var track: AudioTrack? = null
        try {
            track = AudioTrack.Builder()
                .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_ASSISTANCE_SONIFICATION).setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION).build())
                .setAudioFormat(AudioFormat.Builder().setEncoding(AudioFormat.ENCODING_PCM_16BIT).setSampleRate(rate).setChannelMask(AudioFormat.CHANNEL_OUT_MONO).build())
                .setBufferSizeInBytes(data.size * 2).setTransferMode(AudioTrack.MODE_STATIC).build()
            track.write(data, 0, data.size)
            track.play()
            delay(1850L)
        } catch (_: Throwable) {
        } finally {
            runCatching { track?.stop() }
            runCatching { track?.release() }
        }
    }
}
''')


# App intro routing and Back behavior.
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
require_once(s, 'import androidx.compose.runtime.remember\n', 'remember import')
s = s.replace('import androidx.compose.runtime.remember\n', 'import androidx.compose.runtime.remember\nimport androidx.compose.runtime.saveable.rememberSaveable\n', 1)
require_once(s, '    var showExitDialog by remember { mutableStateOf(false) }', 'exit state')
s = s.replace('    var showExitDialog by remember { mutableStateOf(false) }', '    var showExitDialog by remember { mutableStateOf(false) }\n    var showIntro by rememberSaveable { mutableStateOf(true) }', 1)
require_once(s, 'Screen.Playlists -> PlaylistsScreen(vm, accent)', 'playlist route')
s = s.replace('Screen.Playlists -> PlaylistsScreen(vm, accent)', 'Screen.Playlists -> V070PlaylistsScreen(vm, accent)', 1)
s = s.replace('BackHandler(enabled = hasInternalBackTarget)', 'BackHandler(enabled = !showIntro && hasInternalBackTarget)', 1)
s = s.replace('BackHandler(enabled = u.screen == Screen.Home)', 'BackHandler(enabled = !showIntro && u.screen == Screen.Home)', 1)
old = '''    MaterialTheme(colorScheme = scheme, shapes = shapes) {
        ThemeBackdrop(vm.themeRepo(), info, u.themeId) {'''
new = '''    MaterialTheme(colorScheme = scheme, shapes = shapes) {
        if (showIntro) {
            V070IntroScreen(accent = accent) { showIntro = false }
        } else ThemeBackdrop(vm.themeRepo(), info, u.themeId) {'''
require_once(s, old, 'intro route')
s = s.replace(old, new, 1)
app.write_text(s)


# Fire TV uses a dedicated 16:9 banner with a substantially larger brand mark.
manifest = root / "app/src/main/AndroidManifest.xml"
s = manifest.read_text()
require_once(s, 'android:banner="@drawable/tv_banner"', 'TV banner')
manifest.write_text(s.replace('android:banner="@drawable/tv_banner"', 'android:banner="@drawable/tv_launcher_banner"', 1))

drawable = root / "app/src/main/res/drawable"
drawable.mkdir(parents=True, exist_ok=True)
(drawable / "tv_launcher_banner.xml").write_text(r'''<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item>
        <shape android:shape="rectangle">
            <gradient android:angle="0" android:startColor="#07111E" android:centerColor="#102D4A" android:endColor="#05080E" />
            <corners android:radius="18dp" />
            <stroke android:width="3dp" android:color="#28A7F2" />
        </shape>
    </item>
    <item android:left="18dp" android:right="18dp" android:top="28dp" android:bottom="28dp">
        <bitmap android:src="@drawable/brand_header" android:gravity="fill_horizontal|center_vertical" />
    </item>
</layer-list>
''')


# Final source markers.
checks = [
    (build, 'versionName = "0.7.0"'),
    (build, 'versionCode = 700'),
    (java / "ui/V070Home.kt", 'V070WeatherClient.refresh'),
    (java / "ui/V070Playlists.kt", 'OK · AUSWÄHLEN'),
    (java / "ui/BrowserRows.kt", 'height(if (isTv) 68.dp else 78.dp)'),
    (java / "ui/V070Intro.kt", 'INTRO ÜBERSPRINGEN'),
    (java / "data/ThemeRepository.kt", 'id == "default" || id == "epi_blue" || id == "epi_red"'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"v0.7.0 marker missing in {path}: {marker}")

print("Android v0.7.0 UI, weather, intro, focus, skins and compact Live TV patch applied")
