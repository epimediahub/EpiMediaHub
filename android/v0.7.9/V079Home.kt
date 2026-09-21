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
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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

private data class V079Tile(
    val title: String,
    val subtitle: String,
    val icon: Int,
    val open: () -> Unit
)

@Composable
fun V079HomeScreen(vm: MainViewModel, isTv: Boolean, accent: Color) {
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

    LaunchedEffect(Unit) {
        weather = V070WeatherClient.refresh(context) ?: weather
    }

    LaunchedEffect(isTv) {
        if (isTv) {
            delay(80L)
            runCatching { firstFocus.requestFocus() }
        }
    }

    val tiles = listOf(
        V079Tile("LIVE TV", "Sender · EPG · schneller Wechsel", R.drawable.icon_live) {
            vm.openLibrary(MediaKind.LIVE)
        },
        V079Tile("FILME", "Kategorien · Details · Resume", R.drawable.icon_movies) {
            vm.openLibrary(MediaKind.MOVIE)
        },
        V079Tile("SERIEN", "Staffeln · Episoden · Resume", R.drawable.icon_series) {
            vm.openLibrary(MediaKind.SERIES)
        },
        V079Tile("MEDIATHEK", "Sender · Sendungen · Details", R.drawable.icon_mediathek) {
            vm.navigate(ParityMediathekHome)
        },
        V079Tile(
            "PLAYLISTS",
            if (u.playlists.size > 1) "${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen",
            R.drawable.icon_playlist
        ) {
            vm.navigate(Screen.Playlists)
        },
        V079Tile("GERÄT & DASHBOARD", "Kopplung · Kundensync · Websetup", R.drawable.icon_settings) {
            vm.navigate(Screen.WebAdmin)
        },
        V079Tile("EINSTELLUNGEN", "Design · Sprache · Audio · Update", R.drawable.icon_settings) {
            vm.navigate(Screen.Settings)
        }
    )

    BoxWithConstraints(Modifier.fillMaxSize()) {
        val compact = !isTv && maxHeight < 430.dp
        val headerHeight = when {
            isTv -> 176.dp
            compact -> 78.dp
            else -> 102.dp
        }
        val columns = if (isTv) 2 else 3
        val rows = (tiles.size + columns - 1) / columns
        val gap = if (isTv) 13.dp else if (compact) 6.dp else 9.dp

        Column(Modifier.fillMaxSize()) {
            V079Header(
                playlist = u.active?.name ?: "EpiMediaHub",
                isTv = isTv,
                compact = compact,
                accent = accent,
                now = now,
                weather = weather,
                modifier = Modifier.fillMaxWidth().height(headerHeight)
            )

            Box(
                Modifier.weight(1f).fillMaxWidth().padding(
                    start = if (isTv) 48.dp else 8.dp,
                    end = if (isTv) 48.dp else 8.dp,
                    top = 2.dp,
                    bottom = if (isTv) 18.dp else 7.dp
                )
            ) {
                Column(
                    Modifier.fillMaxSize(),
                    verticalArrangement = Arrangement.spacedBy(gap)
                ) {
                    for (row in 0 until rows) {
                        Row(
                            Modifier.fillMaxWidth().weight(1f),
                            horizontalArrangement = Arrangement.spacedBy(gap)
                        ) {
                            for (column in 0 until columns) {
                                val index = row * columns + column
                                if (index < tiles.size) {
                                    val tile = tiles[index]
                                    V079TileCard(
                                        title = tile.title,
                                        subtitle = tile.subtitle,
                                        iconRes = tile.icon,
                                        skinMark = skinMark,
                                        accent = accent,
                                        isTv = isTv,
                                        compact = compact,
                                        modifier = Modifier.weight(1f)
                                            .fillMaxHeight()
                                            .then(
                                                if (index == 0) Modifier.focusRequester(firstFocus)
                                                else Modifier
                                            ),
                                        onClick = tile.open
                                    )
                                } else {
                                    Spacer(Modifier.weight(1f).fillMaxHeight())
                                }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun V079Header(
    playlist: String,
    isTv: Boolean,
    compact: Boolean,
    accent: Color,
    now: Long,
    weather: V070WeatherSnapshot?,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    val menuLocale = remember(weather?.languageCode) {
        val tag = weather?.languageCode?.takeIf { it.isNotBlank() }
            ?: runCatching {
                context.resources.configuration.locales[0].language
            }.getOrDefault(Locale.getDefault().language)
        Locale.forLanguageTag(tag)
    }

    val time = remember(now / 1000L, menuLocale) {
        SimpleDateFormat("HH:mm", menuLocale).format(Date(now))
    }
    val date = remember(now / 60000L, menuLocale) {
        SimpleDateFormat("EEE, dd.MM.yyyy", menuLocale).format(Date(now))
    }
    val isNight = remember(now / 60000L) {
        SimpleDateFormat("HH", Locale.getDefault())
            .format(Date(now))
            .toIntOrNull()
            ?.let { it < 7 || it >= 20 } == true
    }

    Box(modifier.padding(horizontal = if (isTv) 36.dp else 9.dp, vertical = 6.dp)) {
        Image(
            painterResource(R.drawable.brand_header),
            "EpiMediaHub",
            Modifier.align(Alignment.TopStart)
                .width(if (isTv) 315.dp else if (compact) 168.dp else 205.dp)
                .height(if (isTv) 108.dp else if (compact) 58.dp else 72.dp),
            contentScale = ContentScale.Fit
        )

        Column(
            Modifier.align(Alignment.TopEnd).padding(top = if (compact) 2.dp else 6.dp),
            horizontalAlignment = Alignment.End
        ) {
            Text(
                playlist,
                color = Color.White,
                fontSize = if (isTv) 20.sp else if (compact) 13.sp else 15.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1
            )
            Text(
                if (isTv) "ANDROID TV · 0.7.9" else "ANDROID MOBILE · 0.7.9",
                color = Color.White.copy(.45f),
                fontSize = if (isTv) 11.sp else 9.sp,
                fontWeight = FontWeight.Bold
            )
        }

        if (!compact || isTv) {
            Column(
                Modifier.align(Alignment.BottomCenter)
                    .padding(bottom = if (isTv) 8.dp else 2.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                weather?.let {
                    val cityPrefix = it.city.takeIf { value -> value.isNotBlank() }
                        ?.let { value -> "$value · " }
                        .orEmpty()
                    Text(
                        "${V079WeatherIcon(it.code, isNight)}  $cityPrefix${it.temperatureC}° · ${it.description}",
                        color = Color.White.copy(.84f),
                        fontSize = if (isTv) 13.sp else 10.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = 1
                    )
                    Spacer(Modifier.height(if (isTv) 2.dp else 0.dp))
                }

                Text(
                    time,
                    color = Color.White,
                    fontSize = if (isTv) 32.sp else 19.sp,
                    fontWeight = FontWeight.Black
                )
                Text(
                    date,
                    color = Color.White.copy(.60f),
                    fontSize = if (isTv) 12.sp else 10.sp,
                    fontWeight = FontWeight.Medium
                )
            }
        }

        Box(
            Modifier.align(Alignment.BottomCenter)
                .fillMaxWidth()
                .height(1.dp)
                .background(
                    Brush.horizontalGradient(
                        listOf(Color.Transparent, accent.copy(.70f), Color.Transparent)
                    )
                )
        )
    }
}

private fun V079WeatherIcon(code: Int, night: Boolean): String = when (code) {
    113 -> if (night) "☾" else "☀"
    116 -> if (night) "☾☁" else "☀☁"
    119, 122 -> "☁"
    143, 248, 260 -> "≋"
    227, 230, 323, 326, 329, 332, 335, 338, 368, 371 -> "❄"
    in 176..377 -> "☂"
    else -> if (night) "☾" else "◌"
}

@Composable
private fun V079TileCard(
    title: String,
    subtitle: String,
    iconRes: Int,
    skinMark: Int,
    accent: Color,
    isTv: Boolean,
    compact: Boolean,
    modifier: Modifier = Modifier,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(
        if (focused) 1.038f else 1f,
        spring(
            dampingRatio = Spring.DampingRatioNoBouncy,
            stiffness = Spring.StiffnessMediumLow
        ),
        label = "v079TileScale"
    )
    val shape = RoundedCornerShape(if (isTv) 18.dp else 14.dp)

    Box(
        modifier
            .graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 26.dp else 2.dp, shape)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clip(shape)
            .background(
                Brush.linearGradient(
                    if (focused) {
                        listOf(Color(0xF2232C37), Color(0xF20C131B))
                    } else {
                        listOf(Color(0xE9141B24), Color(0xE4090F16))
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
        if (skinMark != 0 && !compact) {
            Image(
                painterResource(skinMark),
                null,
                Modifier.align(Alignment.CenterEnd)
                    .padding(end = if (isTv) 22.dp else 9.dp)
                    .width(if (isTv) 126.dp else 72.dp)
                    .height(if (isTv) 72.dp else 42.dp)
                    .graphicsLayer { alpha = if (focused) .18f else .09f },
                contentScale = ContentScale.Fit
            )
        }

        Box(
            Modifier.align(Alignment.CenterStart)
                .fillMaxHeight()
                .width(if (focused) 7.dp else 3.dp)
                .background(if (focused) accent else accent.copy(.52f))
        )

        Box(
            Modifier.align(Alignment.CenterStart)
                .padding(start = if (compact) 12.dp else if (isTv) 28.dp else 15.dp)
                .size(if (compact) 39.dp else if (isTv) 66.dp else 47.dp)
                .background(
                    Color.White.copy(if (focused) .08f else .045f),
                    RoundedCornerShape(if (isTv) 17.dp else 13.dp)
                ),
            contentAlignment = Alignment.Center
        ) {
            Image(
                painterResource(iconRes),
                null,
                Modifier.size(if (compact) 29.dp else if (isTv) 47.dp else 34.dp)
                    .graphicsLayer { alpha = if (focused) 1f else .86f },
                contentScale = ContentScale.Fit
            )
        }

        Column(
            Modifier.align(Alignment.CenterStart)
                .fillMaxWidth()
                .padding(
                    start = if (isTv) 112.dp else if (compact) 61.dp else 74.dp,
                    end = if (isTv) 150.dp else if (compact) 8.dp else 82.dp
                )
        ) {
            Text(
                title,
                color = Color.White,
                fontSize = if (compact) 14.sp else if (isTv) 24.sp else 17.sp,
                fontWeight = FontWeight.Black,
                maxLines = 1
            )
            if (!compact) {
                Spacer(Modifier.height(if (isTv) 5.dp else 2.dp))
                Text(
                    subtitle,
                    color = Color.White.copy(if (focused) .70f else .52f),
                    fontSize = if (isTv) 12.sp else 10.sp,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 2
                )
            }
        }

        if (focused) {
            Surface(
                modifier = Modifier.align(Alignment.BottomEnd).padding(9.dp),
                color = accent,
                shape = RoundedCornerShape(7.dp)
            ) {
                Text(
                    "OK",
                    color = Color.Black,
                    fontSize = 9.sp,
                    fontWeight = FontWeight.Black,
                    modifier = Modifier.padding(horizontal = 7.dp, vertical = 3.dp)
                )
            }
        }
    }
}
