package de.epimediahub.app.ui

import android.content.SharedPreferences
import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.Image
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.layout.ContentScale
import coil.compose.AsyncImage
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.Screen
import de.epimediahub.app.data.V128ParentalControl
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext

@Composable
internal fun v129RememberKidsActive(): Boolean {
    val context = LocalContext.current
    val store = remember(context) { V129KidsStore(context) }
    var active by remember { mutableStateOf(store.active()) }
    DisposableEffect(store) {
        val listener = SharedPreferences.OnSharedPreferenceChangeListener { _, key ->
            if (key == "active") active = store.active()
        }
        store.prefs.registerOnSharedPreferenceChangeListener(listener)
        onDispose { store.prefs.unregisterOnSharedPreferenceChangeListener(listener) }
    }
    return active
}

@Composable
internal fun V129SmartTubeGate(vm: MainViewModel, accent: Color, isTv: Boolean, onBack: () -> Unit) {
    val context = LocalContext.current
    val store = remember(context) { V129KidsStore(context) }
    val parental = remember(context) { V128ParentalControl(context) }
    val scope = rememberCoroutineScope()
    val kidsActive = v129RememberKidsActive()
    var normal by remember { mutableStateOf(false) }
    var message by remember { mutableStateOf("") }
    var pinAction by remember { mutableStateOf<(() -> Unit)?>(null) }
    var pinError by remember { mutableStateOf("") }
    var pinBusy by remember { mutableStateOf(false) }
    var settingPin by remember { mutableStateOf(false) }
    var firstPin by remember { mutableStateOf<String?>(null) }

    fun parentAction(action: () -> Unit) {
        pinError = ""; firstPin = null
        settingPin = !parental.settings().hasPin
        pinAction = action
    }
    fun leaveKids() = parentAction { store.leave(); normal = false }

    if (kidsActive) {
        V129KidsScreen(isTv, onParents = ::leaveKids, load = { V108SmartTubeCore.kids(context) })
    } else if (normal) {
        V112SmartTubeShell(vm, accent, isTv, onBack = { normal = false })
    } else {
        BackHandler(onBack = onBack)
        V129ModeChooser(isTv, onNormal = { normal = true }, onKids = {
            if (parental.settings().hasPin) { vm.navigate(Screen.Home, remember = false); store.enter() }
            else parentAction { vm.navigate(Screen.Home, remember = false); store.enter() }
        }, onBack = onBack)
    }

    // Prepare the service once the chooser is visible, without decoding or requesting a video.
    LaunchedEffect(Unit) { V108SmartTubeCore.warmPlayback(context) }

    if (message.isNotBlank()) AlertDialog(onDismissRequest = { message = "" },
        title = { Text("SmartTube Kids") }, text = { Text(message) },
        confirmButton = { TextButton(onClick = { message = "" }, modifier = Modifier.v114FocusRing()) { Text("OK") } })

    pinAction?.let { action ->
        V128PinDialog(if (settingPin) { if (firstPin == null) "Eltern-PIN festlegen" else "Eltern-PIN wiederholen" } else "Elternbereich entsperren",
            accent, pinBusy, pinError, onCancel = { pinAction = null; firstPin = null }, onSubmit = { pin ->
                if (settingPin && firstPin == null) firstPin = pin
                else if (settingPin && firstPin != pin) { firstPin = null; pinError = "Die PINs stimmen nicht überein." }
                else {
                    pinBusy = true
                    scope.launch {
                        val failure = withContext(Dispatchers.IO) {
                            try {
                                if (settingPin) {
                                    parental.setPin(pin); parental.update(true, false, false); null
                                } else parental.verify(pin).let { if (it.accepted) null else it.message }
                            } catch (_: Exception) { "PIN konnte nicht geprüft werden. Bitte erneut versuchen." }
                        }
                        pinBusy = false
                        if (failure == null) {
                            pinAction = null; firstPin = null; vm.refreshParentalSettings(); action()
                        } else pinError = failure
                    }
                }
            })
    }
}

@Composable
internal fun V129ModeChooser(isTv: Boolean, onNormal: () -> Unit, onKids: () -> Unit, onBack: () -> Unit) {
    val first = remember { FocusRequester() }
    LaunchedEffect(Unit) { withFrameNanos { }; runCatching { first.requestFocus() } }
    Column(Modifier.fillMaxSize().background(Color(0xFF101827)).verticalScroll(rememberScrollState()).padding(if (isTv) 32.dp else 18.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text("SmartTube", color = Color.White, fontSize = if (isTv) 36.sp else 28.sp, fontWeight = FontWeight.Black)
        Text("Was möchtest du ansehen?", color = Color.White.copy(.8f), fontSize = 18.sp)
        V129Choice("SmartTube", "Deine Videos, Abos und Suche", Color(0xFFC92637), Modifier.focusRequester(first).testTag("smarttube-normal"), onNormal)
        V129Choice("SmartTube Kids", "Entdecken · Lachen · Lernen", Color(0xFF135E77), Modifier.testTag("smarttube-kids"), onKids)
        Row(horizontalArrangement = Arrangement.spacedBy(16.dp)) {
            OutlinedButton(onClick = onBack, modifier = Modifier.v114FocusRing()) { Text("Zurück", color = Color.White) }
        }
    }
}

@Composable
private fun V129Choice(title: String, detail: String, color: Color, modifier: Modifier = Modifier, onClick: () -> Unit) {
    Surface(onClick = onClick, modifier = modifier.widthIn(max = 720.dp).fillMaxWidth().v114FocusRing(),
        color = color, shape = RoundedCornerShape(24.dp), border = BorderStroke(1.dp, Color.White.copy(.25f))) {
        Column(Modifier.padding(22.dp)) {
            Text(title, color = Color.White, fontSize = 26.sp, fontWeight = FontWeight.Black)
            Text(detail, color = Color.White.copy(.9f), fontSize = 15.sp)
        }
    }
}

@Composable
internal fun V129KidsScreen(isTv: Boolean, onParents: () -> Unit,
    load: suspend () -> Result<List<V100SmartTubeRow>>
) {
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var catalogue by remember { mutableStateOf(V129KidsCatalogue(emptyList())) }
    var loading by remember { mutableStateOf(true) }
    var reload by remember { mutableIntStateOf(0) }
    var category by remember { mutableStateOf<String?>(null) }
    var active by remember { mutableStateOf<Pair<V100SmartTubeVideo, V100SmartTubePlayback>?>(null) }
    var resolving by remember { mutableStateOf<String?>(null) }
    var error by remember { mutableStateOf("") }
    var playJob by remember { mutableStateOf<kotlinx.coroutines.Job?>(null) }
    val first = remember { FocusRequester() }
    val latestCatalogue by rememberUpdatedState(catalogue)
    LaunchedEffect(reload) {
        loading = true; error = ""
        load().onSuccess { catalogue = V129KidsCatalogue(it) }
            .onFailure { error = "Die Kinder-Videos konnten gerade nicht geladen werden." }
        if (catalogue.videos.isEmpty() && error.isBlank()) error = "Gerade sind keine Kinder-Videos verfügbar."
        loading = false
    }
    fun closePlayback() { playJob?.cancel(); resolving = null; active = null }
    fun play(video: V100SmartTubeVideo) {
        if (resolving != null || !latestCatalogue.allows(video)) return
        resolving = video.videoId; error = ""
        playJob = scope.launch {
            try {
                V108SmartTubeCore.resolvePlayback(context, video)
                    .onSuccess { if (latestCatalogue.allows(video)) active = video to it }
                    .onFailure { error = "Dieses Video kann gerade nicht geladen werden." }
            } finally { resolving = null }
        }
    }
    active?.let { (video, playback) ->
        V112SmartTubePlayer(video, playback, isTv, Color(0xFF63E3D2), onBack = ::closePlayback,
            onEnded = ::closePlayback, suggestions = catalogue.videos.filter { it.videoId != video.videoId },
            suggestionsLoading = false, suggestionsError = error, resolvingId = resolving, onSelectVideo = ::play,
            onReloadSuggestions = {}, historyAccountKey = "kids", onProgress = { _, _, _, _, _ -> })
        return
    }
    BackHandler { if (resolving != null) closePlayback() else onParents() }
    LaunchedEffect(loading, active) { withFrameNanos { }; runCatching { first.requestFocus() } }
    val colors = listOf(Color(0xFF8454C6), Color(0xFFE08A20), Color(0xFF168578), Color(0xFF3169B3))
    Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color(0xFF112E57), Color(0xFF223967)))).testTag("kids-world")) {
        V129KidsSky(Modifier.fillMaxSize())
        Column(Modifier.fillMaxSize().padding(horizontal = if (isTv) 26.dp else 14.dp, vertical = 16.dp)) {
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("SmartTube KIDS", color = Color(0xFFFFDD78), fontSize = if (isTv) 32.sp else 24.sp, fontWeight = FontWeight.Black)
                    Text("Lachen, lernen, Neues entdecken!", color = Color.White, fontSize = if (isTv) 18.sp else 14.sp)
                }
                OutlinedButton(onClick = onParents, modifier = Modifier.v114FocusRing().testTag("kids-parents"),
                    border = BorderStroke(1.dp, Color.White.copy(.65f))) { Text("Eltern · PIN", color = Color.White) }
            }
            Spacer(Modifier.height(16.dp))
            LazyRow(horizontalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                item {
                    Button(onClick = { category = null }, modifier = Modifier.focusRequester(first).v114FocusRing().testTag("kids-all"),
                        colors = ButtonDefaults.buttonColors(containerColor = if (category == null) Color(0xFFFFDD78) else Color(0xFF344D78),
                            contentColor = if (category == null) Color(0xFF15274B) else Color.White)) { Text("★  Für dich", fontWeight = FontWeight.Bold) }
                }
                items(catalogue.rows.map { it.title }.distinct()) { title ->
                    Button(onClick = { category = title }, modifier = Modifier.v114FocusRing(),
                        colors = ButtonDefaults.buttonColors(containerColor = if (category == title) Color(0xFF63E3D2) else Color(0xFF344D78),
                            contentColor = if (category == title) Color(0xFF15274B) else Color.White)) { Text(title, fontWeight = FontWeight.Bold) }
                }
            }
            if (loading) Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                V128LoadingPanel("Deine Videos kommen gleich …", "", Color(0xFFFFDD78), isTv)
            } else if (catalogue.videos.isEmpty()) Column(Modifier.padding(top = 32.dp)) {
                Text(error, color = Color.White, fontSize = 22.sp)
                Button(onClick = { reload++ }, modifier = Modifier.padding(top = 14.dp).v114FocusRing()) { Text("Noch einmal versuchen") }
            } else {
                if (error.isNotBlank()) Text(error, color = Color(0xFFFFDD78))
                LazyColumn(Modifier.fillMaxSize().padding(top = 16.dp), verticalArrangement = Arrangement.spacedBy(22.dp)) {
                    catalogue.rows.filter { category == null || it.title == category }.forEachIndexed { rowIndex, row ->
                        item(key = "$rowIndex:${row.title}") {
                            Column {
                                Text(row.title, color = Color.White, fontSize = if (isTv) 23.sp else 19.sp, fontWeight = FontWeight.Black,
                                    modifier = Modifier.padding(bottom = 10.dp))
                                LazyRow(horizontalArrangement = Arrangement.spacedBy(15.dp)) {
                                    items(row.videos, key = { it.videoId }) { video ->
                                        V129KidsVideoCard(video, isTv, colors[rowIndex % colors.size], resolving == video.videoId) { play(video) }
                                    }
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
internal fun V129KidsVideoCard(video: V100SmartTubeVideo, isTv: Boolean, color: Color, loading: Boolean, onClick: () -> Unit) {
    Surface(onClick = onClick, modifier = Modifier.width(if (isTv) 268.dp else 204.dp).v114FocusRing().testTag("kids-video-${video.videoId}"),
        color = color, shape = RoundedCornerShape(24.dp), border = BorderStroke(2.dp, Color.White.copy(.24f))) {
        Column {
            Box(Modifier.fillMaxWidth().height(if (isTv) 146.dp else 112.dp).background(Color(0xFF244263)), contentAlignment = Alignment.Center) {
                if (video.image.isNotBlank()) AsyncImage(video.image, video.title, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
                else Text("▶", color = Color.White, fontSize = 36.sp)
                if (loading) CircularProgressIndicator(color = Color(0xFFFFDD78))
            }
            Text(video.title, color = Color.White, fontSize = if (isTv) 18.sp else 15.sp, fontWeight = FontWeight.Bold,
                maxLines = 2, overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                modifier = Modifier.heightIn(min = if (isTv) 70.dp else 60.dp).padding(12.dp))
        }
    }
}

/** Light, static vector decoration: no continuous animation or extra bitmap allocation. */
@Composable
private fun V129KidsSky(modifier: Modifier) {
    Canvas(modifier) {
        val radius = size.minDimension * .12f
        val centre = Offset(size.width * .90f, size.height * .28f)
        drawCircle(Color(0xFF728EE8).copy(alpha = .16f), radius, centre)
        drawOval(Color(0xFFA5CAFF).copy(alpha = .18f), Offset(centre.x - radius * 1.6f, centre.y - radius * .38f),
            Size(radius * 3.2f, radius * .76f), style = Stroke(7.dp.toPx()))
        for (index in 0 until 19) {
            val x = ((index * 173 + 41) % 997) / 997f * size.width
            val y = ((index * 127 + 79) % 521) / 521f * size.height
            drawCircle(Color(0xFFFFE4A0).copy(alpha = .3f), if (index % 3 == 0) 3.dp.toPx() else 1.5.dp.toPx(), Offset(x, y))
        }
    }
}
