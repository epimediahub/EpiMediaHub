#!/usr/bin/env python3
"""v1.0.66: show Xtream NOW reliably without changing Live playback or navigation."""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
here = Path(__file__).resolve().parent
java = root / "app/src/main/java/de/epimediahub/app"

def replace(path, old, new, count=1):
    source = path.read_text()
    actual = source.count(old)
    if actual != count:
        raise SystemExit(f"v166 expected {count} anchors, got {actual} in {path}: {old[:110]}")
    path.write_text(source.replace(old, new, count))

gradle = root / "app/build.gradle.kts"
replace(gradle, "versionCode = 1065", "versionCode = 1066")
replace(gradle, 'versionName = "1.0.65"', 'versionName = "1.0.66"')

shutil.copyfile(here / "V166EpgRows.kt", java / "data/V166EpgRows.kt")
tests = root / "app/src/test/java/de/epimediahub/app/data"
shutil.copyfile(here / "V166EpgNowTest.kt", tests / "V166EpgNowTest.kt")

client = java / "data/XtreamClient.kt"
before = '''    fun shortEpg(streamId: String): List<EpgItem> {
        val root = objectAction("get_short_epg", "&stream_id=${enc(streamId)}&limit=4")
        val a = root.optJSONArray("epg_listings") ?: return emptyList()
        fun b64(o: JSONObject, k: String) = runCatching {
            String(Base64.decode(o.optString(k), Base64.DEFAULT))
        }.getOrDefault(o.optString(k))
        return buildList {
            for (i in 0 until a.length()) {
                val o = a.optJSONObject(i) ?: continue
                add(
                    EpgItem(
                        b64(o, "title"),
                        b64(o, "description"),
                        o.optLong("start_timestamp"),
                        o.optLong("stop_timestamp")
                    )
                )
            }
        }
    }'''
after = '''    fun shortEpg(streamId: String, requireCurrent: Boolean = false): List<EpgItem> {
        // A short response may omit NOW and show NEXT alone. Parse alternate
        // timestamp units/fields before deciding whether the programme is absent.
        val now = System.currentTimeMillis() / 1000L
        val short = runCatching {
            V166EpgRows.parse(objectAction("get_short_epg",
                "&stream_id=${enc(streamId)}&limit=12"), now)
        }.getOrDefault(emptyList())
        if (!requireCurrent || V163Epg.current(short, now) != null) return short

        // Only the actively inspected/playing channel requires the full table;
        // prefetching all Live channels must never cause a provider-wide flood.
        val complete = runCatching {
            V166EpgRows.parse(objectAction("get_simple_data_table",
                "&stream_id=${enc(streamId)}"), now)
        }.getOrDefault(emptyList())
        return if (V163Epg.current(complete, now) != null) complete
            else if (short.isNotEmpty()) short else complete
    }'''
replace(client, before, after)

vm = java / "MainViewModel.kt"
replace(vm,
    'else if (p.type == PlaylistType.XTREAM) XtreamClient(p).shortEpg(item.id)',
    'else if (p.type == PlaylistType.XTREAM) XtreamClient(p).shortEpg(item.id, requireCurrent = true)')
# A warmup response can finish AFTER the playing-channel full-table response.
# Never let its future-only short list evict the available current event.
replace(vm, 'set { it.copy(epgLoading = false, epg = it.epg + map) }',
    '''set { state -> state.copy(epgLoading = false,
        epg = V166EpgMerge.merge(state.epg, map, System.currentTimeMillis() / 1000L)) }''')
replace(vm, 'if (list.isNotEmpty()) set { it.copy(epg = it.epg + (item.id to list)) }',
    '''if (list.isNotEmpty()) set { state -> state.copy(
                epg = V166EpgMerge.merge(state.epg, mapOf(item.id to list),
                    System.currentTimeMillis() / 1000L)) }''')

# The four-channel background warmup still uses one inexpensive short call.
assert 'client.shortEpg(channel.id)' in vm.read_text()
assert 'requireCurrent = true' in vm.read_text()
assert 'get_simple_data_table' in client.read_text()
assert 'V164LiveNavigation.resume(' in vm.read_text()
assert 'V163LiveInfoPanel(' in (java / "ui/V076LiveTv.kt").read_text()
print("v1.0.66: resilient Xtream EPG timestamps, local/UTC display date fallback and targeted full guide only when NOW missing.")
