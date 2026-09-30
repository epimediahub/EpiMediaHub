package de.epimediahub.app.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.composed
import androidx.compose.ui.draw.drawWithContent
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.geometry.CornerRadius
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.semantics.SemanticsPropertyKey
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp

internal val V114FocusVisible = SemanticsPropertyKey<Boolean>("Visible selection outline")

/** Draw inside the bounds so list clipping and bright skins cannot hide focus. */
internal fun Modifier.v114FocusRing(): Modifier = composed {
    var focused by remember { mutableStateOf(false) }
    this.onFocusChanged { focused = it.hasFocus }
        .semantics { this[V114FocusVisible] = focused }
        .drawWithContent {
            drawContent()
            if (focused && size.width > 10.dp.toPx() && size.height > 10.dp.toPx()) {
                val inset = 4.dp.toPx()
                val outlineSize = Size(size.width - inset * 2, size.height - inset * 2)
                val corner = CornerRadius(10.dp.toPx(), 10.dp.toPx())
                drawRoundRect(Color.Black, Offset(inset, inset), outlineSize, corner, style = Stroke(7.dp.toPx()))
                drawRoundRect(Color.White, Offset(inset, inset), outlineSize, corner, style = Stroke(3.dp.toPx()))
            }
        }
}
