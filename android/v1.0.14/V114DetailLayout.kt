package de.epimediahub.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusProperties
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.input.key.*
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.graphics.Color
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.flow.distinctUntilChanged

/** A bounded reading area with pinned title/actions and remote-controlled scrolling. */
@OptIn(ExperimentalLayoutApi::class)
@Composable
internal fun V114DetailLayout(
    title: String,
    description: String,
    accent: Color,
    isTv: Boolean,
    memoryKey: String,
    poster: @Composable (Modifier) -> Unit,
    metadata: List<String> = emptyList(),
    credits: List<Pair<String, String>> = emptyList(),
    loading: Boolean = false,
    isSeries: Boolean = false,
    favorite: Boolean? = null,
    onPlay: () -> Unit,
    onFavorite: (() -> Unit)? = null,
    onTrailer: (() -> Unit)? = null,
    modifier: Modifier = Modifier
) {
    key(memoryKey) {
        val playFocus = remember { FocusRequester() }
        val descriptionFocus = remember { FocusRequester() }
        val savedFocus = remember { V111MenuMemory.id(memoryKey) }
        LaunchedEffect(memoryKey, isTv) {
            if (isTv && savedFocus.isBlank()) {
                delay(110L)
                runCatching { playFocus.requestFocus() }
            }
        }
        BoxWithConstraints(modifier.fillMaxSize().padding(horizontal = if (isTv) 32.dp else 12.dp, vertical = 10.dp)) {
            val wide = isTv || maxWidth >= 680.dp
            val posterWidth = if (isTv) 205.dp else if (wide) 170.dp else 92.dp
            Row(Modifier.fillMaxSize(), horizontalArrangement = Arrangement.spacedBy(if (isTv) 24.dp else 12.dp)) {
                if (wide) {
                    poster(Modifier.width(posterWidth).heightIn(max = 315.dp).aspectRatio(2f / 3f).testTag("detail-poster"))
                }
                Column(
                    Modifier.weight(1f).fillMaxHeight()
                        .background(Color(0xFC0C131D), RoundedCornerShape(18.dp))
                        .border(1.dp, Color.White.copy(.16f), RoundedCornerShape(18.dp))
                        .padding(if (isTv) 20.dp else 14.dp),
                    verticalArrangement = Arrangement.spacedBy(if (isTv) 12.dp else 8.dp)
                ) {
                    Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                        if (!wide) poster(Modifier.width(posterWidth).aspectRatio(2f / 3f).testTag("detail-poster"))
                        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                            Text(
                                title, color = Color.White, fontFamily = FontFamily.SansSerif,
                                fontStyle = FontStyle.Normal, fontWeight = FontWeight.Bold,
                                fontSize = if (isTv) 28.sp else 22.sp,
                                lineHeight = if (isTv) 34.sp else 28.sp,
                                maxLines = if (wide) 3 else 4, overflow = TextOverflow.Ellipsis
                            )
                            FlowRow(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                metadata.filter { it.isNotBlank() }.forEach { value ->
                                    Text(
                                        value, color = Color.White, fontFamily = FontFamily.SansSerif,
                                        fontSize = if (isTv) 15.sp else 12.sp, fontWeight = FontWeight.Medium,
                                        modifier = Modifier.background(Color(0xFF243449), RoundedCornerShape(7.dp))
                                            .padding(horizontal = 9.dp, vertical = 5.dp)
                                    )
                                }
                            }
                        }
                    }
                    FlowRow(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Button(
                            onClick = onPlay, colors = ButtonDefaults.buttonColors(containerColor = accent, contentColor = Color.Black),
                            modifier = v111RememberFocus(memoryKey, "play", 0, isTv)
                                .focusRequester(playFocus).focusProperties { down = descriptionFocus }
                                .v114FocusRing().height(if (isTv) 48.dp else 44.dp).testTag("detail-play")
                        ) {
                            Text(if (isSeries) "Staffeln & Episoden" else "Abspielen", fontSize = if (isTv) 16.sp else 14.sp, fontWeight = FontWeight.Bold)
                        }
                        if (onFavorite != null) {
                            OutlinedButton(
                                onClick = onFavorite,
                                modifier = v111RememberFocus(memoryKey, "favorite", 1, isTv)
                                    .focusProperties { down = descriptionFocus }.v114FocusRing()
                                    .height(if (isTv) 48.dp else 44.dp).testTag("detail-favorite")
                            ) { Text(if (favorite == true) "★ Favorit" else "☆ Zu Favoriten", color = Color.White, fontWeight = FontWeight.Bold) }
                        }
                        if (onTrailer != null) {
                            OutlinedButton(
                                onClick = onTrailer,
                                modifier = v111RememberFocus(memoryKey, "trailer", 2, isTv)
                                    .focusProperties { down = descriptionFocus }.v114FocusRing()
                                    .height(if (isTv) 48.dp else 44.dp).testTag("detail-trailer")
                            ) { Text("Trailer ansehen", color = Color.White, fontWeight = FontWeight.Bold) }
                        }
                    }
                    if (loading) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            CircularProgressIndicator(Modifier.size(18.dp), color = accent, strokeWidth = 2.dp)
                            Spacer(Modifier.width(8.dp))
                            Text("Weitere Informationen werden geladen …", color = Color.White.copy(.85f), fontSize = 13.sp)
                        }
                    }
                    V114DescriptionPanel(
                        description = description, credits = credits, isTv = isTv, memoryKey = memoryKey,
                        playFocus = playFocus, descriptionFocus = descriptionFocus,
                        modifier = Modifier.weight(1f).fillMaxWidth()
                    )
                }
            }
        }
    }
}

@Composable
private fun V114DescriptionPanel(
    description: String,
    credits: List<Pair<String, String>>,
    isTv: Boolean,
    memoryKey: String,
    playFocus: FocusRequester,
    descriptionFocus: FocusRequester,
    modifier: Modifier
) {
    val scrollKey = memoryKey + ":description-scroll"
    val initialScroll = remember(scrollKey) { V111MenuMemory.scroll(scrollKey).first }
    val scroll = rememberScrollState(initialScroll)
    LaunchedEffect(scrollKey, scroll) {
        snapshotFlow { scroll.value }.distinctUntilChanged().collect {
            V111MenuMemory.rememberScroll(scrollKey, it, 0)
        }
    }
    DisposableEffect(scrollKey, scroll) {
        onDispose { V111MenuMemory.rememberScroll(scrollKey, scroll.value, 0) }
    }
    val scope = rememberCoroutineScope()
    val step = with(LocalDensity.current) { 68.dp.toPx() }
    Column(
        modifier.background(Color(0xFF111E2E), RoundedCornerShape(12.dp))
            .then(v111RememberFocus(memoryKey, "description", 3, isTv))
            .focusRequester(descriptionFocus).focusProperties { up = playFocus; left = playFocus }
            .v114FocusRing()
            .onPreviewKeyEvent { event ->
                if (!isTv || event.type != KeyEventType.KeyDown) false
                else {
                    val delta = when (event.key) {
                        Key.DirectionDown -> if (scroll.value < scroll.maxValue) step else 0f
                        Key.DirectionUp -> if (scroll.value > 0) -step else 0f
                        else -> 0f
                    }
                    if (delta == 0f) false else { scope.launch { scroll.scrollBy(delta) }; true }
                }
            }
            .focusable(enabled = isTv).testTag("detail-description").padding(if (isTv) 16.dp else 12.dp)
    ) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text("BESCHREIBUNG", color = Color.White, fontSize = if (isTv) 15.sp else 13.sp, fontWeight = FontWeight.Bold)
            if (isTv) Text("↑ ↓ Lesen", color = Color.White.copy(.8f), fontSize = 13.sp)
        }
        Spacer(Modifier.height(10.dp))
        Column(Modifier.weight(1f).fillMaxWidth().verticalScroll(scroll).testTag("detail-description-body"), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Text(
                description.trim().ifBlank { "Für diesen Titel ist noch keine Beschreibung verfügbar." },
                color = Color.White, fontFamily = FontFamily.SansSerif, fontStyle = FontStyle.Normal,
                fontSize = if (isTv) 21.sp else 16.sp, lineHeight = if (isTv) 30.sp else 24.sp,
                textAlign = TextAlign.Justify, modifier = Modifier.fillMaxWidth()
            )
            credits.filter { it.second.isNotBlank() }.forEach { (label, value) ->
                Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                    Text(label.uppercase(), color = Color.White.copy(.8f), fontWeight = FontWeight.Bold, fontSize = if (isTv) 14.sp else 12.sp)
                    Text(value, color = Color.White, fontFamily = FontFamily.SansSerif, fontStyle = FontStyle.Normal,
                        fontSize = if (isTv) 18.sp else 15.sp, lineHeight = if (isTv) 26.sp else 22.sp)
                }
            }
        }
        if (scroll.maxValue > 0) {
            Spacer(Modifier.height(8.dp))
            LinearProgressIndicator(progress = { scroll.value.toFloat() / scroll.maxValue }, modifier = Modifier.fillMaxWidth().height(3.dp), color = Color.White, trackColor = Color.White.copy(.15f))
        }
    }
}
