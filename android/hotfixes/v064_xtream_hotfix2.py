#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# Make this hotfix visibly distinguishable and upgradeable on-device while keeping
# the public release asset filename/URL unchanged.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 604', 'versionCode = 605', 'hotfix2 versionCode')
replace_once(gradle, 'versionName = "0.6.4"', 'versionName = "0.6.4.2"', 'hotfix2 versionName')

home = java / "ui/V044Home.kt"
home_text = home.read_text()
if "0.6.4" not in home_text:
    raise SystemExit("visible home version 0.6.4 not found")
home.write_text(home_text.replace("0.6.4", "0.6.4.2", 1))

xtream = java / "data/XtreamClient.kt"
s = xtream.read_text()

old_http = r'''    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")
    private fun api(action: String, extra: String = "") =
        "${p.server}/player_api.php?username=${enc(p.username)}&password=${enc(p.password)}&action=$action$extra"

    private fun text(url: String): String {
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 10000
            readTimeout = 25000
            setRequestProperty("User-Agent", "EpiMediaHub-Android/0.3.3")
        }
        return try {
            val code = c.responseCode
            if (code !in 200..299) error("Xtream HTTP $code")
            c.inputStream.bufferedReader().use { it.readText() }
        } finally {
            c.disconnect()
        }
    }

    private fun array(url: String) = JSONArray(text(url))
'''

new_http = r'''    private fun enc(s: String) = URLEncoder.encode(s, "UTF-8")

    private fun apiWithEndpoint(endpoint: String, action: String, extra: String = "") =
        "${p.server.trimEnd('/')}/$endpoint?username=${enc(p.username)}&password=${enc(p.password)}&action=$action$extra"

    private fun api(action: String, extra: String = "") = apiWithEndpoint("player_api.php", action, extra)

    private fun apiCandidates(action: String, extra: String = "") = listOf(
        apiWithEndpoint("player_api.php", action, extra),
        apiWithEndpoint("panel_api.php", action, extra)
    ).distinct()

    private fun safeRequestName(url: String): String {
        val parsed = runCatching { Uri.parse(url) }.getOrNull()
        val action = parsed?.getQueryParameter("action").orEmpty().trim()
        if (action.isNotBlank()) return action
        return when {
            url.contains("get.php", ignoreCase = true) -> "get.php"
            url.contains("player_api.php", ignoreCase = true) -> "player_api"
            url.contains("panel_api.php", ignoreCase = true) -> "panel_api"
            else -> "request"
        }
    }

    private fun text(url: String): String {
        var current = url
        repeat(5) {
            val c = (URL(current).openConnection() as HttpURLConnection).apply {
                connectTimeout = 10000
                readTimeout = 25000
                instanceFollowRedirects = false
                setRequestProperty("User-Agent", "VLC/3.0.21 LibVLC/3.0.21")
                setRequestProperty("Accept", "*/*")
            }
            try {
                val code = c.responseCode
                if (code in listOf(301, 302, 303, 307, 308)) {
                    val location = c.getHeaderField("Location").orEmpty().trim()
                    if (location.isBlank()) error("Xtream ${safeRequestName(current)} redirect without location")
                    current = URL(URL(current), location).toString()
                    return@repeat
                }
                if (code !in 200..299) error("Xtream ${safeRequestName(current)} HTTP $code")
                return c.inputStream.bufferedReader().use { it.readText() }
            } finally {
                c.disconnect()
            }
        }
        error("Xtream ${safeRequestName(current)} too many redirects")
    }

    private fun array(url: String) = JSONArray(text(url))

    private fun arrayAction(action: String, extra: String = ""): JSONArray {
        var last: Throwable? = null
        apiCandidates(action, extra).forEach { url ->
            try {
                return JSONArray(text(url))
            } catch (t: Throwable) {
                last = t
            }
        }
        throw last ?: IllegalStateException("Xtream $action failed")
    }

    private fun objectAction(action: String, extra: String = ""): JSONObject {
        var last: Throwable? = null
        apiCandidates(action, extra).forEach { url ->
            try {
                return JSONObject(text(url))
            } catch (t: Throwable) {
                last = t
            }
        }
        throw last ?: IllegalStateException("Xtream $action failed")
    }
'''
if old_http not in s:
    raise SystemExit("Xtream HTTP/API anchor missing")
s = s.replace(old_http, new_http, 1)

old_categories = '''        val a = array(api(action))
        return buildList {
'''
new_categories = '''        val a = runCatching { arrayAction(action) }.getOrElse {
            return listOf(MediaCategory("__all__", "Alle"))
        }
        return buildList {
'''
if old_categories not in s:
    raise SystemExit("categories array anchor missing")
s = s.replace(old_categories, new_categories, 1)

old_entries = '''        val extra = if (categoryId.isNullOrBlank()) "" else "&category_id=${enc(categoryId)}"
        val a = array(api(action, extra))
        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()
'''
new_entries = '''        val requestedCategory = categoryId.orEmpty().trim().takeUnless { it == "__all__" }.orEmpty()
        val extra = if (requestedCategory.isBlank()) "" else "&category_id=${enc(requestedCategory)}"
        val a = if (requestedCategory.isBlank()) {
            arrayAction(action)
        } else {
            runCatching { arrayAction(action, extra) }.getOrElse {
                val all = arrayAction(action)
                JSONArray().also { filtered ->
                    for (i in 0 until all.length()) {
                        val row = all.optJSONObject(i) ?: continue
                        if (row.optString("category_id") == requestedCategory) filtered.put(row)
                    }
                }
            }
        }
        val streamServer = if (kind == MediaKind.LIVE || kind == MediaKind.MOVIE) resolveStreamServer() else cachedStreamServer()
'''
if old_entries not in s:
    raise SystemExit("entries API anchor missing")
s = s.replace(old_entries, new_entries, 1)

replacements = [
    ('JSONObject(text(api("get_vod_info", "&vod_id=${enc(item.id)}")))', 'objectAction("get_vod_info", "&vod_id=${enc(item.id)}")', 'vod details API'),
    ('JSONObject(text(api("get_series_info", "&series_id=${enc(id)}")))', 'objectAction("get_series_info", "&series_id=${enc(id)}")', 'series details API'),
    ('JSONObject(text(api("get_series_info", "&series_id=${enc(seriesId)}")))', 'objectAction("get_series_info", "&series_id=${enc(seriesId)}")', 'episodes API'),
    ('JSONObject(text(api("get_short_epg", "&stream_id=${enc(streamId)}&limit=4")))', 'objectAction("get_short_epg", "&stream_id=${enc(streamId)}&limit=4")', 'short EPG API'),
]
for old, new, label in replacements:
    if old not in s:
        raise SystemExit(f"{label} anchor missing")
    s = s.replace(old, new, 1)

xtream.write_text(s)

# Sanity markers.
xf = xtream.read_text()
for marker in [
    'apiWithEndpoint("panel_api.php"',
    'arrayAction(action, extra)',
    'val all = arrayAction(action)',
    'row.optString("category_id") == requestedCategory',
    'Xtream ${safeRequestName(current)} HTTP $code',
    'VLC/3.0.21 LibVLC/3.0.21',
    'objectAction("get_vod_info"',
    'objectAction("get_series_info"',
]:
    if marker not in xf:
        raise SystemExit(f"missing Xtream hotfix2 marker: {marker}")

print("Android v0.6.4.2 Xtream API compatibility hotfix applied")
