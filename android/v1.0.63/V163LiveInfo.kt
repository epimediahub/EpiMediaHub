package de.epimediahub.app.ui

import android.view.KeyEvent
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.focusable
import androidx.compose.foundation.gestures.scrollBy
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.data.V163Epg
import de.epimediahub.app.model.EpgItem
import de.epimediahub.app.model.MediaEntry
import kotlinx.coroutines.launch
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** The programme description owns the remaining height instead of being clipped below duplicate titles. */
@Composable
internal fun V163LiveInfoPanel(
    channel: MediaEntry?, events: List<EpgItem>, accent: Color, compact: Boolean,
    modifier: Modifier = Modifier, watermarkRes: Int = 0, watermarkUrl: String = "", skinLabel: String = ""
) {
    val now = v163EpgClock(channel?.resumeKey.orEmpty(), events)
    val current = V163Epg.current(events, now)
    val next = V163Epg.next(events, now)
    fun clock(time: Long) = SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date(time * 1000L))
    Surface(modifier, color = Color(0xC20A1019), shape = RoundedCornerShape(14.dp),
        border = BorderStroke(1.dp, Color.White.copy(.08f))) {
        if (channel == null) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("Sender auswählen", color = Color.White.copy(.58f))
            }
        } else Column(Modifier.fillMaxSize().padding(if (compact) 10.dp else 12.dp)) {
            Box(Modifier.fillMaxWidth().height(if (compact) 42.dp else 64.dp)) {
                if (watermarkRes != 0) Image(painterResource(watermarkRes), null,
                    Modifier.align(Alignment.CenterEnd).fillMaxHeight().width(100.dp)
                        .graphicsLayer { alpha = .12f }, contentScale = ContentScale.Fit)
                else if (watermarkUrl.isNotBlank()) AsyncImage(watermarkUrl, null,
                    Modifier.align(Alignment.CenterEnd).fillMaxHeight().width(100.dp)
                        .graphicsLayer { alpha = .12f }, contentScale = ContentScale.Fit)
                Row(Modifier.fillMaxSize(), verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Surface(Modifier.width(if (compact) 52.dp else 72.dp).fillMaxHeight(),
                        color = Color.White, shape = RoundedCornerShape(8.dp)) {
                        if (channel.image.isNotBlank())
                            V128MediaArtwork(channel, Modifier.fillMaxSize().padding(5.dp), ContentScale.Fit)
                        else Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            Text("TV", color = accent, fontWeight = FontWeight.Black, fontSize = 16.sp)
                        }
                    }
                    Column(Modifier.weight(1f)) {
                        Text(channel.name, color = Color.White, fontSize = if (compact) 14.sp else 16.sp,
                            fontWeight = FontWeight.Black, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        if (!compact && skinLabel.isNotBlank()) Text("SKIN · $skinLabel", color = accent.copy(.76f),
                            fontSize = 9.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                    Surface(color = accent, shape = RoundedCornerShape(6.dp)) {
                        Text("LIVE", Modifier.padding(horizontal = 5.dp, vertical = 3.dp),
                            color = Color.White, fontSize = 8.sp, fontWeight = FontWeight.Black)
                    }
                }
            }
            Spacer(Modifier.height(if (compact) 5.dp else 9.dp))
            if (current != null) {
                Text("JETZT · ${clock(current.start)} – ${clock(current.end)}", color = accent,
                    fontSize = 10.sp, fontWeight = FontWeight.Black)
                Text(current.title, color = Color.White, fontSize = if (compact) 12.sp else 14.sp,
                    fontWeight = FontWeight.Bold, maxLines = if (compact) 1 else 2, overflow = TextOverflow.Ellipsis)
                if (!compact) LinearProgressIndicator(
                    progress = { ((now - current.start).toFloat() / (current.end - current.start).coerceAtLeast(1L)).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth().padding(top = 5.dp).height(3.dp),
                    color = accent, trackColor = Color.White.copy(.10f))
            } else Text("Keine aktuellen EPG-Daten verfügbar", color = Color.White.copy(.68f), fontSize = 11.sp)
            if (next != null) Text("ALS NÄCHSTES · ${clock(next.start)}  ${next.title}",
                color = Color.White.copy(.78f), fontSize = if (compact) 10.sp else 11.sp,
                maxLines = if (compact) 1 else 2, overflow = TextOverflow.Ellipsis,
                modifier = Modifier.padding(top = if (compact) 4.dp else 8.dp))
            if (!compact) Text("WORUM ES GEHT", color = Color.White.copy(.60f), fontSize = 10.sp,
                fontWeight = FontWeight.Black, modifier = Modifier.padding(top = 10.dp, bottom = 4.dp))
            val description = current?.description?.trim().orEmpty()
            val scroll = rememberScrollState()
            val scope = rememberCoroutineScope()
            val step = with(LocalDensity.current) { 54.dp.toPx() }
            LaunchedEffect(channel.resumeKey, current?.start) { scroll.scrollTo(0) }
            Box(Modifier.weight(1f).fillMaxWidth().padding(top = if (compact) 4.dp else 0.dp)
                .clip(RoundedCornerShape(7.dp)).testTag("live-programme-description")
                .then(if (description.isNotBlank()) Modifier.v114FocusRing().onPreviewKeyEvent { event ->
                    val key = event.nativeKeyEvent
                    val direction = when (key.keyCode) {
                        KeyEvent.KEYCODE_DPAD_DOWN -> if (scroll.canScrollForward) 1 else 0
                        KeyEvent.KEYCODE_DPAD_UP -> if (scroll.canScrollBackward) -1 else 0
                        else -> 0
                    }
                    if (key.action == KeyEvent.ACTION_DOWN && direction != 0) {
                        scope.launch { scroll.scrollBy(step * direction) }; true
                    } else false
                }.focusable() else Modifier)) {
                Text(description.ifBlank { "Keine Beschreibung vom Anbieter verfügbar." },
                    modifier = Modifier.fillMaxWidth().verticalScroll(scroll).padding(horizontal = 3.dp, vertical = 4.dp),
                    color = Color.White.copy(.85f), fontSize = if (compact) 11.sp else 12.sp,
                    lineHeight = if (compact) 15.sp else 17.sp)
            }
        }
    }
}
