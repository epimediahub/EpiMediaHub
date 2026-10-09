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
candidate = os.environ.get("EPIMEDIAHUB_OFFICIAL_CANDIDATE") == "1"
expected = 'applicationId = "de.epimediahub.app"' if candidate else 'applicationId = "de.epimediahub.app.vpnbeta"'
assert expected in build, "Unexpected applicationId; refusing release"

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
# VPN is reached from the EXISTING Settings page, never before the home menu.
# Preserve the app's own back stack and render the settings button with TV focus.
replace(app,
    "                Screen.Settings -> SettingsScreen(vm, accent)",
    "                Screen.Settings -> de.epimediahub.app.vpn.V141VpnSettingsHost(context, u.active?.id?.toString(), accent) { SettingsScreen(vm, accent) }")
replace(app, "    MaterialTheme(colorScheme = scheme, shapes = shapes) {",
    """    val v134Ready = de.epimediahub.app.vpn.v134RouteReady(context, u.active?.id?.toString())
    MaterialTheme(colorScheme = scheme, shapes = shapes) {""")
replace(app, "        } else if (kidsSessionActive) {",
    """        } else if (u.active != null && u.screen != Screen.Playlists && !v134Ready) {
            de.epimediahub.app.vpn.V134VpnRouteBlockedScreen(
                context,
                u.active!!.id.toString(),
                u.active?.name ?: "Playlist",
                onPlaylists = { vm.navigate(Screen.Playlists) },
                onDirectApproved = {
                    // The playback surface is removed while VPN egress is unverified.
                    // After explicit direct consent, reprepare the very same channel
                    // so the user does not need to zap away and back manually.
                    val interrupted = u.screen as? Screen.Player
                    if (interrupted != null &&
                        interrupted.item.kind == de.epimediahub.app.model.MediaKind.LIVE) {
                        if (interrupted.episodeList.isNotEmpty()) {
                            vm.switchLiveChannel(interrupted.item, interrupted.episodeList)
                        } else {
                            vm.play(interrupted.item)
                        }
                    }
                }
            )
        } else if (kidsSessionActive) {""")
print("V134 beta routing UI installed: per-playlist toggle and guarded playlist selection")

# v1.0.40: A real, on-demand bandwidth test beside Radio and Playlist wechseln.
# Keep the main menu tiles and all regular production resources untouched.
home = java/"ui/V083Home.kt"
# The home has accumulated many skin/focus changes since the original source.
# Anchor to V083HomeScreen itself instead of assuming a first-focus declaration.
_home = home.read_text()
_screen = _home.index("fun V083HomeScreen(")
_context = _home.find("    val context = LocalContext.current", _screen)
assert _context >= 0 and _context < _home.index("    BoxWithConstraints(", _screen), "Home context anchor missing"
_line_end = _home.index("\n", _context) + 1
_home = _home[:_line_end] + """    var v140SpeedOpen by remember { mutableStateOf(false) }
    if (v140SpeedOpen) {
        de.epimediahub.app.vpn.V140SpeedTestScreen(
            context, u.active?.id?.toString(), isTv, accent,
            onBack = { v140SpeedOpen = false }
        )
        return
    }
""" + _home[_line_end:]
home.write_text(_home)
replace(home,
    "                onRadio = { radioOpen = true },",
    "                onRadio = { radioOpen = true },\n                onSpeedtest = { v140SpeedOpen = true },")
replace(home,
    "    onRadio: () -> Unit,",
    "    onRadio: () -> Unit,\n    onSpeedtest: () -> Unit,")
replace(home,
    """                    RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio)
                }""",
    """                    RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio)
                    de.epimediahub.app.vpn.V140SpeedShortcutButton(accent, isTv, onSpeedtest)
                }""")
print("V140 beta: added real speed test screen and focusable speed button to central home shortcuts")

# Extend the existing geometry tests so the new shortcut also has to keep every
# sports portrait unobstructed on TV and mobile. Do not weaken existing checks.
home_tests = root/"app/src/test/java/de/epimediahub/app/ui/V133HomeControlsUiTest.kt"
replace(home_tests,
    'listOf("home-radio","home-playlist-switch") else listOf("home-radio")',
    'listOf("home-radio","home-playlist-switch","home-speedtest") else listOf("home-radio","home-speedtest")')
_tests = home_tests.read_text()
_end = _tests.rfind("}")
home_tests.write_text(_tests[:_end] + '''
    @Test fun speedShortcutOpensRealTestScreenAndReturnsHome() {
        home(true)
        compose.onNodeWithTag("home-speedtest").performClick()
        settle()
        compose.onNodeWithTag("speedtest-screen").assertIsDisplayed()
        compose.onNodeWithTag("speedtest-start").assertIsDisplayed().assertIsFocused()
        compose.onNodeWithTag("speedtest-back").performClick()
        settle()
        compose.onNodeWithTag("home-speedtest").assertIsDisplayed()
    }
''' + _tests[_end:])

# Adding a third shortcut changes Compose's geometric Up target from FILME.
# Preserve the established Radio <-> FILME route with an explicit focus target;
# keep Left/Right traversal free to reach the new speed shortcut.
replace(home, "import androidx.compose.ui.focus.focusRequester",
    "import androidx.compose.ui.focus.focusRequester\nimport androidx.compose.ui.focus.focusProperties")
replace(home, "    var v140SpeedOpen by remember { mutableStateOf(false) }",
    "    val v140RadioFocus = remember { FocusRequester() }\n    var v140SpeedOpen by remember { mutableStateOf(false) }")
replace(home, "                onSpeedtest = { v140SpeedOpen = true },",
    "                onSpeedtest = { v140SpeedOpen = true },\n                radioFocus = v140RadioFocus,")
replace(home, "    onSpeedtest: () -> Unit,",
    "    onSpeedtest: () -> Unit,\n    radioFocus: FocusRequester,")
replace(home,
    "                                    modifier = Modifier.weight(1f).fillMaxHeight(),",
    """                                    modifier = Modifier.weight(1f).fillMaxHeight()
                                        .focusProperties {
                                            if (isTv && tile.title == "FILME") up = v140RadioFocus
                                        },""")
replace(home,
    "RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio)",
    "RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio, radioModifier = Modifier.focusRequester(radioFocus))")

radio = java/"ui/RadioScreen.kt"
replace(radio,
    "    onPlaylistSwitch: () -> Unit, onRadio: () -> Unit, modifier: Modifier = Modifier) {",
    "    onPlaylistSwitch: () -> Unit, onRadio: () -> Unit, modifier: Modifier = Modifier, radioModifier: Modifier = Modifier) {")
replace(radio,
    'RadioHomeButton("radio", "Radio", isTv, accent, onRadio) {',
    'RadioHomeButton("radio", "Radio", isTv, accent, onRadio, modifier = radioModifier) {')
replace(radio,
    "    onClick: () -> Unit, content: @Composable () -> Unit) {",
    "    onClick: () -> Unit, modifier: Modifier = Modifier, content: @Composable () -> Unit) {")
replace(radio,
    "        modifier = Modifier.size(if (isTv) 44.dp else 40.dp)",
    "        modifier = modifier.size(if (isTv) 44.dp else 40.dp)")

# Exercise the added sibling without removing the existing Radio/tiles checks.
replace(home_tests,
    """        settle(); radio.assertIsFocused()
        radio.performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }""",
    """        settle(); radio.assertIsFocused()
        radio.performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }
        settle(); compose.onNodeWithTag("home-speedtest").assertIsFocused()
        compose.onNodeWithTag("home-speedtest").performKeyInput { keyDown(Key.DirectionLeft); keyUp(Key.DirectionLeft) }
        settle(); radio.assertIsFocused()
        radio.performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }""")
print("V140 beta: preserved Radio/Filme remote navigation and checked speed shortcut traversal")
