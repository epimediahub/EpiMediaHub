#!/usr/bin/env python3
"""Android 0.9.9: original private marks, shared neutral worlds and category picker."""
import json
import os
import shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"
res = root / "app/src/main/res"
here = Path(__file__).resolve().parent


def replace_once(path: Path, old: str, new: str, label: str):
    value = path.read_text()
    count = value.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(value.replace(old, new, 1))


replace_once(root / "app/build.gradle.kts", "versionCode = 908", "versionCode = 909", "versionCode")
replace_once(root / "app/build.gradle.kts", 'versionName = "0.9.8"', 'versionName = "0.9.9"', "versionName")
for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    path = java / relative
    if path.exists():
        path.write_text(path.read_text().replace("0.9.8", "0.9.9"))

draw = res / "drawable-nodpi"
draw.mkdir(parents=True, exist_ok=True)
for image in (here / "assets").glob("*.png"):
    shutil.copyfile(image, draw / image.name)
for image in (here / "assets").glob("*.webp"):
    shutil.copyfile(image, draw / image.name)
# Resource shrinking cannot infer getIdentifier("official_" + id). Keep every
# original mark in a signed release build as well as in a debug APK.
shutil.copyfile(here / "keep.xml", res / "raw/keep.xml")

shutil.copyfile(here / "V099SkinEnvironment.kt", java / "ui/V097SkinEnvironment.kt")
shutil.copyfile(here / "V099Themes.kt", java / "ui/V079Themes.kt")

repo = java / "data/ThemeRepository.kt"
value = repo.read_text()
start = value.index("    private fun logoCandidates(id: String): List<String> {")
end = value.index("\n}", start)
value = value[:start] + '''    fun officialMarkRes(id: String): Int = drawable("official_${safe(id)}")

    // In private skins an absent original is truly absent. Do not silently
    // substitute an older, invented mark or a different car-brand symbol.
    fun markRes(id: String) = if (isStandard(id)) R.drawable.brand_header else officialMarkRes(id)
    fun homeMotifRes(id: String) = markRes(id)
    fun centerMarkRes(id: String) = markRes(id)
    fun bannerMarkRes(id: String) = markRes(id)''' + value[end:]
repo.write_text(value)

common = java / "ui/Common.kt"
value = common.read_text()
start = value.index("        val bg = remember(themeId) { repo.backgroundRes(themeId) }")
end = value.index("\n        Box(Modifier.fillMaxSize()", start)
value = value[:start] + '''        val watermark = remember(themeId) { repo.officialMarkRes(themeId) }
        val skinWorld = remember(themeId, theme?.group) {
            V097SkinWorldFor(themeId, theme?.label.orEmpty(), theme?.group.orEmpty())
        }
''' + value[end:]
start = value.index("            V097SkinEnvironment(skinWorld, environmentAccent)")
end = value.index("\n            content()", start)
value = value[:start] + '''            V097SkinEnvironment(skinWorld, accent)

            // Same photograph for every skin in the category. Only the
            // transparent, centred original crest and menu accents change.
            if (skinWorld == V097SkinWorld.GARAGE && watermark != 0) {
                // Dark factory marks need neutral showroom light behind them.
                Box(
                    Modifier.align(Alignment.Center)
                        .fillMaxHeight(.64f).fillMaxWidth(.48f)
                        .background(Brush.radialGradient(
                            listOf(Color.White.copy(.42f), Color.White.copy(.12f), Color.Transparent)
                        ))
                )
            }
            if (watermark != 0) {
                Image(
                    painter = painterResource(watermark),
                    contentDescription = null,
                    modifier = Modifier.align(Alignment.Center)
                        .fillMaxHeight(.62f)
                        .fillMaxWidth(.42f)
                        .graphicsLayer { alpha = .96f },
                    contentScale = ContentScale.Fit
                )
            }
''' + value[end:]
common.write_text(value)

home = java / "ui/V083Home.kt"
hs = home.read_text()
hs = hs.replace("Color(0xB2232C37), Color(0xA80C131B)",
                "Color(0xBE151A20), Color(0xAC0B1118)", 1)
hs = hs.replace("Color(0x76141B24), Color(0x68090F16)",
                "Color(0x9710161D), Color(0x8B0B1016)", 1)
hs = hs.replace("Color.White.copy(.09f)", "Color.White.copy(.25f)", 1)
home.write_text(hs)

model = java / "MainViewModel.kt"
replace_once(model,
             '        val privateSelected = state.themeCatalog?.themes?.get(state.themeId)?.family == true\n\n        if (!unlocked && privateSelected) {',
             '        val selected = state.themeCatalog?.themes?.get(state.themeId)\n        val privateSelected = selected?.family == true\n\n        if (selected == null || (!unlocked && privateSelected)) {',
             "migrate removed inspired theme")

catalog_path = res / "raw/theme_catalog.json"
if not catalog_path.exists():
    raise SystemExit(f"Theme catalog not imported: {catalog_path}")
catalog = json.loads(catalog_path.read_text())
available = {p.stem.removeprefix("official_") for p in (here / "assets").glob("official_*.png")}
allowed_groups = {"england", "italy", "spain", "germany", "france", "netherlands",
                  "turkey", "portugal", "scotland", "national_teams", "cars", "formula_1"}
groups = []
included = set()
for group in catalog["groups"]:
    if group["id"] not in allowed_groups:
        continue
    original_ids = [theme_id for theme_id in group["themes"] if theme_id in available]
    if original_ids:
        groups.append({**group, "themes": original_ids})
        included.update(original_ids)
catalog["groups"] = groups
catalog["themes"] = {k: {**v, "family": True} for k, v in catalog["themes"].items() if k in included}
catalog["themes"]["default"] = {
    "label": "EpiMediaHub", "group": "internal", "accent": "#28A7F2", "family": False
}
catalog_path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")

expected_f1 = {"f1_ferrari", "f1_mercedes", "f1_red_bull", "f1_mclaren", "f1_aston_martin",
               "f1_alpine", "f1_haas", "f1_racing_bulls", "f1_williams", "f1_audi", "f1_cadillac"}
if not expected_f1.issubset(included):
    raise SystemExit(f"Missing original Formula 1 marks: {sorted(expected_f1 - included)}")
if len(included) < 70:
    raise SystemExit(f"Only {len(included)} original marks; incomplete asset pack")

print(f"Android 0.9.9: {len(included)} original private skins in {len(groups)} categories")
