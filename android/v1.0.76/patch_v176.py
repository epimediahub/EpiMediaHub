#!/usr/bin/env python3
"""v1.0.76 private QA: SmartTube quality control on supported adaptive streams.

Leaves IPTV/VPN playback and Fire TV frame cadence unmodified.
Requires the v1.0.75 signed/private GalaBox source baseline.
"""
from pathlib import Path
import os
import shutil

root=Path(os.environ["PROJECT_ROOT"])
here=Path(__file__).resolve().parent
ui=root/"app/src/main/java/de/epimediahub/app/ui"
tests=root/"app/src/test/java/de/epimediahub/app/ui"

def one(path,old,new):
    value=path.read_text(encoding="utf-8")
    if value.count(old)!=1:
        raise SystemExit("v176 unexpected "+path.name+" anchor="+str(value.count(old))+": "+old[:85])
    path.write_text(value.replace(old,new,1),encoding="utf-8")

gradle=root/"app/build.gradle.kts"
one(gradle,"versionCode = 1075","versionCode = 1076")
one(gradle,'versionName = "1.0.75"','versionName = "1.0.76"')
shutil.copy2(here/"V176SmartTubeQuality.kt",ui/"V176SmartTubeQuality.kt")
tests.mkdir(parents=True,exist_ok=True)
shutil.copy2(here/"V176SmartTubeQualityTest.kt",tests/"V176SmartTubeQualityTest.kt")

browse=ui/"V124SmartTubeBrowseLayer.kt"
one(browse,'onTogglePlayback: () -> Unit, onSeek: (Long) -> Unit, onShowControls: () -> Unit,',
    'onTogglePlayback: () -> Unit, onSeek: (Long) -> Unit, onShowControls: () -> Unit,\n    onQuality: () -> Unit,')
one(browse,'                browsing -> false // The focused card owns OK and Left/Right; never seek behind it.',
    '                browsing -> false // The focused card owns OK and Left/Right; never seek behind it.\n'
    '                event.nativeKeyEvent.keyCode == android.view.KeyEvent.KEYCODE_MENU -> {\n'
    '                    if (!repeated) onQuality(); true\n'
    '                }')

player=ui/"V112SmartTubePlayer.kt"
one(player,'    var controlsVisible by remember(video.videoId) { mutableStateOf(true) }',
    '''    var controlsVisible by remember(video.videoId) { mutableStateOf(true) }
    var showV176Quality by remember(video.videoId) { mutableStateOf(false) }
    var v176Qualities by remember(video.videoId, playback.url) {
        mutableStateOf<List<Int>>(emptyList())
    }
    var v176ChosenHeight by remember(video.videoId) { mutableStateOf<Int?>(null) }''')
one(player,'                override fun onIsPlayingChanged(playing: Boolean) {',
    '''                override fun onTracksChanged(tracks: androidx.media3.common.Tracks) {
                    v176Qualities = V176SmartTubeQuality.supportedHeights(
                        tracks, playback.extension)
                }

                override fun onIsPlayingChanged(playing: Boolean) {''')
one(player,'        onSeek = ::seekBy, onShowControls = { controlsVisible = true },',
    '''        onSeek = ::seekBy, onShowControls = { controlsVisible = true },
        onQuality = { showV176Quality = true },''')
one(player,'    ) { browsing ->\n        if (player != null) {',
    '''    ) { browsing ->
        if (!browsing && controlsVisible && player != null) {
            TextButton(onClick = { showV176Quality = true },
                modifier = Modifier.align(Alignment.TopCenter).padding(top = 14.dp)) {
                Text("Qualität · " + V176SmartTubeQuality.label(v176ChosenHeight),
                    color = Color.White)
            }
        }
        if (player != null) {''')
# The dialog uses Android Dialog's own focus window; keep D-pad player navigation stable.
old='''        }
    }
}


@Composable
private fun V112PlayerControlChip('''
new='''        }
    }
    if (showV176Quality) {
        V176SmartTubeQualityDialog(v176Qualities, v176ChosenHeight,
            onChoose = { height ->
                val active = player
                if (active != null && (height == null || height in v176Qualities)) {
                    V176SmartTubeQuality.apply(active, height)
                    v176ChosenHeight = height
                }
                showV176Quality = false
                controlsVisible = true
            },
            onDismiss = { showV176Quality = false })
    }
}


@Composable
private fun V112PlayerControlChip('''
one(player,old,new)
assert "V176SmartTubeQuality.supportedHeights" in player.read_text()
assert "KEYCODE_MENU" in browse.read_text()
assert "setMaxVideoSize" in (ui/"V176SmartTubeQuality.kt").read_text()
print("v176: first-party SmartTube can select available HLS/DASH video qualities; fixed MP4 unchanged")
