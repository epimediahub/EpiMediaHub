package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
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
import kotlinx.coroutines.launch

@Composable
fun V110SmartTubeShell(
    vm: MainViewModel,
    accent: Color,
    isTv: Boolean,
    onBack: () -> Unit
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    val ui by vm.ui.collectAsState()
    val smartTubeBackgroundRes = vm.themeRepo().backgroundRes(ui.themeId)
    val smartTubeMotifRes = vm.themeRepo().homeMotifRes(ui.themeId).takeIf { it != 0 }
        ?: vm.themeRepo().markRes(ui.themeId)

    var selectedSection by remember { mutableStateOf(V108SmartTubeSection.HOME) }
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
        V110SmartTubePlayer(
            video = video,
            playback = playback,
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

    Column(Modifier.fillMaxSize()) {
        EpiTopBar(
            "SMARTTUBE",
            R.drawable.brand_header,
            onBack,
            actions = {
                V108TopAction(
                    label = if (auth.signed) {
                        auth.accountName.ifBlank { "KONTO" }.uppercase()
                    } else "ANMELDEN",
                    accent = accent,
                    onClick = { accountDialog = true }
                )
                Spacer(Modifier.width(7.dp))
                V108TopAction(
                    label = "SUCHE",
                    accent = accent,
                    leading = { Icon(Icons.Default.Search, null, tint = Color.White) },
                    onClick = { searchDialog = true }
                )
                Spacer(Modifier.width(7.dp))
                V108TopAction(
                    label = "NEU",
                    accent = accent,
                    leading = { Icon(Icons.Default.Refresh, null, tint = Color.White) },
                    onClick = { reloadSection(selectedSection) }
                )
            }
        )

        Box(
            Modifier
                .fillMaxSize()
                .background(
                    Brush.verticalGradient(
                        listOf(Color(0xFF090D13), Color(0xFF05070B))
                    )
                )
        ) {
            if (smartTubeBackgroundRes != 0) {
                Image(
                    painter = painterResource(smartTubeBackgroundRes),
                    contentDescription = null,
                    modifier = Modifier.fillMaxSize().graphicsLayer { alpha = .20f },
                    contentScale = ContentScale.Crop
                )
            }
            if (smartTubeMotifRes != 0) {
                Image(
                    painter = painterResource(smartTubeMotifRes),
                    contentDescription = null,
                    modifier = Modifier
                        .align(Alignment.CenterEnd)
                        .fillMaxHeight(.86f)
                        .fillMaxWidth(.34f)
                        .padding(end = if (isTv) 26.dp else 8.dp)
                        .graphicsLayer { alpha = .10f },
                    contentScale = ContentScale.Fit
                )
            }
            Row(
                Modifier
                    .fillMaxSize()
                    .background(Color.Black.copy(alpha = .32f))
            ) {
            if (isTv) {
                V108SmartTubeSidebar(
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
                        if (searchTitle.isNotBlank()) searchTitle.uppercase()
                        else selectedSection.label.uppercase(),
                        color = Color.White,
                        fontSize = if (isTv) 21.sp else 16.sp,
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
                        modifier = Modifier.fillMaxSize(),
                        contentPadding = PaddingValues(
                            start = if (isTv) 24.dp else 12.dp,
                            end = if (isTv) 34.dp else 12.dp,
                            top = 6.dp,
                            bottom = 30.dp
                        ),
                        verticalArrangement = Arrangement.spacedBy(if (isTv) 22.dp else 15.dp)
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
                            V108SmartTubeRowView(
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
        if (isTv) {
            V110SmartTubeTvSearchDialog(
                initialValue = query,
                accent = accent,
                onDismiss = { searchDialog = false },
                onSearch = { value ->
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
private fun V108TopAction(
    label: String,
    accent: Color,
    leading: (@Composable () -> Unit)? = null,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        onClick = onClick,
        modifier = Modifier
            .height(38.dp)
            .onFocusChanged { focused = it.isFocused },
        color = if (focused) accent.copy(.42f) else Color(0x32101620),
        contentColor = Color.White,
        shape = RoundedCornerShape(10.dp),
        border = BorderStroke(
            if (focused) 2.dp else 1.dp,
            if (focused) Color.White else Color.White.copy(.16f)
        )
    ) {
        Row(
            Modifier.padding(horizontal = 12.dp, vertical = 7.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (leading != null) {
                leading()
                Spacer(Modifier.width(6.dp))
            }
            Text(
                label,
                color = Color.White,
                fontWeight = FontWeight.Black,
                fontSize = 12.sp,
                maxLines = 1,
                overflow = TextOverflow.Ellipsis
            )
        }
    }
}

@Composable
private fun V108SmartTubeSidebar(
    selected: V108SmartTubeSection,
    accent: Color,
    onSelect: (V108SmartTubeSection) -> Unit
) {
    Surface(
        modifier = Modifier
            .width(188.dp)
            .fillMaxHeight(),
        color = Color(0xF00B1017),
        border = BorderStroke(1.dp, Color.White.copy(.07f))
    ) {
        LazyColumn(
            contentPadding = PaddingValues(horizontal = 10.dp, vertical = 14.dp),
            verticalArrangement = Arrangement.spacedBy(7.dp)
        ) {
            items(
                V108SmartTubeSection.entries.filterNot { it == V108SmartTubeSection.TRENDING },
                key = { it.name }
            ) { section ->
                V108SidebarItem(
                    section = section,
                    selected = section == selected,
                    accent = accent,
                    onClick = { onSelect(section) }
                )
            }
        }
    }
}

@Composable
private fun V108SidebarItem(
    section: V108SmartTubeSection,
    selected: Boolean,
    accent: Color,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        onClick = onClick,
        modifier = Modifier
            .fillMaxWidth()
            .height(48.dp)
            .onFocusChanged { focused = it.isFocused },
        color = when {
            focused -> accent.copy(.34f)
            selected -> accent.copy(.18f)
            else -> Color.Transparent
        },
        shape = RoundedCornerShape(12.dp),
        border = BorderStroke(
            if (focused) 2.dp else 1.dp,
            when {
                focused -> Color.White
                selected -> accent.copy(.75f)
                else -> Color.Transparent
            }
        )
    ) {
        Row(
            Modifier.fillMaxSize().padding(horizontal = 10.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Surface(
                modifier = Modifier.size(30.dp),
                color = when {
                    focused -> Color.White
                    selected -> accent
                    else -> Color.White.copy(.08f)
                },
                shape = RoundedCornerShape(9.dp)
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Text(
                        section.shortMark,
                        color = if (focused) Color.Black else if (selected) Color.Black else Color.White,
                        fontWeight = FontWeight.Black,
                        fontSize = if (section.shortMark.length > 1) 9.sp else 11.sp
                    )
                }
            }
            Spacer(Modifier.width(10.dp))
            Text(
                section.label,
                color = Color.White,
                fontWeight = if (focused || selected) FontWeight.Black else FontWeight.SemiBold,
                fontSize = 13.sp,
                maxLines = 1
            )
        }
    }
}

@Composable
private fun V108SmartTubeRowView(
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
                V108SmartTubeVideoCard(
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
private fun V108SmartTubeVideoCard(
    video: V100SmartTubeVideo,
    accent: Color,
    isTv: Boolean,
    resolving: Boolean,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val width = if (isTv) 246.dp else 178.dp
    val imageHeight = if (isTv) 138.dp else 100.dp
    val shape = RoundedCornerShape(if (isTv) 14.dp else 12.dp)

    Surface(
        onClick = onClick,
        modifier = Modifier
            .width(width)
            .onFocusChanged { focused = it.isFocused },
        color = if (focused) accent.copy(.20f) else Color(0xDC101720),
        shape = shape,
        border = BorderStroke(
            if (focused) 3.dp else 1.dp,
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
                        modifier = Modifier
                            .align(Alignment.BottomStart)
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


@Composable
private fun V110SmartTubeTvSearchDialog(
    initialValue: String,
    accent: Color,
    onDismiss: () -> Unit,
    onSearch: (String) -> Unit
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
        title = { Text("SmartTube durchsuchen") },
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
                                onClick = { value += key.lowercase() },
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
                        onClick = { value += " " },
                        modifier = Modifier.weight(1.4f)
                    ) { Text("LEERZEICHEN", fontSize = 11.sp) }
                    OutlinedButton(
                        onClick = { if (value.isNotEmpty()) value = value.dropLast(1) },
                        modifier = Modifier.weight(1f)
                    ) { Text("⌫", fontSize = 17.sp) }
                    OutlinedButton(
                        onClick = { value = "" },
                        modifier = Modifier.weight(1f)
                    ) { Text("LÖSCHEN", fontSize = 10.sp) }
                }
            }
        },
        confirmButton = {
            Button(
                enabled = value.isNotBlank(),
                onClick = { onSearch(value) }
            ) { Text("Suchen") }
        },
        dismissButton = {
            TextButton(onClick = onDismiss) { Text("Abbrechen") }
        }
    )
}
