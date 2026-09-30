#!/usr/bin/env python3
"""Keep Live TV list state stable while D-pad focus moves between channels."""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent


def replace(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f"{label}: expected one anchor, found {text.count(old)}")
    return text.replace(old, new, 1)


def span(text, signature):
    start = text.index(signature)
    brace = text.index("{", start)
    depth = 0
    for i in range(brace, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return start, i + 1
    raise SystemExit(f"unclosed function: {signature}")


gradle = root / "app/build.gradle.kts"
g = gradle.read_text()
g = replace(g, "versionCode = 1012", "versionCode = 1013", "version code")
g = replace(g, 'versionName = "1.0.12"', 'versionName = "1.0.13"', "version name")
g = replace(g, "    buildFeatures {\n", "    testOptions { unitTests.isIncludeAndroidResources = true }\n\n    buildFeatures {\n", "UI test resources")
g = replace(g, '    testImplementation("junit:junit:4.13.2")\n', '''    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.13")
    testImplementation("androidx.compose.ui:ui-test-junit4")
    testImplementation("androidx.test.ext:junit:1.2.1")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
''', "Compose UI regression tests")
gradle.write_text(g)

with gradle.open("a") as output:
    output.write('''
tasks.withType<org.gradle.api.tasks.testing.Test>().configureEach {
    testLogging {
        events("failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
        showStandardStreams = true
    }
}
''')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt", "ui/V112SmartTubePlayer.kt"):
    path = java / relative
    path.write_text(path.read_text().replace("1.0.12", "1.0.13"))

live = java / "ui/V076LiveTv.kt"
s = live.read_text()
s = replace(s, "import androidx.compose.ui.layout.ContentScale\n", "import androidx.compose.ui.layout.ContentScale\nimport androidx.compose.ui.platform.testTag\n", "test tags")

# Both TV/wide and mobile routes identify the list by its owning playlist.
for name in ("V076WideLiveTv", "V076MobileLiveTv"):
    s = replace(s, f"                {name}(\n                    vm = vm,\n", f"                {name}(\n                    vm = vm,\n                    playlistId = u.active?.id.orEmpty(),\n", name + " playlist")
    s = replace(s, f"private fun {name}(\n    vm: MainViewModel,\n", f"private fun {name}(\n    vm: MainViewModel,\n    playlistId: String,\n", name + " parameter")

channel_call = "        V076ChannelPane(\n            channels = channels,\n"
if s.count(channel_call) != 2:
    raise SystemExit("expected TV and mobile channel pane routes")
s = s.replace(channel_call, """        V076ChannelPane(
            channels = channels,
            memoryKey = V113LiveTvKeys.channels(playlistId, selectedCategory?.id.orEmpty()),
            focusScope = V113LiveTvKeys.focus(playlistId),
""")
s = replace(s, "        V076CategoryPane(\n            categories = categories,\n", """        V076CategoryPane(
            categories = categories,
            memoryKey = V113LiveTvKeys.categories(playlistId),
            focusScope = V113LiveTvKeys.focus(playlistId),
""", "category memory scope")

a, b = span(s, "private fun V076CategoryPane(")
category = s[a:b]
category = category.replace("private fun V076CategoryPane(", "internal fun V076CategoryPane(", 1)
category = replace(category, "    categories: List<MediaCategory>,\n", "    categories: List<MediaCategory>,\n    memoryKey: String,\n    focusScope: String,\n", "category scope parameters")
category = replace(category, 'v111RememberLazyListState("livetv-categories")', 'v111RememberLazyListState(memoryKey)', "category list identity")
category = replace(category, "remember(categories.size) { FocusRequester() }", "remember(memoryKey, categories.size) { FocusRequester() }", "category requester identity")
category = replace(category, "var initialFocusDone by remember {", "var initialFocusDone by remember(memoryKey) {", "category restore identity")
category = replace(category, "LaunchedEffect(categories.size) {", "LaunchedEffect(memoryKey, categories.size) {", "category entry effect")
category = replace(category, "if (categories.isNotEmpty() && !initialFocusDone)", "if (categories.isNotEmpty() && !initialFocusDone && V111MenuMemory.ownsFocus(memoryKey, focusScope))", "do not steal channel focus on Back")
category = replace(category, "{ _, category ->", "{ index, category ->", "category indices")
category = replace(category, "onSelected = { onCategory(category) }", """onSelected = {
                            V111MenuMemory.rememberFocus(memoryKey, index, category.id, focusScope)
                            onCategory(category)
                        }""", "remember focused category")
s = s[:a] + category + s[b:]

a, b = span(s, "private fun V076ChannelPane(")
channels = s[a:b]
channels = channels.replace("private fun V076ChannelPane(", "internal fun V076ChannelPane(", 1)
channels = replace(channels, "    channels: List<MediaEntry>,\n", "    channels: List<MediaEntry>,\n    memoryKey: String,\n    focusScope: String,\n", "channel scope parameters")
channels = replace(channels, '    val state = v111RememberLazyListState("livetv-channels:" + selectedId)\n', '''    val state = v111RememberLazyListState(memoryKey)
    var initialPositionRestored by remember(memoryKey) { mutableStateOf(false) }
    LaunchedEffect(memoryKey, channels.size) {
        if (channels.isNotEmpty() && !initialPositionRestored) {
            val position = V111MenuMemory.scroll(memoryKey)
            val selectedIndex = channels.indexOfFirst { it.id == selectedId }.coerceAtLeast(0)
            if (position.first == 0 && position.second == 0 && selectedIndex > 0) {
                state.scrollToItem(selectedIndex)
            }
            initialPositionRestored = true
        }
    }
''', "stable channel state and one-time restore")
channels = replace(channels, "                        isTv = isTv,\n", """                        isTv = isTv,
                        modifier = v111RememberFocus(
                            menuKey = memoryKey,
                            itemId = media.id,
                            index = index,
                            enabled = isTv,
                            scopeKey = focusScope
                        ),
""", "exact channel focus restoration")
s = s[:a] + channels + s[b:]

a, b = span(s, "private fun V076ChannelRow(")
row = s[a:b]
row = replace(row, "    isTv: Boolean,\n", "    isTv: Boolean,\n    modifier: Modifier = Modifier,\n", "channel modifier")
row = replace(row, "modifier = Modifier.fillMaxWidth()", "modifier = modifier.fillMaxWidth().testTag(\"live-channel:\" + media.id)", "channel test tag and focus requester")
row = replace(row, "            .focusable()\n", "", "one focus target per channel")
s = s[:a] + row + s[b:]

a, b = span(s, "private fun V076CategoryRow(")
row = s[a:b]
row = replace(row, "            .focusable()\n", "", "one focus target per category")
s = s[:a] + row + s[b:]
live.write_text(s)

shutil.copyfile(here / "V113LiveTvKeys.kt", java / "ui/V113LiveTvKeys.kt")
tests = root / "app/src/test/java/de/epimediahub/app/ui"
shutil.copyfile(here / "V113LiveTvNavigationTest.kt", tests / "V113LiveTvNavigationTest.kt")

assert 'v111RememberLazyListState("livetv-channels:" + selectedId)' not in s
assert s.count("memoryKey = V113LiveTvKeys.channels(playlistId, selectedCategory?.id.orEmpty())") == 2
assert "V111MenuMemory.ownsFocus(memoryKey, focusScope)" in s
assert "modifier = v111RememberFocus(" in s
print("Android 1.0.13: Live TV uses stable playlist/category state, single row focus targets and restores the last focused channel")
