#!/usr/bin/env python3
"""VPN Finland beta: playlist toggle, verified selection, and global UI playback guard.

Requires V133 source + V134 test bridge; fail if source anchors changed.
No production release. The VPN app ID must end in .vpnbeta.
"""
import os
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root/"app/src/main/java/de/epimediahub/app"
build = (root/"app/build.gradle.kts").read_text()
assert 'applicationId = "de.epimediahub.app.vpnbeta"' in build, "Refusing production package"

def replace(path, old, new, expected=1):
    content=path.read_text()
    assert content.count(old)==expected, f"{path}: expected {expected} matches, got {content.count(old)} for {old[:110]!r}"
    path.write_text(content.replace(old,new))

playlist=java/"ui/V070Playlists.kt"
replace(playlist, "import kotlinx.coroutines.delay",
    """import kotlinx.coroutines.delay
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import androidx.compose.ui.platform.LocalContext
import android.content.Intent
import de.epimediahub.app.vpn.V134VpnSession
import de.epimediahub.app.vpn.V134VpnDiagnosticActivity""")
replace(playlist, "    val u by vm.ui.collectAsState()",
    """    val u by vm.ui.collectAsState()
    val context = LocalContext.current
    val scope = rememberCoroutineScope()
    var routingRevision by remember { mutableIntStateOf(0) }
    var routeBusy by remember { mutableStateOf(false) }
    var routeFailed by remember { mutableStateOf(false) }
    if (routeFailed) {
        AlertDialog(
            onDismissRequest = { routeFailed = false },
            title = { Text("VPN-Verbindung nicht bestätigt") },
            text = { Text("Der Playlist-Wechsel wurde angehalten. Zuerst VPN-Profil und Freigabe prüfen. Kein direkter Fallback.") },
            confirmButton = {
                TextButton(onClick = {
                    routeFailed = false
                    context.startActivity(Intent(context, V134VpnDiagnosticActivity::class.java))
                }) { Text("VPN-Einstellungen") }
            },
            dismissButton = { TextButton(onClick = { routeFailed = false }) { Text("Schließen") } }
        )
    }""")
replace(playlist, "                    val active = playlist.id == u.active?.id",
    """                    val active = playlist.id == u.active?.id
                    val vpnEnabled = remember(routingRevision, playlist.id) {
                        V134VpnSession.mode(context, playlist.id.toString())
                    }""")
replace(playlist, "                        active = active,",
    """                        active = active,
                        vpnEnabled = vpnEnabled,
                        onVpnToggle = {
                            V134VpnSession.setMode(context, playlist.id.toString(), !vpnEnabled)
                            routingRevision++
                        },""")
replace(playlist, "vm.selectPlaylist(playlist.id)",
    """if (!routeBusy) {
                            routeBusy = true
                            scope.launch {
                                // Never switch the IPTV source until the selected transport is verified.
                                val ready = withContext(Dispatchers.IO) {
                                    V134VpnSession.routeTo(context, playlist.id.toString())
                                }
                                routeBusy = false
                                if (ready) vm.selectPlaylist(playlist.id)
                                else routeFailed = true
                            }
                        }""")
replace(playlist, "private fun V070PlaylistCard(name: String, type: String, status: V112PlaylistStatus, active: Boolean",
    "private fun V070PlaylistCard(name: String, type: String, status: V112PlaylistStatus, active: Boolean, vpnEnabled: Boolean, onVpnToggle: () -> Unit")
# A focusable, clickable ROW captures Fire TV D-pad traversal in the original
# playlist screen, leaving both VPN and LÖSCHEN inaccessible. Make the row only a
# visual container and provide THREE sibling actions: AUSWÄHLEN, VPN and LÖSCHEN.
# The caller-provided FocusRequester + remembered menu index must belong to the
# AUSWÄHLEN action, not the row, so resume and remote Up/Down also still work.
replace(playlist, "    Row(\n        modifier.fillMaxWidth().heightIn(min = 104.dp)",
    "    Row(\n        Modifier.fillMaxWidth().heightIn(min = 104.dp)")
replace(playlist, ".onFocusChanged { focused = it.isFocused }",
    ".onFocusChanged { focused = it.hasFocus }")
replace(playlist,
    ".v114FocusRing().clickable(onClick = onSelect).padding(horizontal = 20.dp, vertical = 15.dp),",
    ".padding(horizontal = 20.dp, vertical = 15.dp),")
replace(playlist,
    """        Surface(shape = RoundedCornerShape(99.dp), color = if (active) accent else if (focused) Color.White else Color.White.copy(.10f)) {
            Text(if (active) "AKTIV" else if (focused) "OK · AUSWÄHLEN" else "AUSWÄHLEN", color = if (active || focused) Color.Black else Color.White.copy(.82f), fontSize = 12.sp, fontWeight = FontWeight.Black, modifier = Modifier.padding(horizontal = 16.dp, vertical = 9.dp))
        }
        Spacer(Modifier.width(10.dp))
        TextButton(onClick = onDelete,""",
    """        TextButton(
            onClick = onSelect,
            modifier = modifier.v070TvFocus(accent).v114FocusRing(),
            colors = ButtonDefaults.textButtonColors(
                containerColor = if (active) accent else Color.White.copy(.14f)
            )
        ) {
            Text(if (active) "AKTIV · AUSWÄHLEN" else "AUSWÄHLEN",
                color = if (active) Color.Black else Color.White, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.width(10.dp))
        TextButton(onClick = onVpnToggle,
            modifier = Modifier.v070TvFocus(accent).v114FocusRing(),
            colors = ButtonDefaults.textButtonColors(
                containerColor = if (vpnEnabled) accent.copy(.26f) else Color.White.copy(.12f)
            )
        ) {
            Text(if (vpnEnabled) "VPN · FINNLAND" else "DIREKT",
                color = Color.White, fontWeight = FontWeight.Bold)
        }
        Spacer(Modifier.width(10.dp))
        TextButton(onClick = onDelete,""")
# Flag that the expected three sibling controls really exist in reconstructed source.
# The separate beta build script checks this before signing.


app=java/"EpiMediaHubApp.kt"
replace(app, "    MaterialTheme(colorScheme = scheme, shapes = shapes) {",
    """    val v134Ready = de.epimediahub.app.vpn.v134RouteReady(context, u.active?.id?.toString())
    MaterialTheme(colorScheme = scheme, shapes = shapes) {""")
replace(app, "        } else if (kidsSessionActive) {",
    """        } else if (u.active != null && u.screen != Screen.Playlists && !v134Ready) {
            de.epimediahub.app.vpn.V134VpnRouteBlockedScreen(context, u.active?.name ?: "Playlist") {
                vm.navigate(Screen.Playlists)
            }
        } else if (kidsSessionActive) {""")
print("V134 beta routing UI installed: per-playlist toggle and guarded playlist selection")
