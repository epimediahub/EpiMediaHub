package de.epimediahub.app.ui

import androidx.media3.common.C
import androidx.media3.common.Player
import androidx.media3.common.Tracks
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp

/** Quality control only for the first-party SmartTube Media3 player.

 * An MP4/WebM file with one fixed track cannot magically switch to 1080p.
 * Never show unsupported qualities and never alter IPTV/VPN players.
 */
internal object V176SmartTubeQuality {
    fun supportedHeights(heights: List<Int>, extension: String): List<Int> {
        if (extension.lowercase() !in setOf("m3u8", "mpd")) return emptyList()
        val available = heights.filter { it in 144..4320 }.distinct().sortedDescending()
        return available.takeIf { it.size >= 2 } ?: emptyList()
    }

    fun supportedHeights(tracks: Tracks, extension: String): List<Int> {
        val heights = mutableListOf<Int>()
        for (group in tracks.groups) {
            if (group.type != C.TRACK_TYPE_VIDEO) continue
            for (index in 0 until group.length) {
                if (group.isTrackSupported(index)) heights.add(group.getTrackFormat(index).height)
            }
        }
        return supportedHeights(heights, extension)
    }

    fun apply(player: Player, selectedHeight: Int?) {
        require(selectedHeight == null || selectedHeight in 144..4320)
        val builder = player.trackSelectionParameters.buildUpon()
        if (selectedHeight == null) {
            // Restore device-native automatic track choice (subject to decoder limits).
            builder.setMaxVideoSize(Int.MAX_VALUE, Int.MAX_VALUE)
        } else {
            builder.setMaxVideoSize(Int.MAX_VALUE, selectedHeight)
        }
        player.trackSelectionParameters = builder.build()
    }

    fun label(height: Int?): String =
        if (height == null) "Automatisch" else height.toString() + "p"
}

@Composable
internal fun V176SmartTubeQualityDialog(
    heights: List<Int>,
    selectedHeight: Int?,
    onChoose: (Int?) -> Unit,
    onDismiss: () -> Unit
) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Bildqualität") },
        text = {
            Column {
                if (heights.size < 2) {
                    Text("Dieser Videostream bietet keine umschaltbaren Qualitätsstufen. " +
                         "Für fest aufgelöste MP4/WebM-Dateien bleibt die Originalqualität erhalten.")
                } else {
                    Text("Nur tatsächlich verfügbare Stufen auswählen.")
                    TextButton(onClick = { onChoose(null) }) {
                        Text(if (selectedHeight == null) "✓ Automatisch" else "Automatisch")
                    }
                    heights.forEach { height ->
                        TextButton(onClick = { onChoose(height) }) {
                            Text((if (selectedHeight == height) "✓ " else "") +
                                 V176SmartTubeQuality.label(height))
                        }
                    }
                }
            }
        },
        confirmButton = {
            TextButton(onClick = onDismiss) { Text("Schließen") }
        },
        modifier = Modifier.padding(horizontal = 8.dp)
    )
}
