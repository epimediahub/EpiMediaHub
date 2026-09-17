#!/usr/bin/env python3
from pathlib import Path
import os

root=Path(os.environ.get("PROJECT_ROOT","."))
java=root/"app/src/main/java/de/epimediahub/app"
gradle=root/"app/build.gradle.kts"
s=gradle.read_text()
if 'versionCode = 54' not in s or 'versionName = "0.4.14"' not in s: raise SystemExit('v0.4.14 version anchors missing')
gradle.write_text(s.replace('versionCode = 54','versionCode = 55',1).replace('versionName = "0.4.14"','versionName = "0.4.15"',1))
for rel in ["ui/V044Home.kt","ui/Screens.kt","data/MediathekClient.kt"]:
 p=java/rel
 if p.exists(): p.write_text(p.read_text().replace('0.4.14','0.4.15'))

# v0.4.12 returned the first reachable metadata source. A stale main/android/update.json
# could therefore hide a newer android-latest release. Query all independent sources
# and choose the highest valid versionCode instead.
manager=java/"data/UpdateManager.kt"
m=manager.read_text()
start=m.index('    private fun fetchLatestInfo(): AppUpdateInfo {')
end=m.index('\n    suspend fun downloadApk',start)
new=r'''    private fun fetchLatestInfo(): AppUpdateInfo {
        val errors = mutableListOf<String>()
        val candidates = mutableListOf<Pair<String, AppUpdateInfo>>()

        fun candidate(source: String, block: () -> AppUpdateInfo) {
            runCatching(block)
                .onSuccess { candidates += source to it }
                .onFailure { errors += "$source: ${shortError(it)}" }
        }

        candidate("raw") { parseManifest(JSONObject(fetchJson(MANIFEST_RAW_URL))) }
        candidate("api-manifest") {
            parseManifest(JSONObject(fetchJson(MANIFEST_API_URL, "application/vnd.github.raw+json")))
        }
        candidate("release") {
            parseRelease(JSONObject(fetchJson(RELEASE_API_URL, "application/vnd.github+json")))
        }

        if (candidates.isEmpty()) {
            error("Update-Metadaten konnten nicht geladen werden. ${errors.joinToString(" | ")}")
        }
        return candidates.maxByOrNull { it.second.versionCode }!!.second
    }
'''
m=m[:start]+new+m[end:]
manager.write_text(m)

# Make manual update checks self-diagnosing on TV: show installed/server versions,
# while preserving the concrete network/JSON error already surfaced by UpdateScreen.
screen=java/"ui/UpdateScreen.kt"
u=screen.read_text()
if 'import de.epimediahub.app.BuildConfig' not in u:
 anchor='package de.epimediahub.app.ui\n'
 if anchor not in u: raise SystemExit('UpdateScreen package anchor missing')
 u=u.replace(anchor,anchor+'import de.epimediahub.app.BuildConfig\n',1)
old='message = if (found == null) "Du nutzt bereits die aktuelle Version." else "Neue Version ${found.version} gefunden."'
newmsg='message = if (found == null) "Installiert: ${BuildConfig.VERSION_NAME} / Server: keine neuere Version" else "Installiert: ${BuildConfig.VERSION_NAME} / Server: ${found.version} – Update gefunden."'
if old not in u: raise SystemExit('UpdateScreen diagnostic anchor missing')
u=u.replace(old,newmsg,1)
screen.write_text(u)
print('Android v0.4.15 updater metadata selection and diagnostics installed')
