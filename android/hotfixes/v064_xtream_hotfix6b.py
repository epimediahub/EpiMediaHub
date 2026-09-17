#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
player = root / "app/src/main/java/de/epimediahub/app/ui/PlayerScreen.kt"
s = player.read_text()

old = '''        val loadControl = DefaultLoadControl.Builder()
            .setBufferDurationsMs(750, 3_000, 150, 300)
            .setPrioritizeTimeOverSizeThresholds(true)
            .build()
        val exo = ExoPlayer.Builder(context)
            .setLoadControl(loadControl)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
            .build()
'''
new = '''        val exoBuilder = ExoPlayer.Builder(context)
            .setMediaSourceFactory(DefaultMediaSourceFactory(context).setDataSourceFactory(httpFactory))
        if (item.kind == MediaKind.LIVE) {
            val liveLoadControl = DefaultLoadControl.Builder()
                .setBufferDurationsMs(750, 3_000, 150, 300)
                .setPrioritizeTimeOverSizeThresholds(true)
                .build()
            exoBuilder.setLoadControl(liveLoadControl)
        }
        val exo = exoBuilder.build()
'''
if s.count(old) != 1:
    raise SystemExit(f"conditional Live load-control anchor mismatch: {s.count(old)}")
s = s.replace(old, new, 1)
player.write_text(s)

final = player.read_text()
assert 'if (item.kind == MediaKind.LIVE)' in final
assert 'val liveLoadControl = DefaultLoadControl.Builder()' in final
assert '.setBufferDurationsMs(750, 3_000, 150, 300)' in final
assert 'exoBuilder.setLoadControl(liveLoadControl)' in final
print("Android v0.6.4.6 Live-only fast buffer patch applied")
