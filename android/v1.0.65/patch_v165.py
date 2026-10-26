#!/usr/bin/env python3
"""v1.0.65: restore direct provider EPG after the v1.0.64 regression.

Apply after v164. Only EPG request/parse/retry behavior changes; the retained
Live playback, category navigation, autostart and smart passive sibling cache
remain intact. Audio sync is prepared separately before this patch is applied.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"

def replace(path, old, new, count=1):
    source = path.read_text()
    if source.count(old) != count:
        raise SystemExit(f"v165 EPG expected {count} anchors in {path}: {old[:110]}")
    path.write_text(source.replace(old, new, count))

gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1064", "versionCode = 1065")
replace(gradle, 'versionName = "1.0.64"', 'versionName = "1.0.65"')

vm = java / "MainViewModel.kt"
replace(vm, """else if (p.type == PlaylistType.XTREAM) V164Epg.load(item.id,
                    peers = { v162EpgWorker.peers(profileKey, item.id) },
                    cached = { id -> _ui.value.epg[id].orEmpty() },
                    fetch = { id -> XtreamClient(p).shortEpg(id) },
                    publish = { id, events ->
                        // These callbacks run off-thread; publish only after returning to Main.
                    })""",
    "else if (p.type == PlaylistType.XTREAM) XtreamClient(p).shortEpg(item.id)")

# The extra 2 sibling downloads could occupy the playing-channel slot for
# up to 15 seconds and return only partial or future programme data.
# Direct provider responses stay authoritative; the safe v162 passive cache
# can still share EPG that was independently fetched for another resolution.
queue = java / "data/V163EpgQueue.kt"
replace(queue,
    "val cooldown = if (priority) minOf(retryAfterMs, 1_500L) else retryAfterMs",
    "val cooldown = if (priority) minOf(retryAfterMs, 6_000L) else retryAfterMs")

# Let the selected channel retry without reopening it, but don't hammer the
# Xtream endpoint with a new request every 1.6 seconds.
banner = java / "ui/V163EpgBanner.kt"
replace(banner, """    LaunchedEffect(item.resumeKey, current?.start, current?.end, now) {
        // Missing/empty first replies retry while the same sender stays open.
        // The queue coalesces pending work and applies the playback cooldown.
        repeat(if (current == null) 8 else 1) {
            vm.ensureEpg(item, priority = true)
            if (current == null) delay(1_600L)
        }
    }""",
    """    LaunchedEffect(item.resumeKey, now) {
        vm.ensureEpg(item, priority = true)
        if (current == null) {
            // One bounded retry, never a continuous network flood.
            delay(6_100L)
            vm.ensureEpg(item, priority = true)
        }
    }""")

client = java / "data/XtreamClient.kt"
replace(client,
    """connectTimeout = if (safeRequestName(url) == "get_short_epg") 3_000 else 10000
                readTimeout = if (safeRequestName(url) == "get_short_epg") 5_000 else 25000""",
    """connectTimeout = 10000
                readTimeout = 25000""")
replace(client, "&limit=12", "&limit=4")
replace(client, """V164Epg.seconds(o.optLong("start_timestamp")),
                        V164Epg.seconds(o.optLong("stop_timestamp", o.optLong("end_timestamp")))""",
    """o.optLong("start_timestamp"),
                        o.optLong("stop_timestamp")""")

assert "V164Epg.load(" not in vm.read_text()
assert "V163Epg.current(list," in vm.read_text()
assert "V162EpgWorker(" in vm.read_text()
assert "liveBackgroundPlayer" in vm.read_text()
assert "V163LiveInfoPanel(" in (java / "ui/V076LiveTv.kt").read_text()
tests = root / "app/src/test/java/de/epimediahub/app/data"
tests.mkdir(parents=True, exist_ok=True)
shutil.copyfile(here / "V165EpgRecoveryTest.kt", tests / "V165EpgRecoveryTest.kt")
legacy = tests / "V164EpgTest.kt"
replace(legacy, "clock = 1_499L", "clock = 5_999L")
replace(legacy, "clock = 1_600L", "clock = 6_000L")
sound = here / "epimedia_intro_v7.mp4"
if not sound.is_file():
    raise SystemExit("Synchronized 17.5s intro v7 not generated")
shutil.copyfile(sound, root / "app/src/main/res/raw/epimedia_intro_v5.mp4")
print("v1.0.65: direct EPG restored, restrained retry, original provider timeouts and 4-item short EPG; synchronized heartbeat intro.")
