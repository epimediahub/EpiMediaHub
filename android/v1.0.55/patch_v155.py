#!/usr/bin/env python3
"""v1.0.55 PRIVATE GalaBox/Android TV exact-stream beta, on top of v1.0.54.

Changes only the non-Amazon live XTREAM prepare path; Fire TV path, VPN,
saved Playlists, all other player settings and library data are unchanged.
No official update manifest is modified.
"""
from pathlib import Path
import os
import shutil

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"

def replace(path: Path, old: str, new: str):
    source = path.read_text()
    assert source.count(old) == 1, (str(path), source.count(old), old[:150])
    path.write_text(source.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace(gradle, 'versionCode = 1054', 'versionCode = 1055')
replace(gradle, 'versionName = "1.0.54"', 'versionName = "1.0.55"')

src = java / "data/XtreamClient.kt"
replace(src,
'''        prefetchExactM3uAsync()
        return item
    }

    fun streamCandidates(item: MediaEntry): List<String> {''',
'''        // v1.0.55: Some XTREAM providers supply valid per-channel URLs only
        // in their authenticated M3U. On non-Fire Android TV, do a bounded
        // one-ID streaming lookup on the existing IO dispatcher. On failure
        // retain every legacy address candidate unchanged.
        if (item.kind == MediaKind.LIVE && V155ExactM3uLive.nonFireTvDevice()) {
            val exactLive = V155ExactM3uLive.resolve(providerM3uUrl(), item.id, m3uStreamKey())
            if (!exactLive.isNullOrBlank()) return item.copy(streamUrl = exactLive)
        }
        prefetchExactM3uAsync()
        return item
    }

    fun streamCandidates(item: MediaEntry): List<String> {''')

shutil.copyfile(here / "V155ExactM3uLive.kt", java / "data/V155ExactM3uLive.kt")
shutil.copyfile(here / "V155ExactM3uLiveTest.kt",
                tests / "data/V155ExactM3uLiveTest.kt")

source = src.read_text()
assert source.count("V155ExactM3uLive.nonFireTvDevice()") == 1
assert 'if (exactLive.isNullOrBlank())' not in source
assert 'fun streamCandidates(item: MediaEntry): List<String>' in source
assert 'return urls.filter { it.isNotBlank() && it != "null" }.distinct()' in source
assert '"VLC/3.0.21 LibVLC/3.0.21"' in source

# No new VPN route or Fire TV player source code should be touched.
print("v1.0.55 private GalaBox beta: bounded exact provider M3U lookup installed")
print("Fire TV, app VPN, Media3 / VLC configuration and existing fallback URLs unchanged")
