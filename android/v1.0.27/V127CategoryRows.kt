package de.epimediahub.app.ui

import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.FastOutSlowInEasing
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawBehind
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.compositeOver
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Read changing colours in draw, so every frame avoids text composition and measurement. */
@Composable
private fun Modifier.categoryBackground(target: Color): Modifier {
    val colour = animateColorAsState(target, tween(95, easing = FastOutSlowInEasing), label = "categoryBackground")
    return drawBehind { drawRoundRect(colour.value, cornerRadius = CornerRadius(10.dp.toPx())) }
}

@Composable
internal fun V071CategoryRailItem(
    title: String, selected: Boolean, accent: Color, modifier: Modifier = Modifier, onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val background = when {
        focused -> accent.copy(alpha = .35f).compositeOver(Color(0xFF172230))
        selected -> accent.copy(alpha = .22f).compositeOver(Color(0xFF172230))
        else -> Color(0xFF141D29)
    }
    Row(
        modifier.fillMaxWidth().heightIn(min = 52.dp).testTag("vod-category-$title")
            .onFocusChanged { focused = it.isFocused }
            .categoryBackground(background).v114FocusRing().clickable(onClick = onClick)
            .padding(horizontal = 11.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        // Constant width and weight: focus never moves text or changes line wrapping.
        Box(Modifier.width(4.dp).height(24.dp)
            .background(if (selected || focused) accent else Color.White.copy(alpha = .18f), RoundedCornerShape(99.dp)))
        Spacer(Modifier.width(9.dp))
        Text(title, color = Color.White.copy(alpha = .96f), fontSize = 13.sp,
            fontWeight = FontWeight.SemiBold, maxLines = 2, overflow = TextOverflow.Ellipsis)
    }
}

@Composable
internal fun V076CategoryRow(
    title: String, selected: Boolean, accent: Color, modifier: Modifier = Modifier, onSelected: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val background = when {
        focused -> accent.copy(alpha = .24f)
        selected -> accent.copy(alpha = .13f)
        else -> Color.Transparent
    }
    Row(
        modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("live-category-$title")
            .onFocusChanged { focused = it.isFocused; if (it.isFocused) onSelected() }
            .categoryBackground(background).v114FocusRing().clickable(onClick = onSelected)
            .padding(horizontal = 10.dp, vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically
    ) {
        Box(Modifier.width(4.dp).height(25.dp)
            .background(if (focused || selected) accent else Color.White.copy(alpha = .16f), RoundedCornerShape(99.dp)))
        Spacer(Modifier.width(9.dp))
        Text(title, color = if (focused || selected) Color.White else Color.White.copy(alpha = .78f),
            fontSize = 13.sp, fontWeight = FontWeight.SemiBold, maxLines = 1, overflow = TextOverflow.Ellipsis)
    }
}
