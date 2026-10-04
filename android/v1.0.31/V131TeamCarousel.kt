package de.epimediahub.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusGroup
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.model.ThemeInfo
import kotlinx.coroutines.launch

@Composable
internal fun V131TeamCarousel(vm: MainViewModel, team: ThemeInfo, selectedId: String, isTv: Boolean) {
    val variants = V131SkinArtwork.variants(LocalContext.current, team.id)
    val scroll = rememberLazyListState(initialFirstVisibleItemIndex = variants.indexOfFirst { it.id == selectedId }.coerceAtLeast(0))
    val scope = rememberCoroutineScope()
    val accent = color(team.accent)
    Column(Modifier.fillMaxWidth()) {
        Row(Modifier.fillMaxWidth().padding(bottom = 6.dp), verticalAlignment = Alignment.CenterVertically) {
            Text(team.label, color = Color.White, fontSize = if (isTv) 20.sp else 17.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.weight(1f))
            Text("‹  VARIANTEN  ›", color = Color.White.copy(.67f), fontSize = if (isTv) 11.sp else 10.sp)
        }
        BoxWithConstraints(Modifier.fillMaxWidth()) {
            // A visible next-card edge communicates sideways navigation.
            val cardWidth = maxWidth * if (isTv) .69f else .86f
            LazyRow(state = scroll, modifier = Modifier.fillMaxWidth().focusGroup().testTag("variants-" + team.id),
                horizontalArrangement = Arrangement.spacedBy(if (isTv) 14.dp else 10.dp),
                contentPadding = PaddingValues(horizontal = 4.dp, vertical = 5.dp)) {
                itemsIndexed(variants, key = { _, variant -> variant.id }) { index, variant ->
                    var focused by remember { mutableStateOf(false) }
                    val active = variant.id == selectedId
                    val shape = RoundedCornerShape(if (isTv) 16.dp else 12.dp)
                    Box(Modifier.width(cardWidth).height(if (isTv) 185.dp else 148.dp)
                        .testTag("skin-" + variant.id)
                        .then(v111RememberFocus("themes-preview:" + team.group, variant.id, index, isTv))
                        .onFocusChanged {
                            focused = it.isFocused
                            if (it.isFocused) scope.launch { scroll.animateScrollToItem(index) }
                        }
                        .clip(shape)
                        .border(if (focused) 3.dp else if (active) 2.dp else 1.dp,
                            if (focused) Color.White else if (active) accent else Color.White.copy(.24f), shape)
                        .v114FocusRing().clickable { vm.selectTheme(variant.id) }) {
                        V097SkinEnvironment(V097SkinWorldFor(team.id, team.label, team.group), accent)
                        V131PortraitLayer(variant.id, preview = true)
                        Image(painterResource(vm.themeRepo().officialMarkRes(team.id)), null,
                            Modifier.align(Alignment.Center).fillMaxHeight(.73f).fillMaxWidth(.34f),
                            contentScale = androidx.compose.ui.layout.ContentScale.Fit)
                        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(
                            listOf(Color.Transparent, Color.Transparent, Color(0xD9070A10)))))
                        Column(Modifier.align(Alignment.BottomStart).padding(horizontal = 17.dp, vertical = 12.dp)) {
                            Text(variant.label, color = Color.White, fontSize = if (isTv) 20.sp else 16.sp,
                                fontWeight = FontWeight.Bold)
                            val detail = variant.portraits.joinToString(" · ") { it.name }
                            Text(if (active) "AKTIV" else detail.ifBlank { "Original-Skin" },
                                color = if (active) accent else Color.White.copy(.85f),
                                fontSize = if (isTv) 12.sp else 10.sp, maxLines = 1, overflow = TextOverflow.Ellipsis)
                        }
                    }
                }
            }
        }
    }
}
