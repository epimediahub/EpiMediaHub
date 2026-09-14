package de.epimediahub.app.ui

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.dp
import com.google.zxing.BarcodeFormat
import com.google.zxing.MultiFormatWriter

@Composable
fun ParityQrCode(value: String, modifier: Modifier = Modifier) {
    if (value.isBlank()) return
    val bitmap = remember(value) {
        runCatching {
            val matrix = MultiFormatWriter().encode(value, BarcodeFormat.QR_CODE, 440, 440)
            Bitmap.createBitmap(matrix.width, matrix.height, Bitmap.Config.ARGB_8888).also { bmp ->
                for (y in 0 until matrix.height) {
                    for (x in 0 until matrix.width) {
                        bmp.setPixel(x, y, if (matrix[x, y]) android.graphics.Color.BLACK else android.graphics.Color.WHITE)
                    }
                }
            }
        }.getOrNull()
    } ?: return
    Box(modifier.background(Color.White).padding(10.dp), contentAlignment = Alignment.Center) {
        Image(bitmap.asImageBitmap(), contentDescription = "QR-Code für lokale Playlist-Verwaltung", modifier = Modifier.size(210.dp))
    }
}
