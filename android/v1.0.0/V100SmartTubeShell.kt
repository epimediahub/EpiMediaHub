package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.launch

@Composable
fun V100SmartTubeShell(
    vm: MainViewModel,
    accent: Color,
    isTv: Boolean,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var rows by remember { mutableStateOf<List<V100SmartTubeRow>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    var searchDialog by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var resolvingId by remember { mutableStateOf<String?>(null) }
    var generation by remember { mutableIntStateOf(0) }

    fun loadHome() {
        generation++
        loading = true
        error = ""
    }

    fun play(video: V100SmartTubeVideo) {
        if (resolvingId != null) return
        resolvingId = video.videoId
        error = ""
        scope.launch {
            V100SmartTubeCore.resolvePlayback(context, video)
                .onSuccess { playback ->
                    resolvingId = null
                    vm.play(
                        MediaEntry(
                            id = "smarttube:${video.videoId}",
                            name = video.title,
                            kind = MediaKind.MOVIE,
                            categoryId = "smarttube",
                            image = video.image,
                            plot = video.author,
                            streamUrl = playback.url,
                            extension = playback.extension
                        )
                    )
                }
                .onFailure {
                    resolvingId = null
                    error = it.message ?: "SmartTube-Wiedergabe konnte nicht gestartet werden."
                }
        }
    }

    LaunchedEffect(generation) {
        loading = true
        V100SmartTubeCore.home(context)
            .onSuccess {
                rows = it
                error = if (it.isEmpty()) "SmartTube hat momentan keine Startseiten-Inhalte geliefert." else ""
            }
            .onFailure { error = it.message ?: "SmartTube konnte nicht geladen werden." }
        loading = false
    }

    BackHandler(onBack = onBack)

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            "SMARTTUBE",
            R.drawable.brand_header,
            onBack,
            actions = {
                TextButton(onClick = { searchDialog = true }) {
                    Icon(Icons.Default.Search, null, tint = accent)
                    Spacer(Modifier.width(6.dp))
                    Text("SUCHE", color = Color.White, fontWeight = FontWeight.Black)
                }
                TextButton(onClick = { loadHome() }) {
                    Icon(Icons.Default.Refresh, null, tint = accent)
                }
            }
        )

        if (loading && rows.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Column(horizontalAlignment = Alignment.CenterHorizontally) {
                    CircularProgressIndicator(color = accent)
                    Spacer(Modifier.height(14.dp))
                    Text("SmartTube wird geladen …", color = Color.White, fontWeight = FontWeight.Bold)
                }
            }
        } else {
            LazyColumn(
                Modifier.fillMaxSize().background(
                    Brush.verticalGradient(listOf(Color(0xA5090D13), Color(0xD905070B)))
                ),
                contentPadding = PaddingValues(
                    start = if (isTv) 34.dp else 12.dp,
                    end = if (isTv) 34.dp else 12.dp,
                    top = 12.dp,
                    bottom = 30.dp
                ),
                verticalArrangement = Arrangement.spacedBy(if (isTv) 22.dp else 15.dp)
            ) {
                if (error.isNotBlank()) {
                    item(key = "smarttube-error") {
                        Surface(
                            color = Color(0xD519202A),
                            shape = RoundedCornerShape(13.dp),
                            border = BorderStroke(1.dp, accent.copy(.48f))
                        ) {
                            Text(
                                error,
                                color = Color.White.copy(.88f),
                                modifier = Modifier.padding(14.dp),
                                fontSize = if (isTv) 14.sp else 12.sp
                            )
                        }
                    }
                }

                items(rows, key = { "st-row:" + it.title }) { row ->
                    V100SmartTubeRowView(
                        row = row,
                        accent = accent,
                        isTv = isTv,
                        resolvingId = resolvingId,
                        onVideo = ::play
                    )
                }
            }
        }
    }

    if (searchDialog) {
        AlertDialog(
            onDismissRequest = { searchDialog = false },
            title = { Text("SmartTube durchsuchen") },
            text = {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    singleLine = true,
                    label = { Text("YouTube-Suche") },
                    leadingIcon = { Icon(Icons.Default.Search, null) }
                )
            },
            confirmButton = {
                Button(
                    onClick = {
                        val needle = query.trim()
                        if (needle.isBlank()) return@Button
                        searchDialog = false
                        loading = true
                        error = ""
                        scope.launch {
                            V100SmartTubeCore.search(context, needle)
                                .onSuccess {
                                    rows = it
                                    error = if (it.isEmpty()) "Keine Treffer für „$needle“." else ""
                                }
                                .onFailure { error = it.message ?: "SmartTube-Suche fehlgeschlagen." }
                            loading = false
                        }
                    }
                ) { Text("Suchen") }
            },
            dismissButton = {
                TextButton(onClick = { searchDialog = false }) { Text("Abbrechen") }
            }
        )
    }
}

@Composable
private fun V100SmartTubeRowView(
    row: V100SmartTubeRow,
    accent: Color,
    isTv: Boolean,
    resolvingId: String?,
    onVideo: (V100SmartTubeVideo) -> Unit
) {
    Column {
        Text(
            row.title.uppercase(),
            color = Color.White,
            fontSize = if (isTv) 18.sp else 14.sp,
            fontWeight = FontWeight.Black,
            letterSpacing = .5.sp,
            modifier = Modifier.padding(start = 2.dp, bottom = 9.dp)
        )
        LazyRow(horizontalArrangement = Arrangement.spacedBy(if (isTv) 12.dp else 8.dp)) {
            items(row.videos, key = { it.videoId }) { video ->
                V100SmartTubeVideoCard(
                    video = video,
                    accent = accent,
                    isTv = isTv,
                    resolving = resolvingId == video.videoId,
                    onClick = { onVideo(video) }
                )
            }
        }
    }
}

@Composable
private fun V100SmartTubeVideoCard(
    video: V100SmartTubeVideo,
    accent: Color,
    isTv: Boolean,
    resolving: Boolean,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val width = if (isTv) 250.dp else 178.dp
    val imageHeight = if (isTv) 140.dp else 100.dp
    val shape = RoundedCornerShape(if (isTv) 15.dp else 12.dp)

    Surface(
        modifier = Modifier
            .width(width)
            .onFocusChanged { focused = it.isFocused }
            .focusable()
            .clickable(onClick = onClick),
        color = if (focused) accent.copy(.20f) else Color(0xDC101720),
        shape = shape,
        border = BorderStroke(
            if (focused) 2.dp else 1.dp,
            if (focused) Color.White else Color.White.copy(.12f)
        )
    ) {
        Column {
            Box(Modifier.fillMaxWidth().height(imageHeight)) {
                if (video.image.isNotBlank()) {
                    AsyncImage(
                        model = video.image,
                        contentDescription = video.title,
                        modifier = Modifier.fillMaxSize(),
                        contentScale = ContentScale.Crop
                    )
                } else {
                    Box(
                        Modifier.fillMaxSize().background(Color(0xFF18222E)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("YouTube", color = accent, fontWeight = FontWeight.Black)
                    }
                }
                if (video.live) {
                    Text(
                        "LIVE",
                        color = Color.White,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier.align(Alignment.BottomStart)
                            .padding(7.dp)
                            .background(Color(0xD9B5161E), RoundedCornerShape(5.dp))
                            .padding(horizontal = 6.dp, vertical = 3.dp)
                    )
                }
                if (resolving) {
                    Box(
                        Modifier.fillMaxSize().background(Color.Black.copy(.58f)),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(if (isTv) 30.dp else 24.dp),
                            color = Color.White,
                            strokeWidth = 2.dp
                        )
                    }
                }
            }
            Column(Modifier.padding(horizontal = 10.dp, vertical = 9.dp)) {
                Text(
                    video.title,
                    color = Color.White,
                    fontSize = if (isTv) 14.sp else 12.sp,
                    fontWeight = FontWeight.Bold,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis,
                    lineHeight = if (isTv) 17.sp else 14.sp
                )
                if (video.author.isNotBlank()) {
                    Spacer(Modifier.height(3.dp))
                    Text(
                        video.author,
                        color = Color.White.copy(.58f),
                        fontSize = if (isTv) 11.sp else 9.sp,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                }
            }
        }
    }
}
