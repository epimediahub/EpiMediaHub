#!/usr/bin/env python3
"""EpiMediaHub v1.0.49: actual Speedtest in labelled drawer, Radio tile, honest local weather,
and role-aware independent provider/series intro skipping. Applied after VPN v1.0.48.
Fail on unknown source structure; never quietly omit a requested feature.
"""
import os
from pathlib import Path
import shutil

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace(path, old, new, count=1):
    value = path.read_text()
    actual = value.count(old)
    assert actual == count, f"{path}: expected {count} occurrences, found {actual}: {old[:100]!r}"
    path.write_text(value.replace(old, new))

def slice_replace(path, first, last, replacement):
    text = path.read_text()
    assert text.count(first)==1 and text.count(last)==1, (str(path),first,last)
    a=text.index(first)
    b=text.index(last,a)
    assert b>a
    path.write_text(text[:a]+replacement+text[b:])

gradle = root/"app/build.gradle.kts"
replace(gradle, "versionCode = 1048", "versionCode = 1049")
replace(gradle, 'versionName = "1.0.48"', 'versionName = "1.0.49"')

shutil.copyfile(here/"V149QuickMenu.kt", java/"ui/V149QuickMenu.kt")

home = java/"ui/V083Home.kt"
replace(home, "import androidx.compose.ui.focus.focusProperties",
    "import androidx.compose.ui.focus.focusProperties\nimport androidx.compose.ui.input.key.Key\nimport androidx.compose.ui.input.key.KeyEventType\nimport androidx.compose.ui.input.key.key\nimport androidx.compose.ui.input.key.onPreviewKeyEvent\nimport androidx.compose.ui.input.key.type\nimport androidx.compose.ui.zIndex")
replace(home, "    val v140RadioFocus = remember { FocusRequester() }",
    """    val v140RadioFocus = remember { FocusRequester() }
    val v149TileFocus = remember { List(6) { FocusRequester() } }
    var v149QuickOpen by remember { mutableStateOf(false) }
    var v149QuickOrigin by remember { mutableIntStateOf(0) }""")
replace(home,
'''        V083Tile("EINSTELLUNGEN", "Design · Sprache · Audio · Update", R.drawable.icon_settings) {
            vm.navigate(Screen.Settings)
        }''',
'''        V083Tile("RADIO", "Sender weltweit · Favoriten · Suche", R.drawable.icon_radio_v149) {
            radioOpen = true
        }''')
# The code above may have replaced the inner expression first; make the loop
# unconditionally from either spelling to avoid one-shot refresh.
for old in (
    '    LaunchedEffect(Unit) {\n        weather = V070WeatherClient.refresh(context)\n    }',
    '    LaunchedEffect(Unit) {\n        weather = V070WeatherClient.refresh(context) ?: weather\n    }',
):
    if old in home.read_text():
        replace(home, old,
'''    LaunchedEffect(Unit) {
        while (true) {
            weather = V070WeatherClient.refresh(context)
            delay(15 * 60 * 1000L)
        }
    }''')
        break
else:
    raise AssertionError("Original weather refresh effect missing")

replace(home,
'''                                    modifier = Modifier.weight(1f).fillMaxHeight()
                                        .focusProperties {
                                            if (isTv && tile.title == "FILME") up = v140RadioFocus
                                        },''',
'''                                    modifier = Modifier.weight(1f).fillMaxHeight()
                                        .focusRequester(v149TileFocus[index])
                                        .onPreviewKeyEvent { e ->
                                            if (isTv && index < columns &&
                                                e.type == KeyEventType.KeyDown && e.key == Key.DirectionUp) {
                                                v149QuickOrigin = index
                                                v149QuickOpen = true
                                                true
                                            } else false
                                        },''')
# Remove tiny permanent round buttons from portraits and clock. Their actual
# actions continue through the quick drawer and RADIO tile.
replace(home,
'''                    RadioHomeActions(showPlaylistSwitch, isTv, accent, onPlaylistSwitch, onRadio, radioModifier = Modifier.focusRequester(radioFocus))
                    de.epimediahub.app.vpn.V140SpeedShortcutButton(accent, isTv, onSpeedtest)''',
'''                    // v1.0.49: uninterrupted center clock, no permanently floating buttons.''')
# Keep existing player, background, expiry, focus and route rules.
# Insert into the BoxWithConstraints immediately before its final closing brace;
# patched builds may have additional composable helpers before V083Header.
home_src = home.read_text()
marker = "\n@Composable\nprivate fun V083Header("
assert home_src.count(marker) == 1
pivot = home_src.index(marker)
segment = home_src[:pivot]
function_close = segment.rfind("\n}")
box_close = segment.rfind("\n    }", 0, function_close)
assert box_close > segment.index("fun V083HomeScreen("), "Home Box closing brace missing"
drawer = """
        Box(Modifier.align(Alignment.TopCenter).zIndex(10f)) {
            V149QuickMenu(
                open = v149QuickOpen,
                isTv = isTv,
                accent = accent,
                onToggle = { v149QuickOpen = !v149QuickOpen },
                onDismiss = { v149QuickOpen = false },
                onSettings = { v149QuickOpen = false; vm.navigate(Screen.Settings) },
                onServers = { v149QuickOpen = false; vm.navigate(Screen.Playlists) },
                onSpeedtest = { v149QuickOpen = false; v140SpeedOpen = true },
                onWeather = { v149QuickOpen = false; vm.navigate(Screen.Settings) }
            )
        }
"""
home_src = home_src[:box_close] + "\n" + drawer + home_src[box_close:]
pivot = home_src.index(marker)
function_close = home_src.rfind("\n}", 0, pivot)
home_src = home_src[:function_close] + """
    LaunchedEffect(v149QuickOpen) {
        if (!v149QuickOpen && v149EverOpened && isTv) {
            delay(85L)
            runCatching { v149TileFocus[v149QuickOrigin].requestFocus() }
        }
    }
""" + home_src[function_close:]
home.write_text(home_src)

# For a closed drawer restore focus via the originating tile, unless the user is
# entering a different screen; this runs only after a drawer was actually opened.
replace(home, '    var v149QuickOrigin by remember { mutableIntStateOf(0) }',
'''    var v149QuickOrigin by remember { mutableIntStateOf(0) }
    var v149EverOpened by remember { mutableStateOf(false) }''')
replace(home,
'''                                                v149QuickOrigin = index
                                                v149QuickOpen = true''',
'''                                                v149QuickOrigin = index
                                                v149EverOpened = true
                                                v149QuickOpen = true''')
replace(home,
'''                weather?.takeIf { !compact || isTv }?.let {''',
'''                weather?.takeIf { !compact || isTv }?.let {''') if False else None
# If no honest, fresh weather exists, show a legible setup/error state instead.
weather_anchor='''                    Spacer(Modifier.height(if (isTv) 2.dp else 0.dp))
                }

                Row('''
replace(home, weather_anchor,
'''                    Spacer(Modifier.height(if (isTv) 2.dp else 0.dp))
                }
                if (weather == null) {
                    Text(
                        if (de.epimediahub.app.data.V070WeatherClient.postalCode(context).isBlank())
                            "Wetterstandort in Einstellungen auswählen"
                        else "Wetter derzeit nicht verfügbar",
                        color = Color.White.copy(.85f),
                        fontSize = if (isTv) 13.sp else 10.sp,
                        maxLines = 1
                    )
                }

                Row(''')

# Replace the two controls' old UI tests with tests matching the requested
# labelled drawer and permanent radio tile. Keep skin portraits' geometry check.
test = tests/"ui/V133HomeControlsUiTest.kt"
slice_replace(test, '    private fun unobstructed(', '    private fun capture(',
'''    private fun unobstructed(id: String, hasSwitch: Boolean = true) {
        val menu = compose.onNodeWithTag("home-quick-toggle").assertIsDisplayed()
            .fetchSemanticsNode().boundsInRoot
        compose.onNodeWithTag("home-center-toolbar").assertIsDisplayed()
        compose.onNodeWithTag("home-quick-panel").assertDoesNotExist()
        for (index in 0..1) {
            val portrait = compose.onNodeWithTag("portrait-$id-$index")
                .assertIsDisplayed().fetchSemanticsNode().boundsInRoot
            assertFalse("Collapsed quick menu must not cover portrait $id / $index",
                overlaps(menu, portrait))
        }
        compose.onNodeWithText("IPTV THE BEST").assertIsDisplayed()
        compose.onNodeWithTag("playlist-expiry")
            .assertIsDisplayed().assertTextEquals("Gültig bis 15.01.2027")
        for (title in listOf("LIVE TV", "FILME", "SERIEN",
                             "MEDIATHEK", "SMARTTUBE", "RADIO"))
            compose.onNodeWithText(title).assertIsDisplayed()
    }

''')
slice_replace(test,
'    @Test fun remoteControlCanMoveBetweenShortcutsAndReturnToTheTiles() {',
'    @Test @Config(qualifiers="de-rDE-w400dp-h800dp-port")',
'''    @Test fun remoteControlOpensDrawerFromTopRowAndShowsLabelledActions() {
        home(true)
        val tile = compose.onNodeWithText("FILME")
        tile.performSemanticsAction(SemanticsActions.RequestFocus) { it() }
        tile.performKeyInput { keyDown(Key.DirectionUp); keyUp(Key.DirectionUp) }
        settle()
        compose.onNodeWithTag("home-quick-panel").assertIsDisplayed()
        for (label in listOf("Einstellungen", "Server wechseln", "Speedtest", "Wetter & Ort")) {
            compose.onNodeWithText(label).assertIsDisplayed()
        }
        compose.onNodeWithTag("quick-settings").assertIsFocused()
        compose.onNodeWithTag("quick-settings")
            .performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }
        settle()
        compose.onNodeWithTag("quick-servers").assertIsFocused()
        compose.onNodeWithTag("quick-servers")
            .performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }
        settle()
        compose.onNodeWithTag("home-quick-panel").assertDoesNotExist()
    }

''')
replace(test,
'''        compose.onNodeWithTag("home-speedtest").performClick()''',
'''        compose.onNodeWithTag("home-quick-toggle").performClick()
        settle()
        compose.onNodeWithTag("quick-speedtest").performClick()''')
replace(test,
'''        compose.onNodeWithTag("home-speedtest").assertIsDisplayed()''',
'''        compose.onNodeWithTag("home-quick-toggle").assertIsDisplayed()''')
# Existing v140 radio focus test no longer fits the icon-free center clock.
replace(test,
'''        val radio = compose.onNodeWithTag("home-radio")
        radio.performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }''',
'''        val radio = compose.onNodeWithTag("home-quick-toggle")
        radio.performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }''') if False else None
# Match installed v140 test extension without retaining the old radio focus assertions.
start='''        settle(); radio.assertIsFocused()
        radio.performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }'''
if start in test.read_text():
    # This is part of removed remoteControl... block, which is already replaced.
    raise AssertionError("Legacy radio focus test unexpectedly survived")

# New radio tile vector works on all existing skins.
drawable = root/"app/src/main/res/drawable/icon_radio_v149.xml"
drawable.parent.mkdir(parents=True,exist_ok=True)
drawable.write_text('''<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="24dp" android:height="24dp"
    android:viewportWidth="24" android:viewportHeight="24">
    <path android:fillColor="#FFFFFFFF"
        android:pathData="M4,9 L19,5 L19,18 L4,18 Z M6,11 L6,16 L17,16 L17,7 Z M7,12 L9,12 L9,14 L7,14 Z M11,12 L16,12 L16,14 L11,14 Z M6,19 L18,19 L18,21 L6,21 Z"/>
</vector>''')

model = java/"data/V115SkipRepository.kt"
replace(model,
'''    val durationMatched: Boolean = false, val confidence: Double = 0.0
) {
    fun active(positionMs: Long): Boolean''',
'''    val durationMatched: Boolean = false, val confidence: Double = 0.0,
    val introRole: String = "unknown"
) {
    val skipLabel: String
        get() = if (kind == V115SegmentKind.INTRO && introRole == "provider")
            "Vorspann überspringen" else kind.label
    fun active(positionMs: Long): Boolean''')
repository = java/"data/V116SkipRepository.kt"
replace(repository,
'''else V115Segment(kind, row.optLong("start_ms", -1), row.optLong("end_ms", -1), "EpiMediaHub · geprüft", true, 1.0)''',
'''else V115Segment(kind, row.optLong("start_ms", -1), row.optLong("end_ms", -1),
                "EpiMediaHub · geprüft", true, 1.0,
                row.optString("intro_role", "unknown"))''')
replace(repository,
'''        return (V115SkipPolicy.select(automatic.filter { it.kind !in disabled }, duration).filter { it.kind !in own } + own.values.filterNotNull()).sortedBy { it.startMs }''',
'''        val selected = V115SkipPolicy.select(automatic.filter { it.kind !in disabled }, duration)
        val overrides = own.values.filterNotNull()
        return (selected.filter { automaticSegment ->
            // "No intro" is a deliberate user decision. It suppresses every
            // intro section, while a timed manual correction replaces only
            // the overlapping section (not a different provider/series intro).
            !(automaticSegment.kind in own && own[automaticSegment.kind] == null) &&
            overrides.none { manual ->
                automaticSegment.kind == manual.kind &&
                    automaticSegment.startMs < manual.endMs &&
                    automaticSegment.endMs > manual.startMs
            }
        } + overrides).sortedBy { it.startMs }''')
chrome = java/"ui/V115PlayerChrome.kt"
replace(chrome, "Text(segment.kind.label, fontSize = if (isTv) 19.sp else 16.sp, fontWeight = FontWeight.Bold)",
        "Text(segment.skipLabel, fontSize = if (isTv) 19.sp else 16.sp, fontWeight = FontWeight.Bold)")

# Weather must never show last week's cached values as live weather or
# use VPN exit-country IP geolocation while claiming it is the local town.
weather = java/"data/V070WeatherClient.kt"
replace(weather,
'''        val json = prefs.getString("payload", null) ?: return null''',
'''        // Fire TV usually lacks location hardware; an exit VPN IP is not the TV's location.
        if (postalCode(context).isBlank()) return null
        val age = System.currentTimeMillis() - prefs.getLong("time", 0L)
        if (age !in 0 until CACHE_MAX_AGE) return null
        val json = prefs.getString("payload", null) ?: return null''')
replace(weather,
'''        val lang = menuLanguage(context)
        val key = locationKey(context)
        val age = System.currentTimeMillis() - prefs.getLong("time", 0L)''',
'''        val lang = menuLanguage(context)
        val key = locationKey(context)
        if (postalCode(context).isBlank()) return@withContext null
        val age = System.currentTimeMillis() - prefs.getLong("time", 0L)''')
replace(weather,
'''                useCaches = true''',
'''                useCaches = false''')
# Keep the inherited User-Agent (updated by other releases); disable HTTP caches.
weather_source = weather.read_text()
import re
weather_source, n = re.subn(
    r'(\s*setRequestProperty\("User-Agent",\s*"[^"]+"\))',
    r'\1\n                setRequestProperty("Cache-Control", "no-cache")',
    weather_source, count=1)
assert n == 1, "weather request user-agent not found"
weather.write_text(weather_source)
settings = java/"ui/V081WeatherSettings.kt"
replace(settings, '"Automatische Standorterkennung"', '"Standort einrichten · bei VPN bitte PLZ angeben"')
replace(settings,
    '''Text("Gib deine Postleitzahl ein. Damit verwendet EpiMediaHub einen festen Standort statt einer ungenauen automatischen Erkennung.")''',
    '''Text("Gib deine Postleitzahl ein, damit das tatsächliche Wetter deiner Stadt angezeigt wird. Besonders bei VPN ist eine automatische Standortbestimmung anhand der Internetadresse falsch.")''')
replace(settings, '''{ Text("Automatisch") }''', '''{ Text("Standort löschen") }''')

# Adjust old per-kind override test because a corrected Netflix pre-roll must
# leave a separate later series-intro visible.
policyTest=tests/"data/V116SkipPolicyTest.kt"
replace(policyTest,
'''        assertEquals(1, merged.size); assertEquals(30_000L, merged.single().startMs); assertEquals(90_000L, merged.single().endMs)''',
'''        assertEquals(2, merged.size)
        assertEquals(listOf(30_000L, 150_000L), merged.map { it.startMs })
        assertEquals(90_000L, merged.first().endMs)''')

# Historical skin-geometry tests should continue testing ALL SIX tiles.
# The sixth tile is RADIO instead of EINSTELLUNGEN by explicit design; the
# settings entry continues through the labelled quick menu and its own tests.
for legacy in ("ui/V131SkinUiTest.kt", "ui/V132SkinUiTest.kt"):
    legacy_test = tests/legacy
    previous = legacy_test.read_text()
    expected = 2 if "V131SkinUiTest" in legacy else 1
    assert previous.count('"SMARTTUBE", "EINSTELLUNGEN"') == expected, (
        legacy, "unexpected skin UI test structure")
    legacy_test.write_text(previous.replace(
        '"SMARTTUBE", "EINSTELLUNGEN"',
        '"SMARTTUBE", "RADIO"'))

# Dedicated deterministic regression cases for independently-labelled intros.
extra = tests/"data/V149IntroRoleTest.kt"
extra.write_text('''package de.epimediahub.app.data

import android.content.Context
import de.epimediahub.app.model.MediaEntry
import de.epimediahub.app.model.MediaKind
import org.junit.Assert.*
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class V149IntroRoleTest {
    @Test fun twoRealIntroSectionsRemainDistinctWithSeparateLabels() {
        val ctx: Context = RuntimeEnvironment.getApplication()
        ctx.getSharedPreferences("v116_own_skip", Context.MODE_PRIVATE).edit().clear().commit()
        val item = MediaEntry("111", "Bridgerton", MediaKind.EPISODE, "Bridgerton",
            streamUrl = "https://provider.example/series/user/pass/111.mkv",
            seriesId = "202", season = 1, episode = 8)
        val provider = V115Segment(V115SegmentKind.INTRO, 0L, 19_000L,
            "EpiMediaHub · geprüft", true, 1.0, "provider")
        val series = V115Segment(V115SegmentKind.INTRO, 218_000L, 225_000L,
            "EpiMediaHub · geprüft", true, 1.0, "series")
        val selected = V116SkipRepository(ctx).merge(item, 2_500_000L, listOf(provider,series))
        assertEquals(2, selected.size)
        assertEquals(listOf("Vorspann überspringen","Intro überspringen"),
            selected.map { it.skipLabel })
        assertEquals(listOf(0L,218_000L),selected.map { it.startMs })
    }
}
''')

print("v1.0.49 patch integrated: Radio tile, clock, focusable labelled drawer, honest refreshed weather, two separate intro roles, real speedtest.")
