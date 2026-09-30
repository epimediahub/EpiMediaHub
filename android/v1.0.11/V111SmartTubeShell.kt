package de.epimediahub.app.ui

import android.os.Build
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Home
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Search
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
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
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import io.reactivex.disposables.Disposable
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
fun V111SmartTubeShell(
    vm: MainViewModel,
    accent: Color,
    isTv: Boolean,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val legacyFireTvKeyboard = remember {
        v110NeedsLegacyFireTvKeyboard()
    }
    val ui by vm.ui.collectAsState()
    val legacyFireTvIme = isTv && Build.VERSION.SDK_INT <= 25
    val activeTheme = ui.themeCatalog?.themes?.get(ui.themeId)
    val smartTubeSkinMark = remember(ui.themeId) {
        vm.themeRepo().officialMarkRes(ui.themeId).takeIf { it != 0 }
            ?: vm.themeRepo().markRes(ui.themeId)
    }
    val smartTubeSkinWorld = remember(ui.themeId, activeTheme?.label, activeTheme?.group) {
        V097SkinWorldFor(
            ui.themeId,
            activeTheme?.label.orEmpty(),
            activeTheme?.group.orEmpty()
        )
    }

    val smartTubeMenuKey = "smarttube-section"
    var selectedSection by remember {
        mutableStateOf(
            V108SmartTubeSection.entries.firstOrNull {
                it.name == V111MenuMemory.id(smartTubeMenuKey)
            } ?: V108SmartTubeSection.HOME
        )
    }
    val smartTubeMainListState = v111RememberLazyListState("smarttube-main")
    var rows by remember { mutableStateOf<List<V100SmartTubeRow>>(emptyList()) }
    var loading by remember { mutableStateOf(true) }
    var error by remember { mutableStateOf("") }
    var generation by remember { mutableIntStateOf(0) }
    var searchTitle by remember { mutableStateOf("") }

    var searchDialog by remember { mutableStateOf(false) }
    var query by remember { mutableStateOf("") }
    var resolvingId by remember { mutableStateOf<String?>(null) }
    var activePlayback by remember {
        mutableStateOf<Pair<V100SmartTubeVideo, V100SmartTubePlayback>?>(null)
    }

    var auth by remember { mutableStateOf(V108SmartTubeAuthState(false, "")) }
    var accountDialog by remember { mutableStateOf(false) }
    var signInCode by remember { mutableStateOf("") }
    var signInError by remember { mutableStateOf("") }
    var signingIn by remember { mutableStateOf(false) }
    var signInDisposable by remember { mutableStateOf<Disposable?>(null) }

    fun reloadSection(section: V108SmartTubeSection = selectedSection) {
        selectedSection = section
        V111MenuMemory.remember(smartTubeMenuKey, section.ordinal, section.name)
        searchTitle = ""
        error = ""
        loading = true
        generation++
    }

    fun play(video: V100SmartTubeVideo) {
        if (resolvingId != null) return
        resolvingId = video.videoId
        error = ""
        scope.launch {
            V108SmartTubeCore.resolvePlayback(context, video)
                .onSuccess { playback ->
                    resolvingId = null
                    activePlayback = video to playback
                }
                .onFailure {
                    resolvingId = null
                    error = it.message ?: "SmartTube-Wiedergabe konnte nicht gestartet werden."
                }
        }
    }

    fun nextVideoAfter(video: V100SmartTubeVideo): V100SmartTubeVideo? {
        val queue = rows
            .flatMap { it.videos }
            .distinctBy { it.videoId }
        val index = queue.indexOfFirst { it.videoId == video.videoId }
        return if (index >= 0) queue.getOrNull(index + 1) else null
    }

    fun submitSearch(raw: String) {
        val needle = raw.trim()
        if (needle.isBlank()) return
        searchDialog = false
        loading = true
        error = ""
        searchTitle = "Suche · $needle"
        scope.launch {
            V108SmartTubeCore.search(context, needle)
                .onSuccess {
                    rows = it
                    error = if (it.isEmpty()) "Keine Treffer für „$needle“." else ""
                }
                .onFailure {
                    error = it.message ?: "SmartTube-Suche fehlgeschlagen."
                }
            loading = false
        }
    }

    fun beginSignIn() {
        if (signingIn) return
        signInDisposable?.dispose()
        signInCode = ""
        signInError = ""
        signingIn = true
        signInDisposable = V108SmartTubeCore.signInObserve(context).subscribe(
            { code ->
                scope.launch {
                    signInCode = code.trim()
                    signInError = ""
                }
            },
            { failure ->
                scope.launch {
                    signingIn = false
                    signInError = failure.message ?: "YouTube-Anmeldung fehlgeschlagen."
                }
            },
            {
                scope.launch {
                    signingIn = false
                    auth = V108SmartTubeCore.authState(context)
                    accountDialog = false
                    signInCode = ""
                    reloadSection(selectedSection)
                }
            }
        )
    }

    DisposableEffect(Unit) {
        onDispose { signInDisposable?.dispose() }
    }

    LaunchedEffect(Unit) {
        auth = V108SmartTubeCore.authState(context)
    }

    LaunchedEffect(selectedSection, generation) {
        if (searchTitle.isNotBlank()) return@LaunchedEffect
        loading = true
        V108SmartTubeCore.section(context, selectedSection)
            .onSuccess {
                rows = it
                error = if (it.isEmpty()) {
                    "Für „${selectedSection.label}“ wurden momentan keine Inhalte geliefert."
                } else ""
            }
            .onFailure {
                error = it.message ?: "SmartTube konnte „${selectedSection.label}“ nicht laden."
            }
        auth = V108SmartTubeCore.authState(context)
        loading = false
    }

    activePlayback?.let { (video, playback) ->
        V111SmartTubePlayer(
            video = video,
            playback = playback,
            accent = accent,
            onBack = { activePlayback = null },
            onEnded = {
                nextVideoAfter(video)?.let { next ->
                    play(next)
                }
            }
        )
        return
    }

    BackHandler {
        if (searchTitle.isNotBlank()) {
            reloadSection(selectedSection)
        } else {
            onBack()
        }
    }

    val smartTubeContentState = v111RememberLazyListState(
        "smarttube-content:" + selectedSection.name
    )

    Column(Modifier.fillMaxSize()) {
        Surface(
            modifier = Modifier.fillMaxWidth().height(if (isTv) 72.dp else 58.dp),
            color = Color(0xF20B0B0B),
            tonalElevation = 0.dp
        ) {
            Row(
                Modifier.fillMaxSize().padding(horizontal = if (isTv) 18.dp else 9.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                V111HeaderIcon(
                    icon = { Icon(Icons.Default.ArrowBack, null, tint = Color.White) },
                    onClick = onBack
                )
                Spacer(Modifier.width(if (isTv) 14.dp else 8.dp))
                Surface(
                    color = Color(0xFFE62117),
                    shape = RoundedCornerShape(7.dp)
                ) {
                    Text(
                        "▶",
                        color = Color.White,
                        fontSize = if (isTv) 18.sp else 14.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier.padding(horizontal = 9.dp, vertical = 4.dp)
                    )
                }
                Spacer(Modifier.width(9.dp))
                Text(
                    "SmartTube",
                    color = Color.White,
                    fontSize = if (isTv) 24.sp else 19.sp,
                    fontWeight = FontWeight.Black
                )
                Spacer(Modifier.weight(1f))
                V111HeaderIcon(
                    icon = { Icon(Icons.Default.Search, null, tint = Color.White) },
                    onClick = { searchDialog = true }
                )
                Spacer(Modifier.width(7.dp))
                V111HeaderIcon(
                    icon = { Icon(Icons.Default.Refresh, null, tint = Color.White) },
                    onClick = { reloadSection(selectedSection) }
                )
                Spacer(Modifier.width(9.dp))
                V111AccountPill(
                    label = if (auth.signed) auth.accountName.ifBlank { "Konto" } else "Anmelden",
                    accent = accent,
                    onClick = { accountDialog = true }
                )
            }
        }

        Box(
            Modifier
                .fillMaxSize()
                .background(Color(0xFF05070B))
        ) {
            V097SkinEnvironment(smartTubeSkinWorld, accent)

            Box(
                Modifier
                    .fillMaxSize()
                    .background(
                        Brush.horizontalGradient(
                            listOf(
                                Color(0xD905080D),
                                Color(0xAF080C12),
                                Color(0x65070A10),
                                Color(0x2B05090D)
                            )
                        )
                    )
            )

            if (smartTubeSkinMark != 0 && ui.themeId != "default") {
                Box(
                    Modifier
                        .align(Alignment.CenterEnd)
                        .fillMaxHeight(if (isTv) .78f else .58f)
                        .fillMaxWidth(if (isTv) .46f else .44f)
                        .background(
                            Brush.radialGradient(
                                listOf(
                                    Color.White.copy(alpha = .13f),
                                    Color.Transparent
                                )
                            )
                        )
                )
                Image(
                    painter = painterResource(smartTubeSkinMark),
                    contentDescription = activeTheme?.label,
                    modifier = Modifier
                        .align(Alignment.CenterEnd)
                        .fillMaxHeight(if (isTv) .70f else .52f)
                        .fillMaxWidth(if (isTv) .40f else .38f)
                        .padding(end = if (isTv) 38.dp else 10.dp)
                        .graphicsLayer { alpha = if (isTv) .46f else .34f },
                    contentScale = ContentScale.Fit
                )
            }

            Row(Modifier.fillMaxSize()) {
            if (isTv) {
                V111SmartTubeSidebar(
                    selected = selectedSection,
                    accent = accent,
                    onSelect = { reloadSection(it) }
                )
            }

            Column(Modifier.weight(1f).fillMaxHeight()) {
                Row(
                    Modifier
                        .fillMaxWidth()
                        .padding(
                            start = if (isTv) 24.dp else 14.dp,
                            end = if (isTv) 32.dp else 14.dp,
                            top = 13.dp,
                            bottom = 8.dp
                        ),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(
                        if (searchTitle.isNotBlank()) searchTitle else selectedSection.label,
                        color = Color.White,
                        fontSize = if (isTv) 26.sp else 19.sp,
                        fontWeight = FontWeight.Black,
                        letterSpacing = .6.sp
                    )
                    if (loading) {
                        Spacer(Modifier.width(14.dp))
                        CircularProgressIndicator(
                            modifier = Modifier.size(if (isTv) 20.dp else 16.dp),
                            color = accent,
                            strokeWidth = 2.dp
                        )
                    }
                    Spacer(Modifier.weight(1f))
                    if (smartTubeSkinMark != 0 && activeTheme != null) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            modifier = Modifier.padding(start = 12.dp)
                        ) {
                            Image(
                                painter = painterResource(smartTubeSkinMark),
                                contentDescription = null,
                                modifier = Modifier.size(if (isTv) 34.dp else 24.dp),
                                contentScale = ContentScale.Fit
                            )
                            Spacer(Modifier.width(8.dp))
                            Text(
                                activeTheme.label.uppercase(),
                                color = Color.White.copy(.78f),
                                fontSize = if (isTv) 12.sp else 9.sp,
                                fontWeight = FontWeight.Black,
                                maxLines = 1
                            )
                        }
                    }
                }

                if (loading && rows.isEmpty()) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            CircularProgressIndicator(color = accent)
                            Spacer(Modifier.height(14.dp))
                            Text(
                                "SmartTube wird geladen …",
                                color = Color.White,
                                fontWeight = FontWeight.Bold
                            )
                        }
                    }
                } else {
                    LazyColumn(
                        state = smartTubeMainListState,
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(
                            start = if (isTv) 24.dp else 12.dp,
                            end = if (isTv) 34.dp else 12.dp,
                            top = 6.dp,
                            bottom = 30.dp
                        ),
                        verticalArrangement = Arrangement.spacedBy(if (isTv) 30.dp else 18.dp)
                    ) {
                        if (error.isNotBlank()) {
                            item(key = "smarttube-error") {
                                Surface(
                                    color = Color(0xD519202A),
                                    shape = RoundedCornerShape(13.dp),
                                    border = BorderStroke(1.dp, accent.copy(.55f))
                                ) {
                                    Text(
                                        error,
                                        color = Color.White.copy(.90f),
                                        modifier = Modifier.padding(14.dp),
                                        fontSize = if (isTv) 14.sp else 12.sp
                                    )
                                }
                            }
                        }

                        items(rows, key = { "st-row:" + it.title }) { row ->
                            V111SmartTubeRowView(
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
        }
        }
    }

    if (searchDialog) {
        if (legacyFireTvKeyboard) {
            V110TvKeyboardDialog(
                title = "SmartTube durchsuchen",
                initialValue = query,
                accent = accent,
                onDismiss = { searchDialog = false },
                onValueChange = { query = it },
                onSubmit = { value ->
                    query = value
                    submitSearch(value)
                }
            )
        } else {
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
                    Button(onClick = { submitSearch(query) }) { Text("Suchen") }
                },
                dismissButton = {
                    TextButton(onClick = { searchDialog = false }) { Text("Abbrechen") }
                }
            )
        }
    }

    if (accountDialog) {
        AlertDialog(
            onDismissRequest = {
                if (!signingIn) accountDialog = false
            },
            title = { Text(if (auth.signed) "YouTube-Konto" else "YouTube anmelden") },
            text = {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    if (auth.signed) {
                        Text("Angemeldet als ${auth.accountName.ifBlank { "YouTube-Konto" }}.")
                    } else if (signInCode.isBlank()) {
                        Text(
                            "Melde SmartTube mit deinem YouTube-Konto an. " +
                                "Die Anmeldung läuft über den Gerätecode von YouTube."
                        )
                        if (signInError.isNotBlank()) {
                            Text(signInError, color = MaterialTheme.colorScheme.error)
                        }
                    } else {
                        Text("Öffne auf Handy oder Computer:")
                        Text("https://yt.be/activate", fontWeight = FontWeight.Black)
                        Text("und gib diesen Code ein:")
                        Text(
                            signInCode,
                            fontWeight = FontWeight.Black,
                            fontSize = if (isTv) 30.sp else 24.sp
                        )
                        Text("Danach wird die Anmeldung hier automatisch abgeschlossen.")
                        if (signingIn) {
                            LinearProgressIndicator(modifier = Modifier.fillMaxWidth())
                        }
                    }
                }
            },
            confirmButton = {
                if (auth.signed) {
                    Button(onClick = { accountDialog = false }) { Text("Fertig") }
                } else if (signInCode.isBlank()) {
                    Button(onClick = { beginSignIn() }, enabled = !signingIn) {
                        Text(if (signingIn) "Bitte warten …" else "Code anfordern")
                    }
                } else {
                    TextButton(onClick = {}, enabled = false) {
                        Text("Warte auf Anmeldung …")
                    }
                }
            },
            dismissButton = {
                if (auth.signed) {
                    TextButton(
                        onClick = {
                            scope.launch {
                                V108SmartTubeCore.signOut(context)
                                auth = V108SmartTubeCore.authState(context)
                                accountDialog = false
                                reloadSection(V108SmartTubeSection.HOME)
                            }
                        }
                    ) { Text("Abmelden") }
                } else {
                    TextButton(
                        onClick = {
                            signInDisposable?.dispose()
                            signInDisposable = null
                            signingIn = false
                            signInCode = ""
                            accountDialog = false
                        }
                    ) { Text("Abbrechen") }
                }
            }
        )
    }
}

@Composable
private fun V111HeaderIcon(
    icon: @Composable () -> Unit,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        onClick = onClick,
        modifier = Modifier.size(46.dp).onFocusChanged { focused = it.isFocused },
        color = if (focused) Color.White.copy(.18f) else Color.Transparent,
        shape = RoundedCornerShape(23.dp),
        border = BorderStroke(if (focused) 2.dp else 0.dp, if (focused) Color.White else Color.Transparent)
    ) {
        Box(contentAlignment = Alignment.Center) { icon() }
    }
}

@Composable
private fun V111AccountPill(
    label: String,
    accent: Color,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        onClick = onClick,
        modifier = Modifier
            .height(44.dp)
            .widthIn(max = 210.dp)
            .onFocusChanged { focused = it.isFocused },
        color = if (focused) Color.White.copy(.18f) else Color(0xFF202020),
        shape = RoundedCornerShape(22.dp),
        border = BorderStroke(if (focused) 2.dp else 1.dp, if (focused) Color.White else Color.White.copy(.10f))
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Surface(
                modifier = Modifier.size(28.dp),
                shape = RoundedCornerShape(14.dp),
                color = accent
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Default.Person, null, tint = Color.Black, modifier = Modifier.size(17.dp))
                }
            }
            Spacer(Modifier.width(8.dp))
            Text(
                label,
                color = Color.White,
                fontWeight = FontWeight.SemiBold,
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
private fun V111SmartTubeSidebar(
    selected: V108SmartTubeSection,
    accent: Color,
    onSelect: (V108SmartTubeSection) -> Unit
) {
    Surface(
        modifier = Modifier.width(164.dp).fillMaxHeight(),
        color = Color.Black.copy(alpha = .58f),
        border = BorderStroke(0.dp, Color.Transparent)
    ) {
        LazyColumn(
            contentPadding = PaddingValues(horizontal = 9.dp, vertical = 12.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp)
        ) {
            items(
                V108SmartTubeSection.entries.filterNot { it == V108SmartTubeSection.TRENDING },
                key = { it.name }
            ) { section ->
                V111SidebarItem(
                    section = section,
                    selected = section == selected,
                    accent = accent,
                    index = section.ordinal,
                    onClick = { onSelect(section) }
                )
            }
        }
    }
}

@Composable
private fun V111SidebarItem(
    section: V108SmartTubeSection,
    selected: Boolean,
    accent: Color,
    index: Int,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .height(50.dp)
            .then(
                v111RememberFocus(
                    menuKey = "smarttube-section",
                    itemId = section.name,
                    index = index,
                    enabled = true
                )
            )
            .onFocusChanged { focused = it.isFocused },
        color = when {
            focused -> Color.White.copy(.18f)
            selected -> Color.White.copy(.11f)
            else -> Color.Transparent
        },
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(if (focused) 2.dp else 0.dp, if (focused) Color.White else Color.Transparent)
    ) {
        Row(
            Modifier.fillMaxSize().padding(horizontal = 9.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Box(Modifier.size(28.dp), contentAlignment = Alignment.Center) {
                if (section == V108SmartTubeSection.HOME) {
                    Icon(
                        Icons.Default.Home,
                        null,
                        tint = if (selected || focused) Color.White else Color.White.copy(.72f),
                        modifier = Modifier.size(21.dp)
                    )
                } else {
                    Text(
                        section.shortMark,
                        color = if (selected || focused) Color.White else Color.White.copy(.72f),
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Black
                    )
                }
            }
            Spacer(Modifier.width(9.dp))
            Text(
                section.label,
                color = if (selected || focused) Color.White else Color.White.copy(.78f),
                fontWeight = if (selected || focused) FontWeight.Bold else FontWeight.Medium,
                fontSize = 13.sp,
                maxLines = 1
            )
        }
    }
}

@Composable
private fun V111SmartTubeRowView(
    row: V100SmartTubeRow,
    accent: Color,
    isTv: Boolean,
    resolvingId: String?,
    onVideo: (V100SmartTubeVideo) -> Unit
) {
    Column {
        Text(
            row.title,
            color = Color.White,
            fontSize = if (isTv) 22.sp else 16.sp,
            fontWeight = FontWeight.Bold,
            modifier = Modifier.padding(start = 2.dp, bottom = 10.dp)
        )
        val rowKey = "smarttube-row:" + row.title
        val rowState = v111RememberLazyListState(rowKey)
        LazyRow(
            state = rowState,
            horizontalArrangement = Arrangement.spacedBy(if (isTv) 17.dp else 10.dp)
        ) {
            itemsIndexed(row.videos, key = { _, video -> video.videoId }) { index, video ->
                V111SmartTubeVideoCard(
                    video = video,
                    accent = accent,
                    isTv = isTv,
                    resolving = resolvingId == video.videoId,
                    rememberedFocus = v111RememberFocus(
                        menuKey = rowKey,
                        itemId = video.videoId,
                        index = index,
                        enabled = isTv
                    ),
                    onClick = { onVideo(video) }
                )
            }
        }
    }
}

@Composable
private fun V111SmartTubeVideoCard(
    video: V100SmartTubeVideo,
    accent: Color,
    isTv: Boolean,
    resolving: Boolean,
    rememberedFocus: Modifier = Modifier,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val width = if (isTv) 306.dp else 198.dp
    val imageHeight = if (isTv) 172.dp else 111.dp
    val imageShape = RoundedCornerShape(if (isTv) 12.dp else 10.dp)

    Column(
        Modifier.width(width)
    ) {
        Surface(
            onClick = onClick,
            modifier = rememberedFocus.onFocusChanged { focused = it.isFocused },
            shape = imageShape,
            color = Color(0xFF181818),
            border = BorderStroke(if (focused) 4.dp else 0.dp, if (focused) Color.White else Color.Transparent)
        ) {
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
                        Modifier.fillMaxSize().background(Color(0xFF202020)),
                        contentAlignment = Alignment.Center
                    ) {
                        Text("SmartTube", color = Color.White.copy(.72f), fontWeight = FontWeight.Bold)
                    }
                }
                if (video.live) {
                    Text(
                        "LIVE",
                        color = Color.White,
                        fontSize = 10.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier
                            .align(Alignment.BottomStart)
                            .padding(8.dp)
                            .background(Color(0xFFE62117), RoundedCornerShape(4.dp))
                            .padding(horizontal = 6.dp, vertical = 3.dp)
                    )
                }
                if (!video.live && video.durationMs > 0L) {
                    Text(
                        v111FormatCardDuration(video.durationMs),
                        color = Color.White,
                        fontSize = if (isTv) 11.sp else 9.sp,
                        fontWeight = FontWeight.Black,
                        modifier = Modifier
                            .align(Alignment.BottomEnd)
                            .padding(7.dp)
                            .background(Color.Black.copy(alpha = .80f), RoundedCornerShape(4.dp))
                            .padding(horizontal = 5.dp, vertical = 2.dp)
                    )
                }
                if (resolving) {
                    Box(
                        Modifier.fillMaxSize().background(Color.Black.copy(.58f)),
                        contentAlignment = Alignment.Center
                    ) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(if (isTv) 34.dp else 26.dp),
                            color = Color.White,
                            strokeWidth = 3.dp
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(8.dp))
        Text(
            video.title,
            color = Color.White,
            fontSize = if (isTv) 16.sp else 13.sp,
            fontWeight = FontWeight.SemiBold,
            maxLines = 2,
            overflow = TextOverflow.Ellipsis,
            lineHeight = if (isTv) 20.sp else 16.sp
        )
        if (video.author.isNotBlank()) {
            Spacer(Modifier.height(3.dp))
            Text(
                video.author,
                color = Color.White.copy(.62f),
                fontSize = if (isTv) 13.sp else 10.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}


@Composable
internal fun V110TvKeyboardDialog(
    title: String,
    initialValue: String,
    accent: Color,
    onDismiss: () -> Unit,
    onValueChange: (String) -> Unit = {},
    onSubmit: (String) -> Unit
) {
    var value by remember(initialValue) { mutableStateOf(initialValue) }
    val rows = remember {
        listOf(
            listOf("A","B","C","D","E","F","G","H","I","J"),
            listOf("K","L","M","N","O","P","Q","R","S","T"),
            listOf("U","V","W","X","Y","Z","0","1","2","3"),
            listOf("4","5","6","7","8","9","Ä","Ö","Ü","-")
        )
    }

    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(title) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(9.dp)) {
                Surface(
                    modifier = Modifier.fillMaxWidth().height(52.dp),
                    color = Color(0xFF111821),
                    shape = RoundedCornerShape(10.dp),
                    border = BorderStroke(1.dp, accent.copy(.65f))
                ) {
                    Box(
                        Modifier.fillMaxSize().padding(horizontal = 14.dp),
                        contentAlignment = Alignment.CenterStart
                    ) {
                        Text(
                            value.ifBlank { "Suchbegriff eingeben …" },
                            color = if (value.isBlank()) Color.White.copy(.42f) else Color.White,
                            fontWeight = FontWeight.Bold,
                            maxLines = 1,
                            overflow = TextOverflow.Ellipsis
                        )
                    }
                }

                rows.forEach { keyRow ->
                    Row(
                        Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.spacedBy(5.dp)
                    ) {
                        keyRow.forEach { key ->
                            OutlinedButton(
                                onClick = {
                                    value += key.lowercase()
                                    onValueChange(value)
                                },
                                modifier = Modifier.weight(1f).height(38.dp),
                                contentPadding = PaddingValues(0.dp),
                                border = BorderStroke(1.dp, Color.White.copy(.18f)),
                                colors = ButtonDefaults.outlinedButtonColors(contentColor = Color.White)
                            ) {
                                Text(key, fontSize = 12.sp, fontWeight = FontWeight.Black)
                            }
                        }
                    }
                }

                Row(
                    Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.spacedBy(7.dp)
                ) {
                    OutlinedButton(
                        onClick = {
                            value += " "
                            onValueChange(value)
                        },
                        modifier = Modifier.weight(1.4f)
                    ) { Text("LEERZEICHEN", fontSize = 11.sp) }
                    OutlinedButton(
                        onClick = {
                            if (value.isNotEmpty()) {
                                value = value.dropLast(1)
                                onValueChange(value)
                            }
                        },
                        modifier = Modifier.weight(1f)
                    ) { Text("⌫", fontSize = 17.sp) }
                    OutlinedButton(
                        onClick = {
                            value = ""
                            onValueChange(value)
                        },
                        modifier = Modifier.weight(1f)
                    ) { Text("LÖSCHEN", fontSize = 10.sp) }
                }
            }
        },
        confirmButton = {
            Button(
                enabled = value.isNotBlank(),
                onClick = { onSubmit(value) }
            ) { Text("Suchen") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Abbrechen") }
        }
    )
}


internal fun v110NeedsLegacyFireTvKeyboard(): Boolean =
    Build.MANUFACTURER.equals("Amazon", ignoreCase = true) &&
        Build.VERSION.SDK_INT <= Build.VERSION_CODES.N_MR1


private fun v111FormatCardDuration(ms: Long): String {
    val total = ms.coerceAtLeast(0L) / 1000L
    val seconds = total % 60L
    val minutes = (total / 60L) % 60L
    val hours = total / 3600L
    return if (hours > 0L) "%d:%02d:%02d".format(hours, minutes, seconds)
    else "%d:%02d".format(minutes, seconds)
}
