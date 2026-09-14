package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Public
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.*
import de.epimediahub.app.R
import de.epimediahub.app.data.EpgParityClient
import de.epimediahub.app.data.MediathekClient
import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import de.epimediahub.app.model.PlaylistType
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

@Composable
fun ParityMediathekHomeScreen(vm: MainViewModel, accent: Color, isTv: Boolean) {
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar("MEDIATHEK", R.drawable.brand_header, { vm.back() }, actions = { Text("Nach Land", color = accent, fontWeight = FontWeight.Bold) })
        LazyVerticalGrid(
            columns = GridCells.Fixed(if (isTv) 3 else 2),
            modifier = Modifier.fillMaxSize().padding(16.dp),
            horizontalArrangement = Arrangement.spacedBy(12.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            gridItems(MediathekClient.countries, key = { it.id }) { country ->
                ParityDirectoryCard(country.label, country.meta, country.info, accent) {
                    vm.navigate(ParityMediathekDirectory(country.id))
                }
            }
        }
    }
}

@Composable
fun ParityMediathekDirectoryScreen(vm: MainViewModel, countryId: String, accent: Color, isTv: Boolean) {
    val country = MediathekClient.countries.firstOrNull { it.id == countryId }
    val providers = remember(countryId) { MediathekClient.providers(countryId) }
    BackHandler { vm.back() }
    Column(Modifier.fillMaxSize()) {
        EpiTopBar(country?.label ?: "MEDIATHEK", R.drawable.brand_header, { vm.back() }, actions = { Text("Anbieter", color = accent, fontWeight = FontWeight.Bold) })
        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal = if (isTv) 70.dp else 14.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = PaddingValues(bottom = 28.dp)
        ) {
            items(providers, key = { it.id }) { provider ->
                ParityProviderRow(provider, accent) { vm.navigate(ParityMediathekList(provider.id)) }
            }
        }
    }
}

@Composable
fun ParityMediathekListScreen(vm: MainViewModel, providerId: String, accent: Color, isTv: Boolean) {
    val provider = remember(providerId) { MediathekClient.provider(providerId) }
    var query by remember { mutableStateOf("") }
    var submitted by remember { mutableStateOf("") }
    var reload by remember { mutableIntStateOf(0) }
    var loading by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf("") }
    var entries by remember { mutableStateOf<List<MediaEntry>>(emptyList()) }
    BackHandler { vm.back() }

    LaunchedEffect(providerId, submitted, reload) {
        val p = provider ?: return@LaunchedEffect
        if (!p.playable) {
            entries = emptyList()
            error = p.info.ifBlank { "Für diesen Anbieter ist derzeit keine stabile offene Stream-Schnittstelle verfügbar." }
            return@LaunchedEffect
        }
        loading = true
        error = ""
        runCatching { withContext(Dispatchers.IO) { MediathekClient.query(p, submitted) } }
            .onSuccess { entries = it; if (it.isEmpty()) error = "Keine abspielbaren Beiträge gefunden." }
            .onFailure { error = it.message ?: "Mediathek konnte nicht geladen werden." }
        loading = false
    }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(provider?.label ?: "MEDIATHEK", R.drawable.brand_header, { vm.back() }, actions = {
            provider?.availability?.takeIf { it.isNotBlank() }?.let { Text(it, color = Color.White.copy(.55f), fontSize = 12.sp) }
        })
        Row(
            Modifier.fillMaxWidth().padding(horizontal = if (isTv) 60.dp else 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = query,
                onValueChange = { query = it },
                label = { Text("Mediathek durchsuchen") },
                leadingIcon = { Icon(Icons.Default.Search, null) },
                singleLine = true,
                modifier = Modifier.weight(1f)
            )
            Button(onClick = { submitted = query.trim(); reload++ }, colors = ButtonDefaults.buttonColors(containerColor = accent)) { Text("Suchen") }
            OutlinedButton(onClick = { reload++ }) { Text("Neu laden") }
        }
        if (loading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        if (error.isNotBlank() && entries.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                GlassPanel(Modifier.fillMaxWidth(.86f).widthIn(max = 760.dp)) {
                    Column(Modifier.padding(24.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                        Icon(Icons.Default.Public, null, tint = accent, modifier = Modifier.size(46.dp))
                        Text(provider?.label ?: "Mediathek", fontSize = 24.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(top = 10.dp))
                        Text(error, color = Color.White.copy(.68f), modifier = Modifier.padding(top = 8.dp))
                        provider?.info?.takeIf { it.isNotBlank() && it != error }?.let { Text(it, color = Color.White.copy(.52f), fontSize = 12.sp, modifier = Modifier.padding(top = 8.dp)) }
                    }
                }
            }
        } else {
            LazyVerticalGrid(
                columns = GridCells.Fixed(if (isTv) 5 else 2),
                modifier = Modifier.fillMaxSize().padding(12.dp),
                horizontalArrangement = Arrangement.spacedBy(10.dp),
                verticalArrangement = Arrangement.spacedBy(10.dp),
                contentPadding = PaddingValues(bottom = 24.dp)
            ) {
                gridItems(entries, key = { it.id }) { media ->
                    MediaCard(media, accent, media.plot) { vm.play(media) }
                }
            }
        }
    }
}

@Composable
fun ParityEpgGridScreen(vm: MainViewModel, category: de.epimediahub.app.model.MediaCategory, accent: Color, isTv: Boolean) {
    val u by vm.ui.collectAsState()
    val profile = u.active
    var fullEpg by remember(profile?.id, category.id) { mutableStateOf<Map<String, List<EpgItem>>>(emptyMap()) }
    val now = System.currentTimeMillis() / 1000L
    BackHandler { vm.back() }

    Column(Modifier.fillMaxSize()) {
        EpiTopBar("EPG · ${category.name}", R.drawable.brand_header, { vm.back() }, actions = {
            Text(if (profile?.type == PlaylistType.XTREAM) "Voll-EPG · Catch-up" else "XMLTV", color = accent, fontWeight = FontWeight.Bold)
        })
        if (u.epgLoading) LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal = if (isTv) 24.dp else 10.dp, vertical = 8.dp),
            verticalArrangement = Arrangement.spacedBy(10.dp),
            contentPadding = PaddingValues(bottom = 28.dp)
        ) {
            items(u.items, key = { it.id }) { channel ->
                LaunchedEffect(profile?.id, channel.id) {
                    if (profile?.type == PlaylistType.XTREAM) {
                        val list = runCatching { withContext(Dispatchers.IO) { EpgParityClient.fullEpg(profile, channel.id) } }.getOrDefault(emptyList())
                        if (list.isNotEmpty()) fullEpg = fullEpg + (channel.id to list)
                    } else if (u.epg[channel.id].isNullOrEmpty()) {
                        vm.ensureEpg(channel)
                    }
                }
                val all = fullEpg[channel.id] ?: u.epg[channel.id].orEmpty()
                val window = all.filter { it.end >= now - 48L * 3600L && it.start <= now + 18L * 3600L }.sortedBy { it.start }
                ParityEpgChannel(vm, profile, channel, window, now, accent)
            }
        }
    }
}

@Composable
private fun ParityEpgChannel(
    vm: MainViewModel,
    profile: de.epimediahub.app.model.PlaylistProfile?,
    channel: MediaEntry,
    events: List<EpgItem>,
    now: Long,
    accent: Color
) {
    GlassPanel(Modifier.fillMaxWidth()) {
        Column(Modifier.fillMaxWidth().padding(14.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(channel.name, fontSize = 18.sp, fontWeight = FontWeight.Black, color = accent, modifier = Modifier.weight(1f))
                Text(if (channel.tvArchive) "ARCHIV ${channel.tvArchiveDurationDays}T" else "LIVE", fontSize = 11.sp, color = Color.White.copy(.55f), fontWeight = FontWeight.Bold)
            }
            Spacer(Modifier.height(8.dp))
            if (events.isEmpty()) {
                Text("Keine EPG-Daten verfügbar.", color = Color.White.copy(.52f))
            } else {
                events.takeLast(12).forEach { event ->
                    val isLive = event.start <= now && event.end > now
                    val replay = profile?.let { EpgParityClient.catchupAvailable(it, channel, event) } == true
                    val canPlay = isLive || replay
                    var focused by remember(channel.id, event.start) { mutableStateOf(false) }
                    val shape = RoundedCornerShape(12.dp)
                    Row(
                        Modifier.fillMaxWidth()
                            .onFocusChanged { focused = it.isFocused }
                            .then(if (canPlay) Modifier.focusable().clickable {
                                if (replay && profile != null) {
                                    val url = EpgParityClient.catchupUrl(profile, channel, event)
                                    if (url.isNotBlank()) vm.play(channel.copy(id = "catchup:${channel.id}:${event.start}", name = "${channel.name} · ${event.title}", streamUrl = url, kind = MediaKind.LIVE))
                                } else if (isLive) vm.play(channel)
                            } else Modifier)
                            .background(if (focused) accent.copy(.18f) else Color.Transparent, shape)
                            .border(1.dp, if (focused) accent else Color.White.copy(.06f), shape)
                            .padding(horizontal = 10.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.Top
                    ) {
                        Text("${parityClock(event.start)}–${parityClock(event.end)}", fontSize = 12.sp, color = Color.White.copy(.56f), modifier = Modifier.width(92.dp))
                        Column(Modifier.weight(1f)) {
                            Text(event.title, fontWeight = if (isLive) FontWeight.Black else FontWeight.SemiBold, maxLines = 2)
                            if (event.description.isNotBlank()) Text(event.description, color = Color.White.copy(.48f), fontSize = 11.sp, maxLines = 2)
                        }
                        when {
                            replay -> Text("REPLAY", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(start = 8.dp))
                            isLive -> Text("LIVE", color = accent, fontSize = 11.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(start = 8.dp))
                            event.start > now -> Text("SPÄTER", color = Color.White.copy(.42f), fontSize = 10.sp, modifier = Modifier.padding(start = 8.dp))
                        }
                    }
                    Spacer(Modifier.height(5.dp))
                }
            }
        }
    }
}

@Composable
private fun ParityDirectoryCard(title: String, meta: String, info: String, accent: Color, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(20.dp)
    Column(
        Modifier.heightIn(min = 150.dp).onFocusChanged { focused = it.isFocused }.focusable()
            .background(Color(0xE80B1624), shape)
            .border(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.10f), shape)
            .clickable(onClick = onClick).padding(18.dp),
        verticalArrangement = Arrangement.SpaceBetween
    ) {
        Icon(Icons.Default.Public, null, tint = accent, modifier = Modifier.size(34.dp))
        Column {
            Text(title, fontSize = 20.sp, fontWeight = FontWeight.Black)
            Text(meta, color = accent.copy(.90f), fontSize = 12.sp, fontWeight = FontWeight.Bold, modifier = Modifier.padding(top = 4.dp))
            Text(info, color = Color.White.copy(.52f), fontSize = 11.sp, maxLines = 2, modifier = Modifier.padding(top = 4.dp))
        }
    }
}

@Composable
private fun ParityProviderRow(provider: MediathekClient.Provider, accent: Color, onClick: () -> Unit) {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(16.dp)
    Row(
        Modifier.fillMaxWidth().onFocusChanged { focused = it.isFocused }.focusable()
            .background(if (focused) accent.copy(.18f) else Color(0xE80B1624), shape)
            .border(if (focused) 2.dp else 1.dp, if (focused) accent else Color.White.copy(.09f), shape)
            .clickable(onClick = onClick).padding(15.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.size(42.dp).background(accent.copy(.14f), RoundedCornerShape(12.dp)), contentAlignment = Alignment.Center) {
            Icon(if (provider.playable) Icons.Default.PlayArrow else Icons.Default.Public, null, tint = accent)
        }
        Spacer(Modifier.width(13.dp))
        Column(Modifier.weight(1f)) {
            Text(provider.label, fontWeight = FontWeight.Black, fontSize = 17.sp)
            if (provider.availability.isNotBlank()) Text(provider.availability, color = accent.copy(.85f), fontSize = 11.sp, fontWeight = FontWeight.Bold)
            if (provider.info.isNotBlank()) Text(provider.info, color = Color.White.copy(.48f), fontSize = 11.sp, maxLines = 2)
        }
    }
}
