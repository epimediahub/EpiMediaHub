#!/usr/bin/env python3
"""Private v168: expose VOD playback diagnostics and a reversible VLC comparison.

No public updater changes. Uses v167 already verified and leaves Live handling
and the standard VOD chrome untouched except for one accessible info control.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"

def replace(path, old, new, count=1):
    data = path.read_text()
    if data.count(old) != count:
        raise SystemExit("v168 source mismatch in %s: %s (%d)" %
            (path, old[:100], data.count(old)))
    path.write_text(data.replace(old, new, count))

gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1067", "versionCode = 1068")
replace(gradle, 'versionName = "1.0.67"', 'versionName = "1.0.68"')
shutil.copyfile(here / "V168VlcVodPlayer.kt", java / "ui/V168VlcVodPlayer.kt")

screen = java / "ui/PlayerScreen.kt"
replace(screen, '''    if (useVlc) {
        V071VlcLivePlayer(vm, item, episodeList, accent, isTv, compatibilityUrl, covered) {
            manualPlayerChoice = true
            useVlc = false
        }
        return
    }''', '''    if (useVlc) {
        if (item.kind == MediaKind.LIVE) {
            V071VlcLivePlayer(vm, item, episodeList, accent, isTv, compatibilityUrl, covered) {
                manualPlayerChoice = true
                useVlc = false
            }
        } else {
            // Dedicated VOD-compatible VLC test; no Live channel shortcuts.
            // The old Media3 player is disposed before this branch is displayed.
            val testRequest = parseIptvHttpRequest(compatibilityUrl.ifBlank { item.streamUrl })
            V168VlcVodPlayer(vm, item, episodeList, isTv,
                testRequest.url, testRequest.userAgent, testRequest.referer) {
                manualPlayerChoice = true
                useVlc = false
            }
        }
        return
    }''')
replace(screen, '''    if (item.kind != MediaKind.LIVE) {
        V116VodPlayer(
            player = player, item = item, episodes = episodeList, isTv = isTv, error = playbackError,
            onBack = ::leave,
            onEpisode = { selected -> save(); vm.selectV115Episode(item, selected, episodeList) },
            onAudioLanguage = vm::setAudioLanguage, onSubtitleLanguage = vm::setSubtitleLanguage
        )
        return
    }''', '''    if (item.kind != MediaKind.LIVE) {
        // VOD is rendered by its own chrome, so the outer Live info action
        // was previously unreachable. Intercept MENU/INFO in the VOD tree
        // and expose a focusable action for remotes without a Menu key.
        Box(Modifier.fillMaxSize().onPreviewKeyEvent { event ->
            if (covered || !isTv || event.nativeKeyEvent.action != KeyEvent.ACTION_DOWN)
                false
            else when (event.nativeKeyEvent.keyCode) {
                KeyEvent.KEYCODE_MENU, KeyEvent.KEYCODE_INFO -> {
                    if (event.nativeKeyEvent.repeatCount == 0) showPlaybackInfo = true
                    true
                }
                else -> false
            }
        }) {
            V116VodPlayer(
                player = player, item = item, episodes = episodeList, isTv = isTv, error = playbackError,
                onBack = ::leave,
                onEpisode = { selected -> save(); vm.selectV115Episode(item, selected, episodeList) },
                onAudioLanguage = vm::setAudioLanguage, onSubtitleLanguage = vm::setSubtitleLanguage
            )
            if (!covered) TextButton(onClick = { showPlaybackInfo = true },
                modifier = Modifier.align(Alignment.TopEnd).padding(10.dp).v114FocusRing()) {
                Text("Player / Diagnose")
            }
        }
        return
    }''')
assert "V168VlcVodPlayer(" in screen.read_text()
assert "Player / Diagnose" in screen.read_text()
print("v168 private: VOD player info via remote; isolated reversible VLC comparison")
