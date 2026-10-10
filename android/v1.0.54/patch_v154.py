#!/usr/bin/env python3
"""v1.0.54: deterministic Fire-TV drawer D-pad focus, including Weather.

Applied strictly after v1.0.53. Direct-route checks and VPN fail-closed mode
stay unchanged. Previous menu animation retained focus nodes across reopen.
"""
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
tests = root / "app/src/test/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, (str(path), text.count(old), old[:80])
    path.write_text(text.replace(old, new, 1))

build = root / "app/build.gradle.kts"
replace(build, "versionCode = 1053", "versionCode = 1054")
replace(build, 'versionName = "1.0.53"', 'versionName = "1.0.54"')

menu = here / "V154QuickMenu.kt"
source = menu.read_text()
for item in ("actionFocus[0]", "actionFocus[1]", "actionFocus[2]",
             "actionFocus[3]", 'testTag("home-quick-panel")', 'if (open) {'):
    assert item in source, item
assert "AnimatedVisibility(open" not in source
shutil.copyfile(menu, java / "ui/V149QuickMenu.kt")

test = tests / "ui/V133HomeControlsUiTest.kt"
replace(test,
'''        compose.onNodeWithTag("quick-servers")
            .performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }
        settle()
        compose.onNodeWithTag("home-quick-panel").assertDoesNotExist()''',
'''        // The last (Weather) action must be reachable on the very first open.
        compose.onNodeWithTag("quick-servers")
            .performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }
        settle()
        compose.onNodeWithTag("quick-speedtest").assertIsFocused()
        compose.onNodeWithTag("quick-speedtest")
            .performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }
        settle()
        compose.onNodeWithTag("quick-weather").assertIsFocused()
        compose.onNodeWithTag("quick-weather")
            .performKeyInput { keyDown(Key.DirectionLeft); keyUp(Key.DirectionLeft) }
        settle()
        compose.onNodeWithTag("quick-speedtest").assertIsFocused()
        compose.onNodeWithTag("quick-speedtest")
            .performKeyInput { keyDown(Key.DirectionDown); keyUp(Key.DirectionDown) }
        settle()
        compose.onNodeWithTag("home-quick-panel").assertDoesNotExist()

        // Closing then reopening must always recover all four D-pad targets.
        compose.onNodeWithTag("home-quick-toggle").performClick()
        settle()
        compose.onNodeWithTag("quick-settings").assertIsFocused()
        for (target in listOf("quick-servers", "quick-speedtest", "quick-weather")) {
            compose.onNodeWithTag(
                when (target) {
                    "quick-servers" -> "quick-settings"
                    "quick-speedtest" -> "quick-servers"
                    else -> "quick-speedtest"
                }
            ).performKeyInput { keyDown(Key.DirectionRight); keyUp(Key.DirectionRight) }
            settle()
            compose.onNodeWithTag(target).assertIsFocused()
        }''')
assert "quick-weather\").assertIsFocused()" in test.read_text()
print("v1.0.54: quick menu focus graph, repeated re-open navigation and Weather action guarded.")
