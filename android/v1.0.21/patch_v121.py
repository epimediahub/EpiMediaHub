#!/usr/bin/env python3
"""Cinematic English launch ident and stable VOD output / content frame-rate matching."""
import os
from pathlib import Path
import shutil

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent


def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f"{path}: expected one anchor, got {text.count(old)}: {old[:100]}"
    path.write_text(text.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 1020', 'versionCode = 1021')
replace_once(gradle, 'versionName = "1.0.20"', 'versionName = "1.0.21"')
for path in java.rglob("*.kt"):
    text = path.read_text()
    if "1.0.20" in text:
        path.write_text(text.replace("1.0.20", "1.0.21"))

shutil.copyfile(here / "V121Intro.kt", java / "ui/V070Intro.kt")
for name in ("V121IntroTimeline.kt", "V121FrameRatePolicy.kt", "V121VodSurface.kt"):
    shutil.copyfile(here / name, java / "ui" / name)

vod = java / "ui/V116VodPlayer.kt"
replace_once(vod, '''        AndroidView(factory = { ctx -> PlayerView(ctx).apply {
            this.player = player; useController = false; controllerAutoShow = false
            isFocusable = false; isFocusableInTouchMode = false; descendantFocusability = ViewGroup.FOCUS_BLOCK_DESCENDANTS; hideController()
        } }, update = { it.player = player }, modifier = modifier, onRelease = { it.player = null })''',
    '''        V121VodSurface(player, isTv, modifier)''')

player = java / "ui/PlayerScreen.kt"
replace_once(player, '''    LaunchedEffect(player, item.resumeKey) {
        while (true) {
            playbackPositionMs = player.currentPosition.coerceAtLeast(0L)
            playbackDurationMs = player.duration.takeIf { it > 0L } ?: 0L
            delay(250L)
        }
    }''', '''    // VOD owns its progress clock inside V116VodPlayer; do not run a second parent clock.
    if (item.kind == MediaKind.LIVE) LaunchedEffect(player, item.resumeKey) {
        while (true) {
            playbackPositionMs = player.currentPosition.coerceAtLeast(0L)
            playbackDurationMs = player.duration.takeIf { it > 0L } ?: 0L
            delay(250L)
        }
    }''')

dialog = java / "ui/V115PlayerDialogs.kt"
replace_once(dialog,
    '                Text("Zeitmarken: SkipDB (skipdb.tv, ODbL 1.0), TheIntroDB (theintrodb.org), IntroDB (introdb.app). Serienzuordnung: TVmaze (tvmaze.com, CC BY-SA).",',
    '                if (isTv) V121FrameRateControl()\n'
    '                Text("Zeitmarken: SkipDB (skipdb.tv, ODbL 1.0), TheIntroDB (theintrodb.org), IntroDB (introdb.app). Serienzuordnung: TVmaze (tvmaze.com, CC BY-SA).",')
# Keep the additional TV option reachable even with many audio/subtitle tracks.
replace_once(dialog, 'import androidx.compose.foundation.horizontalScroll',
    'import androidx.compose.foundation.verticalScroll\nimport androidx.compose.foundation.horizontalScroll')
replace_once(dialog,
    '            Column(Modifier.padding(if (isTv) 24.dp else 18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {',
    '            Column(Modifier.heightIn(max = androidx.compose.ui.platform.LocalConfiguration.current.screenHeightDp.dp * .88f)\n'
    '                .verticalScroll(rememberScrollState()).padding(if (isTv) 24.dp else 18.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {')

tests = root / "app/src/test/java/de/epimediahub/app/ui"
tests.mkdir(parents=True, exist_ok=True)
for source in here.glob("*Test.kt"):
    shutil.copyfile(source, tests / source.name)

old_sound = root / "app/src/main/res/raw/epimedia_intro_organic_orchestral_chime.wav"
old_sound.unlink(missing_ok=True)
assert 'versionCode = 1021' in gradle.read_text()
assert 'V121VodSurface(player, isTv, modifier)' in vod.read_text()
assert 'v120RememberLicenseState' in (java / "EpiMediaHubApp.kt").read_text()
print("Android 1.0.21: English cinematic ident, Compose surface synchronization and TV frame-rate matching installed")
