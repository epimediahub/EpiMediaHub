#!/usr/bin/env python3
"""Seven-day server trial, reseller credit activation and lifetime license gate."""
import os
from pathlib import Path
import shutil

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
here = Path(__file__).resolve().parent

def replace_once(path, old, new):
    text = path.read_text()
    assert text.count(old) == 1, f"{path}: expected one anchor {old!r}, got {text.count(old)}"
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 1019', 'versionCode = 1020')
replace_once(gradle, 'versionName = "1.0.19"', 'versionName = "1.0.20"')

for path in java.rglob("*.kt"):
    text = path.read_text()
    if "1.0.19" in text:
        path.write_text(text.replace("1.0.19", "1.0.20"))

shutil.copyfile(here / "V120LicenseManager.kt", java / "data/V120LicenseManager.kt")
shutil.copyfile(here / "V120LicenseGate.kt", java / "ui/V120LicenseGate.kt")

app = java / "EpiMediaHubApp.kt"
replace_once(
    app,
    """    var dashboardPaired by remember {
        mutableStateOf(SetupCodeProvisioning.sessionToken(context.applicationContext) != null)
    }
    LaunchedEffect(Unit) {""",
    """    var dashboardPaired by remember {
        mutableStateOf(SetupCodeProvisioning.sessionToken(context.applicationContext) != null)
    }
    var v120LicenseRefresh by remember { mutableStateOf(0) }
    val v120LicenseState = de.epimediahub.app.ui.v120RememberLicenseState(
        context.applicationContext,
        v120LicenseRefresh
    )
    LaunchedEffect(Unit) {"""
)
replace_once(
    app,
    """        } else if (showIntro) {""",
    """        } else if (!v120LicenseState.allowsUse) {
            de.epimediahub.app.ui.V120LicenseGate(
                state = v120LicenseState,
                accent = accent,
                isTv = isTv,
                deviceId = de.epimediahub.app.data.V120LicenseManager.deviceId(context.applicationContext),
                onRetry = { v120LicenseRefresh += 1 }
            )
        } else if (showIntro) {"""
)

home = java / "ui/V083Home.kt"
home_text = home.read_text()
home_anchor = """    }
}

@Composable
private fun V083Header("""
assert home_text.count(home_anchor) == 1, "V083Home end anchor missing"
home_text = home_text.replace(
    home_anchor,
    """        de.epimediahub.app.ui.V120TrialBadge(
            state = de.epimediahub.app.data.V120LicenseManager.cached(context),
            accent = accent,
            isTv = isTv,
            modifier = if (isTv) {
                Modifier.align(Alignment.TopCenter).padding(top = 18.dp)
            } else {
                Modifier.align(Alignment.TopEnd).padding(top = 44.dp, end = 10.dp)
            }
        )
    }
}

@Composable
private fun V083Header(""",
    1
)
home.write_text(home_text)

assert 'versionCode = 1020' in gradle.read_text()
assert 'v120RememberLicenseState' in app.read_text()
assert 'V120LicenseGate(' in app.read_text()
assert 'V120TrialBadge(' in home.read_text()
print("Android 1.0.20: seven-day trial, credit activation and lifetime license gate installed")
