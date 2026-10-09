package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.expandVertically
import androidx.compose.animation.shrinkVertically
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.key.Key
import androidx.compose.ui.input.key.KeyEventType
import androidx.compose.ui.input.key.onPreviewKeyEvent
import androidx.compose.ui.input.key.type
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Transient top drawer: explicitly labelled shortcuts, no permanent face-obscuring circles. */
@Composable
internal fun V149QuickMenu(
    open: Boolean,
    isTv: Boolean,
    accent: Color,
    onToggle: () -> Unit,
    onDismiss: () -> Unit,
    onSettings: () -> Unit,
    onServers: () -> Unit,
    onSpeedtest: () -> Unit,
    onWeather: () -> Unit
) {
    val firstAction = remember { FocusRequester() }
    BackHandler(enabled = open) { onDismiss() }
    LaunchedEffect(open, isTv) {
        if (open && isTv) {
            kotlinx.coroutines.delay(95)
            runCatching { firstAction.requestFocus() }
        }
    }
    Column(
        Modifier.padding(top = if (isTv) 6.dp else 3.dp)
            .testTag("home-quick-menu"),
        horizontalAlignment = Alignment.CenterHorizontally
    ) {
        // Small visible discovery hint; pressing Up on any first-row tile opens it too.
        Surface(
            onClick = onToggle,
            modifier = Modifier.height(if (isTv) 30.dp else 25.dp)
                .testTag("home-quick-toggle").v114FocusRing(),
            color = Color(0xE0162233),
            contentColor = Color.White,
            border = BorderStroke(1.dp, accent.copy(alpha = 0.65f)),
            shape = RoundedCornerShape(0.dp, 0.dp, 10.dp, 10.dp)
        ) {
            Box(Modifier.padding(horizontal = 18.dp), contentAlignment = Alignment.Center) {
                Text(if (open) "SCHNELLMENÜ  ▲" else "SCHNELLMENÜ  ▼",
                    fontSize = if (isTv) 12.sp else 10.sp, fontWeight = FontWeight.Bold)
            }
        }
        AnimatedVisibility(open, enter = expandVertically(expandFrom = Alignment.Top),
            exit = shrinkVertically(shrinkTowards = Alignment.Top)) {
            Surface(
                color = Color(0xF50C1523),
                contentColor = Color.White,
                shape = RoundedCornerShape(15.dp),
                border = BorderStroke(1.dp, accent.copy(alpha = 0.7f)),
                shadowElevation = 16.dp,
                modifier = Modifier.padding(top = 5.dp)
                    .onPreviewKeyEvent { event ->
                        if (event.type == KeyEventType.KeyDown && event.key == Key.DirectionDown) {
                            onDismiss(); true
                        } else false
                    }
                    .testTag("home-quick-panel")
            ) {
                if (isTv) {
                    Row(Modifier.padding(horizontal = 10.dp, vertical = 10.dp),
                        horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        V149QuickAction("⚙", "Einstellungen", "quick-settings", accent, isTv,
                            Modifier.focusRequester(firstAction), onSettings)
                        V149QuickAction("⇄", "Server wechseln", "quick-servers", accent, isTv,
                            Modifier, onServers)
                        V149QuickAction("⇅", "Speedtest", "quick-speedtest", accent, isTv,
                            Modifier, onSpeedtest)
                        V149QuickAction("☁", "Wetter & Ort", "quick-weather", accent, isTv,
                            Modifier, onWeather)
                    }
                } else {
                    Column(Modifier.padding(7.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            V149QuickAction("⚙", "Einstellungen", "quick-settings", accent, isTv,
                                Modifier.focusRequester(firstAction), onSettings)
                            V149QuickAction("⇄", "Server wechseln", "quick-servers", accent, isTv,
                                Modifier, onServers)
                        }
                        Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                            V149QuickAction("⇅", "Speedtest", "quick-speedtest", accent, isTv,
                                Modifier, onSpeedtest)
                            V149QuickAction("☁", "Wetter & Ort", "quick-weather", accent, isTv,
                                Modifier, onWeather)
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun V149QuickAction(
    symbol: String,
    label: String,
    tag: String,
    accent: Color,
    isTv: Boolean,
    modifier: Modifier,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    Surface(
        modifier = modifier.width(if (isTv) 135.dp else 134.dp)
            .height(if (isTv) 79.dp else 67.dp)
            .onFocusChanged { focused = it.isFocused }
            .semantics { contentDescription = label }
            .testTag(tag).v114FocusRing()
            .clickable(role = Role.Button, onClick = onClick),
        color = if (focused) accent.copy(alpha = 0.35f) else Color(0xFF1C2A3C),
        border = BorderStroke(if (focused) 3.dp else 1.dp,
            if (focused) Color.White else Color.White.copy(alpha = 0.22f)),
        shape = RoundedCornerShape(12.dp),
        contentColor = Color.White
    ) {
        Column(Modifier.fillMaxSize().padding(horizontal = 3.dp, vertical = 4.dp),
            horizontalAlignment = Alignment.CenterHorizontally,
            verticalArrangement = Arrangement.Center) {
            Text(symbol, fontSize = if (isTv) 27.sp else 22.sp, fontWeight = FontWeight.Bold)
            Spacer(Modifier.height(3.dp))
            Text(label, fontSize = if (isTv) 12.sp else 10.sp,
                fontWeight = FontWeight.Bold, maxLines = 1, textAlign = TextAlign.Center)
        }
    }
}
