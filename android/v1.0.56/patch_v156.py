#!/usr/bin/env python3
"""v1.0.56 private fast-zapping beta. Apply strictly after v1.0.55.

v1.0.55 downloaded/scanned the provider M3U each LIVE channel selection;
v1.0.56 warms one bounded in-memory index per playlist in the background
during live catalog loading, and reads exact URLs by O(1) stream-id lookup.
Fire TV, VPN policy, existing candidates, stored profiles untouched.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (str(path), text.count(old), old[:140])
    path.write_text(text.replace(old, new, 1))

build = root / "app/build.gradle.kts"
replace(build, "versionCode = 1055", "versionCode = 1056")
replace(build, 'versionName = "1.0.55"', 'versionName = "1.0.56"')

client = java / "data/XtreamClient.kt"
replace(client,
'''            val exactLive = V155ExactM3uLive.resolve(providerM3uUrl(), item.id, m3uStreamKey())
            if (!exactLive.isNullOrBlank()) return item.copy(streamUrl = exactLive)''',
'''            // M3U was already prefetched once, during Live catalogue loading.
            // A warm-cache lookup requires zero HTTP calls on each channel zap.
            // At cold start, one shared request may still be awaited.
            val exactLive = V156ExactM3uCache.resolve(m3uStreamKey() + "|" + p.password, providerM3uUrl(), item.id)
            if (!exactLive.isNullOrBlank()) return item.copy(streamUrl = exactLive)''')
replace(client,
'''        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()''',
'''        if (kind == MediaKind.LIVE && V155ExactM3uLive.nonFireTvDevice() &&
            providerOutputFormat() !in setOf("mpegts", "mpeg-ts")) {
            V156ExactM3uCache.warm(m3uStreamKey() + "|" + p.password, providerM3uUrl())
        }
        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()''')

shutil.copyfile(here / "V156ExactM3uCache.kt", java / "data/V156ExactM3uCache.kt")
shutil.copyfile(here / "V156ExactM3uCacheTest.kt", tests / "data/V156ExactM3uCacheTest.kt")

s = client.read_text()
assert s.count("V156ExactM3uCache.resolve(") == 1
assert s.count("V156ExactM3uCache.warm(") == 1
assert "V155ExactM3uLive.resolve(" not in s
assert "V155ExactM3uLive.nonFireTvDevice()" in s
assert "fun streamCandidates(item: MediaEntry)" in s
assert "return urls.filter { it.isNotBlank() && it != \"null\" }.distinct()" in s
print("v1.0.56: one bounded provider M3U index per playlist, instant cached live zaps")
print("v1.0.54 Fire TV route/player and EpiMediaHub VPN remain unchanged")
