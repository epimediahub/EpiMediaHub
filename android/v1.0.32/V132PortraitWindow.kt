package de.epimediahub.app.ui

import androidx.compose.ui.Alignment
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.layout.ScaleFactor
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.LayoutDirection
import kotlin.math.min
import kotlin.math.roundToInt

/** A reviewed head-to-waist rectangle in a bundled source photograph or atlas. */
internal data class V132PortraitWindow(val left: Float = 0f, val top: Float = 0f,
    val right: Float = 1f, val bottom: Float = 1f, val aspectRatio: Float = .7f) {
    val width get() = (right-left).coerceAtLeast(.01f)
    val height get() = (bottom-top).coerceAtLeast(.01f)
    val scale = object : ContentScale {
        override fun computeScaleFactor(srcSize: Size, dstSize: Size): ScaleFactor {
            val factor = min(dstSize.width/(srcSize.width*width), dstSize.height/(srcSize.height*height))
            return ScaleFactor(factor, factor)
        }
    }
    val alignment = object : Alignment {
        override fun align(size: IntSize, space: IntSize, layoutDirection: LayoutDirection): IntOffset =
            IntOffset(((space.width-size.width*width)/2-size.width*left).roundToInt(), (-size.height*top).roundToInt())
    }
}
