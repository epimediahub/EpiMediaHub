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


# ---------------------------------------------------------------------------
# Pluto TV + Rakuten TV as a first-class FAST/streaming directory.
# We deliberately hand protected/commercial playback to the official apps or
# websites instead of depending on undocumented private playback APIs.
# ---------------------------------------------------------------------------
client = java / "data/MediathekClient.kt"
s = client.read_text()

provider_fields_old = '''        val availability: String = "",
        val info: String = "",
        val playable: Boolean = true
    )
'''
provider_fields_new = '''        val availability: String = "",
        val info: String = "",
        val playable: Boolean = true,
        val externalUrl: String = "",
        val appPackages: List<String> = emptyList()
    )
'''
if provider_fields_old not in s:
    raise SystemExit("Mediathek Provider field anchor missing")
s = s.replace(provider_fields_old, provider_fields_new, 1)

country_old = '''        Country("fr", "Frankreich / International", "ARTE France · TV5MONDEplus", "Französische und internationale öffentlich zugängliche Angebote.")
    )
'''
country_new = '''        Country("fr", "Frankreich / International", "ARTE France · TV5MONDEplus", "Französische und internationale öffentlich zugängliche Angebote."),
        Country("fast", "Kostenloses Streaming", "Pluto TV · Rakuten TV", "Kostenlose werbefinanzierte Live-Sender und On-Demand-Angebote über die offiziellen Apps bzw. Webseiten.")
    )
'''
if country_old not in s:
    raise SystemExit("Mediathek country list anchor missing")
s = s.replace(country_old, country_new, 1)

provider_tail_old = '''        Provider("tv5", "fr", "TV5MONDEplus", availability = "International · kostenlos", info = "Anbieterübersicht; direkte native Wiedergabe wird erst bei einer stabilen offenen Stream-Schnittstelle aktiviert.", playable = false)
    )
'''
provider_tail_new = '''        Provider("tv5", "fr", "TV5MONDEplus", availability = "International · kostenlos", info = "Anbieterübersicht; direkte native Wiedergabe wird erst bei einer stabilen offenen Stream-Schnittstelle aktiviert.", playable = false),
        Provider(
            "pluto", "fast", "Pluto TV",
            availability = "Kostenlos · Live-TV + On Demand",
            info = "Pluto TV wird über die offizielle App geöffnet. Falls sie nicht installiert ist, öffnet EpiMediaHub die offizielle Pluto-TV-Webseite.",
            playable = false,
            externalUrl = "https://pluto.tv/",
            appPackages = listOf("tv.pluto.android")
        ),
        Provider(
            "rakuten", "fast", "Rakuten TV",
            availability = "Kostenloser Live-TV + Free VOD",
            info = "Rakuten TV wird über die offizielle TV-/Android-App geöffnet. Falls sie nicht installiert ist, öffnet EpiMediaHub die offizielle Rakuten-TV-Webseite.",
            playable = false,
            externalUrl = "https://www.rakuten.tv/de",
            appPackages = listOf("tv.wuaki.apptv", "tv.wuaki")
        )
    )
'''
if provider_tail_old not in s:
    raise SystemExit("Mediathek provider tail anchor missing")
s = s.replace(provider_tail_old, provider_tail_new, 1)
client.write_text(s)


# ---------------------------------------------------------------------------
# Android 11+/Fire OS package visibility: getLaunchIntentForPackage can only
# reliably see the streaming apps when they are declared as queried packages.
# ---------------------------------------------------------------------------
manifest = root / "app/src/main/AndroidManifest.xml"
ms = manifest.read_text()
if 'tv.pluto.android' not in ms:
    app_anchor = '    <application\n'
    if app_anchor not in ms:
        raise SystemExit("AndroidManifest application anchor missing")
    queries = '''    <queries>
        <package android:name="tv.pluto.android" />
        <package android:name="tv.wuaki.apptv" />
        <package android:name="tv.wuaki" />
    </queries>
'''
    ms = ms.replace(app_anchor, queries + app_anchor, 1)
manifest.write_text(ms)


# ---------------------------------------------------------------------------
# Mediathek UI: external FAST providers have their own clean detail page.
# No dead search field is shown; OK on the main action opens the official app,
# and a browser fallback is used when the app is not installed.
# ---------------------------------------------------------------------------
parity = java / "ui/ParityScreens.kt"
s = parity.read_text()

if 'import android.content.Context\n' not in s:
    pkg = 'package de.epimediahub.app.ui\n\n'
    if pkg not in s:
        raise SystemExit("ParityScreens package anchor missing")
    s = s.replace(
        pkg,
        pkg + 'import android.content.Context\nimport android.content.Intent\nimport android.net.Uri\nimport android.widget.Toast\n',
        1,
    )

focus_import = 'import androidx.compose.ui.focus.onFocusChanged\n'
if focus_import not in s:
    raise SystemExit("ParityScreens focus import missing")
if 'import androidx.compose.ui.platform.LocalContext\n' not in s:
    s = s.replace(focus_import, focus_import + 'import androidx.compose.ui.platform.LocalContext\n', 1)

function_anchor = '''fun ParityMediathekListScreen(vm: MainViewModel, providerId: String, accent: Color, isTv: Boolean) {
    val provider = remember(providerId) { MediathekClient.provider(providerId) }
'''
function_new = '''fun ParityMediathekListScreen(vm: MainViewModel, providerId: String, accent: Color, isTv: Boolean) {
    val provider = remember(providerId) { MediathekClient.provider(providerId) }
    val context = LocalContext.current
'''
if function_anchor not in s:
    raise SystemExit("Mediathek list context anchor missing")
s = s.replace(function_anchor, function_new, 1)

nonplayable_old = '''        if (!p.playable) {
            entries = emptyList()
            error = p.info.ifBlank { "Für diesen Anbieter ist derzeit keine stabile offene Stream-Schnittstelle verfügbar." }
            return@LaunchedEffect
        }
'''
nonplayable_new = '''        if (!p.playable) {
            entries = emptyList()
            error = if (p.externalUrl.isNotBlank()) {
                "Kostenloses Streaming über den offiziellen Anbieter."
            } else {
                p.info.ifBlank { "Für diesen Anbieter ist derzeit keine stabile offene Stream-Schnittstelle verfügbar." }
            }
            return@LaunchedEffect
        }
'''
if nonplayable_old not in s:
    raise SystemExit("Mediathek non-playable anchor missing")
s = s.replace(nonplayable_old, nonplayable_new, 1)

controls_old = '''        Row(
            Modifier.fillMaxWidth().padding(horizontal = if (isTv) 60.dp else 12.dp, vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            if (isTv) {
                OutlinedButton(onClick = { searchDialog = true }, modifier = Modifier.weight(1f)) {
                    Icon(Icons.Default.Search, null)
                    Spacer(Modifier.width(8.dp))
                    Text("Mediathek durchsuchen")
                }
            } else {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    label = { Text("Mediathek durchsuchen") },
                    leadingIcon = { Icon(Icons.Default.Search, null) },
                    singleLine = true,
                    modifier = Modifier.weight(1f)
                )
                Button(onClick = { submitted = query.trim(); reload++ }, colors = ButtonDefaults.buttonColors(containerColor = accent)) { Text("Suchen") }
            }
            OutlinedButton(onClick = { reload++ }) { Text("Neu laden") }
        }
'''
controls_new = '''        if (provider?.externalUrl.isNullOrBlank()) {
            Row(
                Modifier.fillMaxWidth().padding(horizontal = if (isTv) 60.dp else 12.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                if (isTv) {
                    OutlinedButton(onClick = { searchDialog = true }, modifier = Modifier.weight(1f)) {
                        Icon(Icons.Default.Search, null)
                        Spacer(Modifier.width(8.dp))
                        Text("Mediathek durchsuchen")
                    }
                } else {
                    OutlinedTextField(
                        value = query,
                        onValueChange = { query = it },
                        label = { Text("Mediathek durchsuchen") },
                        leadingIcon = { Icon(Icons.Default.Search, null) },
                        singleLine = true,
                        modifier = Modifier.weight(1f)
                    )
                    Button(onClick = { submitted = query.trim(); reload++ }, colors = ButtonDefaults.buttonColors(containerColor = accent)) { Text("Suchen") }
                }
                OutlinedButton(onClick = { reload++ }) { Text("Neu laden") }
            }
        }
'''
if controls_old not in s:
    raise SystemExit("Mediathek controls anchor missing")
s = s.replace(controls_old, controls_new, 1)

info_old = '''                        provider?.info?.takeIf { it.isNotBlank() && it != error }?.let { Text(it, color = Color.White.copy(.82f), fontSize = 14.sp, modifier = Modifier.padding(top = 10.dp)) }
'''
info_new = '''                        provider?.info?.takeIf { it.isNotBlank() && it != error }?.let { Text(it, color = Color.White.copy(.82f), fontSize = 14.sp, modifier = Modifier.padding(top = 10.dp)) }
                        provider?.takeIf { it.externalUrl.isNotBlank() }?.let { external ->
                            Spacer(Modifier.height(18.dp))
                            Button(
                                onClick = { openExternalMediathekProvider(context, external) },
                                colors = ButtonDefaults.buttonColors(containerColor = accent),
                                modifier = Modifier.height(if (isTv) 54.dp else 48.dp)
                            ) {
                                Icon(Icons.Default.PlayArrow, null)
                                Spacer(Modifier.width(8.dp))
                                Text("${external.label} öffnen", fontWeight = FontWeight.Black)
                            }
                        }
'''
if info_old not in s:
    raise SystemExit("Mediathek provider info anchor missing")
s = s.replace(info_old, info_new, 1)

helper_anchor = '''@Composable
fun ParityEpgGridScreen(vm: MainViewModel, category: de.epimediahub.app.model.MediaCategory, accent: Color, isTv: Boolean) {
'''
helper = '''private fun openExternalMediathekProvider(context: Context, provider: MediathekClient.Provider) {
    for (packageName in provider.appPackages) {
        val launch = runCatching { context.packageManager.getLaunchIntentForPackage(packageName) }.getOrNull()
        if (launch != null) {
            launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            runCatching { context.startActivity(launch) }
                .onSuccess { return }
        }
    }

    val url = provider.externalUrl
    if (url.isBlank()) return
    val browser = Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    val opened = runCatching {
        context.startActivity(browser)
        true
    }.getOrDefault(false)
    if (!opened) {
        Toast.makeText(context, "${provider.label} konnte auf diesem Gerät nicht geöffnet werden.", Toast.LENGTH_LONG).show()
    }
}

@Composable
fun ParityEpgGridScreen(vm: MainViewModel, category: de.epimediahub.app.model.MediaCategory, accent: Color, isTv: Boolean) {
'''
if helper_anchor not in s:
    raise SystemExit("Mediathek helper insertion anchor missing")
s = s.replace(helper_anchor, helper, 1)
parity.write_text(s)


checks = [
    (client, 'Country("fast", "Kostenloses Streaming", "Pluto TV · Rakuten TV"'),
    (client, 'externalUrl = "https://pluto.tv/"'),
    (client, 'appPackages = listOf("tv.pluto.android")'),
    (client, 'externalUrl = "https://www.rakuten.tv/de"'),
    (client, 'appPackages = listOf("tv.wuaki.apptv", "tv.wuaki")'),
    (manifest, '<package android:name="tv.pluto.android" />'),
    (manifest, '<package android:name="tv.wuaki.apptv" />'),
    (parity, 'private fun openExternalMediathekProvider(context: Context, provider: MediathekClient.Provider)'),
    (parity, 'getLaunchIntentForPackage(packageName)'),
    (parity, 'Text("${external.label} öffnen", fontWeight = FontWeight.Black)'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.6.4.11 FAST marker {marker} in {path}")

print("Android v0.6.4.11 Pluto TV + Rakuten TV FAST directory and official-app handoff applied")
