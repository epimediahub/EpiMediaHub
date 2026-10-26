package de.epimediahub.app.ui

import androidx.compose.foundation.border
import androidx.compose.foundation.focusable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.unit.dp

fun Modifier.v070TvFocus(accent: Color, radius: Int = 12): Modifier = composed {
    var focused by remember { mutableStateOf(false) }
    val shape = RoundedCornerShape(radius.dp)
    this
        .onFocusChanged { focused = it.hasFocus }
        .graphicsLayer {
            scaleX = if (focused) 1.035f else 1f
            scaleY = if (focused) 1.035f else 1f
        }
        .shadow(if (focused) 22.dp else 0.dp, shape)
        .border(
            if (focused) 3.dp else 0.dp,
            if (focused) Color.White else Color.Transparent,
            shape
        )
}
