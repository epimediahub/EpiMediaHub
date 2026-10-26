package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.model.MediaCategory
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.delay

@Composable
fun V076LiveTvScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val categories = remember(u.categories, u.catalogRows) {
        u.categories.filter { u.catalogRows[it.id].orEmpty().isNotEmpty() }
    }
    var selectedCategoryId by remember(u.active?.id) {
        mutableStateOf(vm.rememberedLibraryCategory(MediaKind.LIVE))
    }

    LaunchedEffect(categories, selectedCategoryId) {
        if (categories.isNotEmpty() && categories.none { it.id == selectedCategoryId }) {
            selectedCategoryId = categories.first().id
            vm.rememberLibraryCategory(MediaKind.LIVE, selectedCategoryId)
        }
    }

    val selectedCategory = categories.firstOrNull { it.id == selectedCategoryId } ?: categories.firstOrNull()
    val channels = selectedCategory?.let { u.catalogRows[it.id].orEmpty() }.orEmpty()
    var selectedChannelId by remember(selectedCategory?.id, u.active?.id) {
        mutableStateOf(
            selectedCategory?.let { vm.browserSelectedId(MediaKind.LIVE, it.id) }.orEmpty()
        )
    }

    LaunchedEffect(channels, selectedChannelId) {
        if (channels.isNotEmpty() && channels.none { it.id == selectedChannelId }) {
            selectedChannelId = channels.first().id
        }
    }

    val selectedChannel = channels.firstOrNull { it.id == selectedChannelId } ?: channels.firstOrNull()
    LaunchedEffect(selectedChannel?.id) {
        selectedChannel?.let { channel ->
            if (u.epg[channel.id].orEmpty().isEmpty()) vm.ensureEpg(channel)
        }
    }

    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            "LIVE TV",
            R.drawable.brand_header,
            { vm.back() },
            actions = {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    TextButton(onClick = { vm.openKindSearch(MediaKind.LIVE) }) {
                        Text("Suche", color = accent, fontWeight = FontWeight.Black)
                    }
                    TextButton(onClick = { vm.openKindFavorites(MediaKind.LIVE) }) {
                        Text("Favoriten", color = accent, fontWeight = FontWeight.Black)
                    }
                }
            }
        )

        if (u.loading || u.catalogRowsLoading) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(color = accent)
                    Spacer(Modifier.height(14.dp))
                    Text("Sender werden geladen …", color = Color.White, fontWeight = FontWeight.Black)
                }
            }
            return@Column
        }

        LoadingOrError(false, u.error)
        if (u.epgLoading) LinearProgressIndicator(Modifier.fillMaxWidth(), color = accent)

        BoxWithConstraints(Modifier.fillMaxSize()) {
            val wide = isTv || maxWidth >= 760.dp
            if (wide) {
                V076WideLiveTv(
                    vm = vm,
                    accent = accent,
                    categories = categories,
                    selectedCategory = selectedCategory,
                    channels = channels,
                    selectedChannel = selectedChannel,
                    onCategory = { category ->
                        selectedCategoryId = category.id
                        vm.rememberLibraryCategory(MediaKind.LIVE, category.id)
                        selectedChannelId = vm.browserSelectedId(MediaKind.LIVE, category.id)
                    },
                    onChannelSelected = { index, channel ->
                        selectedChannelId = channel.id
                        selectedCategory?.let {
                            vm.rememberBrowserPosition(MediaKind.LIVE, it.id, index, channel.id)
                        }
                    },
                    onPlay = { channel -> vm.play(channel, channels) },
                    isTv = isTv
                )
            } else {
                V076MobileLiveTv(
                    vm = vm,
                    accent = accent,
                    categories = categories,
                    selectedCategory = selectedCategory,
                    channels = channels,
                    selectedChannel = selectedChannel,
                    onCategory = { category ->
                        selectedCategoryId = category.id
                        vm.rememberLibraryCategory(MediaKind.LIVE, category.id)
                        selectedChannelId = vm.browserSelectedId(MediaKind.LIVE, category.id)
                    },
                    onChannelSelected = { index, channel ->
                        selectedChannelId = channel.id
                        selectedCategory?.let {
                            vm.rememberBrowserPosition(MediaKind.LIVE, it.id, index, channel.id)
                        }
                    },
                    onPlay = { channel -> vm.play(channel, channels) }
                )
            }
        }
    }
}

@Composable
private fun V076WideLiveTv(
    vm: MainViewModel,
    accent: Color,
    categories: List<MediaCategory>,
    selectedCategory: MediaCategory?,
    channels: List<MediaEntry>,
    selectedChannel: MediaEntry?,
    onCategory: (MediaCategory) -> Unit,
    onChannelSelected: (Int, MediaEntry) -> Unit,
    onPlay: (MediaEntry) -> Unit,
    isTv: Boolean
) {
    Row(
        Modifier.fillMaxSize().padding(horizontal = if (isTv) 14.dp else 8.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(if (isTv) 10.dp else 7.dp)
    ) {
        V076CategoryPane(
            categories = categories,
            selectedId = selectedCategory?.id.orEmpty(),
            accent = accent,
            onCategory = onCategory,
            modifier = Modifier.width(if (isTv) 250.dp else 205.dp).fillMaxHeight()
        )

        V076ChannelPane(
            channels = channels,
            selectedId = selectedChannel?.id.orEmpty(),
            accent = accent,
            isTv = isTv,
            onSelected = onChannelSelected,
            onPlay = onPlay,
            modifier = Modifier.weight(1f).fillMaxHeight()
        )

        V076InfoPane(
            vm = vm,
            channel = selectedChannel,
            accent = accent,
            compact = !isTv,
            modifier = Modifier.width(if (isTv) 350.dp else 285.dp).fillMaxHeight()
        )
    }
}

@Composable
private fun V076MobileLiveTv(
    vm: MainViewModel,
    accent: Color,
    categories: List<MediaCategory>,
    selectedCategory: MediaCategory?,
    channels: List<MediaEntry>,
    selectedChannel: MediaEntry?,
    onCategory: (MediaCategory) -> Unit,
    onChannelSelected: (Int, MediaEntry) -> Unit,
    onPlay: (MediaEntry) -> Unit
) {
    Column(Modifier.fillMaxSize()) {
        LazyRow(
            Modifier.fillMaxWidth().padding(horizontal = 9.dp, vertical = 6.dp),
            horizontalArrangement = Arrangement.spacedBy(7.dp)
        ) {
            itemsIndexed(categories, key = { _, it -> it.id }) { _, category ->
                val selected = category.id == selectedCategory?.id
                Surface(
                    modifier = Modifier.clickable { onCategory(category) },
                    color = if (selected) accent.copy(.32f) else Color(0xD90A111B),
                    shape = RoundedCornerShape(12.dp),
                    border = BorderStroke(1.dp, if (selected) accent else Color.White.copy(.10f))
                ) {
                    Text(
                        category.name,
                        modifier = Modifier.padding(horizontal = 12.dp, vertical = 9.dp),
                        color = Color.White,
                        fontWeight = if (selected) FontWeight.Black else FontWeight.SemiBold,
                        fontSize = 12.sp,
                        maxLines = 1
                    )
                }
            }
        }

        V076InfoPane(
            vm = vm,
            channel = selectedChannel,
            accent = accent,
            compact = true,
            modifier = Modifier.fillMaxWidth().heightIn(min = 176.dp, max = 215.dp).padding(horizontal = 9.dp)
        )

        Spacer(Modifier.height(6.dp))

        V076ChannelPane(
            channels = channels,
            selectedId = selectedChannel?.id.orEmpty(),
            accent = accent,
            isTv = false,
            onSelected = onChannelSelected,
            onPlay = onPlay,
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 9.dp)
        )
    }
}

@Composable
private fun V076CategoryPane(
    categories: List<MediaCategory>,
    selectedId: String,
    accent: Color,
    onCategory: (MediaCategory) -> Unit,
    modifier: Modifier = Modifier
) {
    val railState = rememberLazyListState()
    val selectedIndex = categories.indexOfFirst { it.id == selectedId }.coerceAtLeast(0)
    val selectedFocus = remember(selectedId, categories.size) { FocusRequester() }

    LaunchedEffect(selectedId, categories.size) {
        if (categories.isNotEmpty()) {
            railState.scrollToItem(selectedIndex)
            delay(90)
            runCatching { selectedFocus.requestFocus() }
        }
    }

    Surface(
        modifier = modifier,
        color = Color(0xE80A1019),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.White.copy(.08f))
    ) {
        Column(Modifier.fillMaxSize()) {
            Text(
                "KATEGORIEN",
                modifier = Modifier.padding(horizontal = 13.dp, vertical = 12.dp),
                color = Color.White.copy(.58f),
                fontSize = 11.sp,
                fontWeight = FontWeight.Black
            )
            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal = 6.dp),
                state = railState,
                verticalArrangement = Arrangement.spacedBy(3.dp),
                contentPadding = PaddingValues(bottom = 12.dp)
            ) {
                itemsIndexed(categories, key = { _, it -> it.id }) { _, category ->
                    val selected = category.id == selectedId
                    V076CategoryRow(
                        title = category.name,
                        selected = selected,
                        accent = accent,
                        modifier = if (selected) Modifier.focusRequester(selectedFocus) else Modifier,
                        onSelected = { onCategory(category) }
                    )
                }
            }
        }
    }
}

@Composable
private fun V076CategoryRow(
    title: String,
    selected: Boolean,
    accent: Color,
    modifier: Modifier = Modifier,
    onSelected: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(10.dp)
    Row(
        modifier.fillMaxWidth()
            .onFocusChanged {
                focused = it.isFocused
                if (it.isFocused) onSelected()
            }
            .focusable()
            .background(
                when {
                    focused -> Brush.horizontalGradient(listOf(accent.copy(.48f), accent.copy(.18f)))
                    selected -> Brush.horizontalGradient(listOf(accent.copy(.25f), Color.Transparent))
                    else -> Brush.horizontalGradient(listOf(Color.Transparent, Color.Transparent))
                },
                shape
            )
            .clickable(onClick = onSelected)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(
            Modifier.width(if (focused || selected) 4.dp else 2.dp).height(25.dp)
                .background(if (focused || selected) accent else Color.White.copy(.16f), RoundedCornerShape(99.dp))
        )
        Spacer(Modifier.width(9.dp))
        Text(
            title,
            color = if (focused || selected) Color.White else Color.White.copy(.72f),
            fontSize = 13.sp,
            fontWeight = if (focused || selected) FontWeight.Black else FontWeight.SemiBold,
            maxLines = 1,
            overflow = TextOverflow.Ellipsis
        )
    }
}

@Composable
private fun V076ChannelPane(
    channels: List<MediaEntry>,
    selectedId: String,
    accent: Color,
    isTv: Boolean,
    onSelected: (Int, MediaEntry) -> Unit,
    onPlay: (MediaEntry) -> Unit,
    modifier: Modifier = Modifier
) {
    val state = rememberLazyListState()
    val selectedIndex = channels.indexOfFirst { it.id == selectedId }
    LaunchedEffect(selectedId, channels.size) {
        if (selectedIndex >= 0) state.scrollToItem(selectedIndex)
    }
    Surface(
        modifier = modifier,
        color = Color(0xE80A1019),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.White.copy(.08f))
    ) {
        if (channels.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Keine Sender in dieser Kategorie", color = Color.White.copy(.62f))
            }
        } else {
            LazyColumn(
                state = state,
                modifier = Modifier.fillMaxSize().padding(5.dp),
                verticalArrangement = Arrangement.spacedBy(3.dp),
                contentPadding = PaddingValues(bottom = 14.dp)
            ) {
                itemsIndexed(channels, key = { _, m -> m.sourceProfileId + "|" + m.id }) { index, media ->
                    V076ChannelRow(
                        number = index + 1,
                        media = media,
                        selected = media.id == selectedId,
                        accent = accent,
                        isTv = isTv,
                        onSelected = { onSelected(index, media) },
                        onPlay = { onSelected(index, media); onPlay(media) }
                    )
                }
            }
        }
    }
}

@Composable
private fun V076ChannelRow(
    number: Int,
    media: MediaEntry,
    selected: Boolean,
    accent: Color,
    isTv: Boolean,
    onSelected: () -> Unit,
    onPlay: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val active = focused || selected
    val epgHeight = if (isTv) 55.dp else 58.dp
    Surface(
        modifier = Modifier.fillMaxWidth()
            .onFocusChanged {
                focused = it.isFocused
                if (it.isFocused) onSelected()
            }
            .focusable()
            .clickable(onClick = onPlay),
        color = if (active) accent.copy(if (focused) .42f else .23f) else Color(0xA80D1520),
        shape = RoundedCornerShape(8.dp),
        border = BorderStroke(if (focused) 2.dp else 1.dp, if (focused) Color.White else Color.White.copy(.06f))
    ) {
        Row(
            Modifier.fillMaxWidth().height(epgHeight).padding(horizontal = 8.dp, vertical = 5.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Text(
                number.toString(),
                modifier = Modifier.width(32.dp),
                color = if (active) Color.White else Color.White.copy(.58f),
                fontSize = 12.sp,
                fontWeight = FontWeight.Black
            )
            Surface(
                modifier = Modifier.width(if (isTv) 52.dp else 58.dp).fillMaxHeight(),
                color = Color.White,
                shape = RoundedCornerShape(6.dp)
            ) {
                if (media.image.isNotBlank()) {
                    AsyncImage(
                        model = media.image,
                        contentDescription = media.name,
                        modifier = Modifier.fillMaxSize().padding(4.dp),
                        contentScale = ContentScale.Fit
                    )
                } else {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("TV", color = accent, fontWeight = FontWeight.Black, fontSize = 12.sp)
                    }
                }
            }
            Spacer(Modifier.width(9.dp))
            Text(
                media.name,
                modifier = Modifier.weight(1f),
                color = Color.White,
                fontSize = if (isTv) 15.sp else 14.sp,
                fontWeight = if (active) FontWeight.Black else FontWeight.SemiBold,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
            if (active) {
                Text("LIVE", color = Color.White, fontSize = 9.sp, fontWeight = FontWeight.Black)
            }
        }
    }
}

@Composable
private fun V076InfoPane(
    vm: MainViewModel,
    channel: MediaEntry?,
    accent: Color,
    compact: Boolean,
    modifier: Modifier = Modifier
) {
    val u by vm.ui.collectAsState()
    val epg = channel?.let { u.epg[it.id].orEmpty() }.orEmpty()
    val now = System.currentTimeMillis() / 1000L
    val currentIndex = epg.indexOfFirst { now >= it.start && now < it.end }
    val current = if (currentIndex >= 0) epg[currentIndex] else epg.firstOrNull()
    val next = if (currentIndex >= 0) epg.getOrNull(currentIndex + 1) else epg.getOrNull(1)
    val progress = current?.let {
        val duration = (it.end - it.start).coerceAtLeast(1L)
        ((now - it.start).toFloat() / duration.toFloat()).coerceIn(0f, 1f)
    } ?: 0f

    Surface(
        modifier = modifier,
        color = Color(0xE80A1019),
        shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.White.copy(.08f))
    ) {
        if (channel == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Sender auswählen", color = Color.White.copy(.58f))
            }
        } else {
            Column(Modifier.fillMaxSize().padding(if (compact) 11.dp else 14.dp)) {
                Surface(
                    modifier = Modifier.fillMaxWidth().height(if (compact) 80.dp else 150.dp),
                    color = Color(0xFF111925),
                    shape = RoundedCornerShape(10.dp)
                ) {
                    Box(Modifier.fillMaxSize()) {
                        if (channel.image.isNotBlank()) {
                            AsyncImage(
                                model = channel.image,
                                contentDescription = channel.name,
                                modifier = Modifier.fillMaxSize().padding(if (compact) 10.dp else 18.dp),
                                contentScale = ContentScale.Fit
                            )
                        } else {
                            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                Text("LIVE TV", color = accent, fontSize = if (compact) 18.sp else 26.sp, fontWeight = FontWeight.Black)
                            }
                        }
                        Surface(
                            modifier = Modifier.align(Alignment.TopEnd).padding(7.dp),
                            color = accent,
                            shape = RoundedCornerShape(6.dp)
                        ) {
                            Text("LIVE", Modifier.padding(horizontal = 8.dp, vertical = 4.dp), color = Color.White, fontSize = 9.sp, fontWeight = FontWeight.Black)
                        }
                    }
                }

                Spacer(Modifier.height(if (compact) 8.dp else 12.dp))
                Text(
                    channel.name,
                    color = Color.White,
                    fontSize = if (compact) 17.sp else 21.sp,
                    fontWeight = FontWeight.Black,
                    maxLines = 1,
                    overflow = TextOverflow.Ellipsis
                )

                if (current != null) {
                    Text(
                        "${V076Clock(current.start)} – ${V076Clock(current.end)}",
                        color = accent,
                        fontSize = if (compact) 11.sp else 12.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier.padding(top = 4.dp)
                    )
                    Text(
                        current.title,
                        color = Color.White,
                        fontSize = if (compact) 13.sp else 15.sp,
                        fontWeight = FontWeight.Bold,
                        maxLines = if (compact) 1 else 2,
                        overflow = TextOverflow.Ellipsis
                    )
                    LinearProgressIndicator(
                        progress = { progress },
                        modifier = Modifier.fillMaxWidth().padding(top = 7.dp).height(3.dp).clip(RoundedCornerShape(99.dp)),
                        color = accent,
                        trackColor = Color.White.copy(.10f)
                    )
                } else {
                    Text("Keine EPG-Daten verfügbar", color = Color.White.copy(.60f), fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp))
                }

                if (!compact) {
                    Spacer(Modifier.height(12.dp))
                    HorizontalDivider(color = Color.White.copy(.08f))
                    Spacer(Modifier.height(10.dp))
                    Text("PROGRAMM", color = Color.White.copy(.46f), fontSize = 10.sp, fontWeight = FontWeight.Black)
                    current?.let {
                        V076ProgrammeLine(V076Clock(it.start), it.title, true, accent)
                    }
                    next?.let {
                        V076ProgrammeLine(V076Clock(it.start), it.title, false, accent)
                    }
                    if (!current?.description.isNullOrBlank()) {
                        Text(
                            current?.description.orEmpty(),
                            color = Color.White.copy(.58f),
                            fontSize = 11.sp,
                            maxLines = 4,
                            overflow = TextOverflow.Ellipsis,
                            modifier = Modifier.padding(top = 9.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun V076ProgrammeLine(time: String, title: String, current: Boolean, accent: Color) {
    Row(Modifier.fillMaxWidth().padding(top = 7.dp), verticalAlignment = Alignment.Top) {
        Text(time, color = if (current) accent else Color.White.copy(.55f), fontSize = 11.sp, fontWeight = FontWeight.Black, modifier = Modifier.width(48.dp))
        Text(title, color = if (current) Color.White else Color.White.copy(.70f), fontSize = 11.sp, fontWeight = if (current) FontWeight.Bold else FontWeight.Medium, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

private fun V076Clock(epochSeconds: Long): String =
    SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(epochSeconds * 1000L))
