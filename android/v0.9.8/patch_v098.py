#!/usr/bin/env python3
"""Android 0.9.8: premium/private skins, original crest support and receiver-style Live TV."""
import os, re, shutil
from pathlib import Path

root = Path(os.environ["PROJECT_ROOT"])
java = root / "app/src/main/java/de/epimediahub/app"

def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor in {path}, found {count}")
    path.write_text(text.replace(old, new, 1))

gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 907', 'versionCode = 908', 'versionCode')
replace_once(gradle, 'versionName = "0.9.7"', 'versionName = "0.9.8"', 'versionName')

for relative in ("ui/Screens.kt", "ui/V078DashboardPairingGate.kt", "ui/V083Home.kt", "data/V070WeatherClient.kt"):
    p = java / relative
    if p.exists():
        p.write_text(p.read_text().replace("0.9.7", "0.9.8"))

# Replace the procedural 0.9.7 environment implementation with the richer 0.9.8 one.
shutil.copyfile(Path(__file__).with_name("V098SkinEnvironment.kt"), java / "ui/V097SkinEnvironment.kt")

# ---------------------------------------------------------------------------
# Theme metadata: newly added national teams can carry a remote original crest.
# Imported Enigma skins continue to use their packaged original resources.
# ---------------------------------------------------------------------------
models = java / "model/Models.kt"
ms = models.read_text()
old_theme = 'data class ThemeInfo(val id: String, val label: String, val group: String, val accent: String, val family: Boolean = false)'
if old_theme not in ms:
    raise SystemExit("ThemeInfo v0.9.7 anchor missing")
models.write_text(ms.replace(
    old_theme,
    'data class ThemeInfo(val id: String, val label: String, val group: String, val accent: String, val family: Boolean = false, val logoUrl: String = "")',
    1,
))

repo = java / "data/ThemeRepository.kt"
rs = repo.read_text()
old_map = 'themes[id] = ThemeInfo(id, t.optString("label", id), t.optString("group"), t.optString("accent", "#28A7F2"), t.optBoolean("family", false))'
if old_map not in rs:
    raise SystemExit("ThemeRepository ThemeInfo mapping anchor missing")
rs = rs.replace(
    old_map,
    'themes[id] = ThemeInfo(id, t.optString("label", id), t.optString("group"), t.optString("accent", "#28A7F2"), t.optBoolean("family", false), t.optString("logo_url", ""))',
    1,
)

old_helpers = '''    private fun isStandard(id: String) = id == "default" || id == "epi_blue" || id == "epi_red"

    fun markRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("mark_${safe(id)}")
    fun homeMotifRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("home_motif_${safe(id)}")
    fun centerMarkRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("center_mark_${safe(id)}")
    fun bannerMarkRes(id: String) = if (isStandard(id)) R.drawable.brand_header else drawable("banner_mark_${safe(id)}")'''
if old_helpers not in rs:
    raise SystemExit("ThemeRepository resource helper anchor missing")

new_helpers = '''    private fun isStandard(id: String) = id == "default" || id == "epi_blue" || id == "epi_red"

    private fun logoCandidates(id: String): List<String> {
        val direct = safe(id)
        val aliases = when (id) {
            "f1_ferrari" -> listOf("ferrari")
            "f1_mercedes" -> listOf("mercedes", "mercedes_benz")
            "f1_red_bull" -> listOf("red_bull", "redbull")
            "f1_mclaren" -> listOf("mclaren")
            "f1_aston_martin" -> listOf("aston_martin")
            "f1_alpine" -> listOf("alpine")
            "f1_haas" -> listOf("haas")
            "f1_racing_bulls" -> listOf("racing_bulls", "rb")
            "f1_williams" -> listOf("williams")
            "f1_audi" -> listOf("audi")
            "f1_cadillac" -> listOf("cadillac")
            else -> emptyList()
        }
        return (listOf(direct) + aliases).distinct()
    }

    private fun themedDrawable(prefix: String, id: String): Int {
        for (candidate in logoCandidates(id)) {
            val value = drawable("${prefix}_${safe(candidate)}")
            if (value != 0) return value
        }
        return 0
    }

    fun markRes(id: String) = if (isStandard(id)) R.drawable.brand_header else themedDrawable("mark", id)
    fun homeMotifRes(id: String) = if (isStandard(id)) R.drawable.brand_header else themedDrawable("home_motif", id)
    fun centerMarkRes(id: String) = if (isStandard(id)) R.drawable.brand_header else themedDrawable("center_mark", id)
    fun bannerMarkRes(id: String) = if (isStandard(id)) R.drawable.brand_header else themedDrawable("banner_mark", id)'''
repo.write_text(rs.replace(old_helpers, new_helpers, 1))

# ---------------------------------------------------------------------------
# Global backdrop: richer environments, luxury brand colors and original
# remote crest fallback when a new national theme has no packaged drawable.
# ---------------------------------------------------------------------------
common = java / "ui/Common.kt"
cs = common.read_text()
if 'import coil.compose.AsyncImage' not in cs:
    import_anchor = 'import de.epimediahub.app.model.ThemeInfo\n'
    if import_anchor not in cs:
        raise SystemExit("Common ThemeInfo import anchor missing")
    cs = cs.replace(import_anchor, import_anchor + 'import coil.compose.AsyncImage\n', 1)

skin_anchor = '''        val skinWorld = remember(themeId, theme?.label, theme?.group) {
            V097SkinWorldFor(themeId, theme?.label.orEmpty(), theme?.group.orEmpty())
        }
'''
if skin_anchor not in cs:
    raise SystemExit("Common skinWorld anchor missing")
cs = cs.replace(
    skin_anchor,
    skin_anchor + '''        val environmentAccent = remember(themeId, theme?.label, accent) {
            V098EnvironmentAccent(themeId, theme?.label.orEmpty(), accent)
        }
''',
    1,
)
cs = cs.replace('            V097SkinEnvironment(skinWorld, accent)\n', '            V097SkinEnvironment(skinWorld, environmentAccent)\n', 1)

# Let cinematic environments show instead of being buried under the old veil.
cs = cs.replace('Color(0x7604080D),\n                            Color(0x9E080D14),\n                            Color(0xC805080D)',
                'Color(0x4A04080D),\n                            Color(0x72080D14),\n                            Color(0xA605080D)', 1)

old_mark = '''            if (watermark != 0) {
                Image(
                    painter = painterResource(watermark),
                    contentDescription = null,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 8.dp, vertical = 8.dp)
                        .graphicsLayer { alpha = .34f },
                    contentScale = ContentScale.Fit
                )
            } else if (skinWorld != V097SkinWorld.NEUTRAL) {
                V097FallbackSkinMark(
                    themeId = themeId,
                    label = theme?.label.orEmpty(),
                    accent = accent
                )
            }
'''
if old_mark not in cs:
    raise SystemExit("Common watermark render anchor missing")
new_mark = '''            if (watermark != 0) {
                Image(
                    painter = painterResource(watermark),
                    contentDescription = null,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 8.dp, vertical = 8.dp)
                        .graphicsLayer { alpha = .38f },
                    contentScale = ContentScale.Fit
                )
            } else if (!theme?.logoUrl.isNullOrBlank()) {
                AsyncImage(
                    model = theme?.logoUrl,
                    contentDescription = null,
                    modifier = Modifier
                        .fillMaxSize()
                        .padding(horizontal = 56.dp, vertical = 46.dp)
                        .graphicsLayer { alpha = .42f },
                    contentScale = ContentScale.Fit
                )
            } else if (skinWorld != V097SkinWorld.NEUTRAL) {
                V097FallbackSkinMark(
                    themeId = themeId,
                    label = theme?.label.orEmpty(),
                    accent = environmentAccent
                )
            }
'''
common.write_text(cs.replace(old_mark, new_mark, 1))

# ---------------------------------------------------------------------------
# Theme picker: same premium environment and original crest fallback.
# ---------------------------------------------------------------------------
themes = java / "ui/V079Themes.kt"
ts = themes.read_text()
if 'import coil.compose.AsyncImage' not in ts:
    anchor = 'import de.epimediahub.app.model.ThemeInfo\n'
    if anchor not in ts:
        raise SystemExit("V079 ThemeInfo import anchor missing")
    ts = ts.replace(anchor, anchor + 'import coil.compose.AsyncImage\n', 1)

world_anchor = '    val skinWorld = V097SkinWorldFor(theme.id, theme.label, theme.group)\n'
if world_anchor not in ts:
    raise SystemExit("V079 skinWorld anchor missing")
ts = ts.replace(world_anchor, world_anchor + '    val environmentAccent = V098EnvironmentAccent(theme.id, theme.label, themeAccent)\n', 1)
ts = ts.replace('        V097SkinEnvironment(skinWorld, themeAccent)\n', '        V097SkinEnvironment(skinWorld, environmentAccent)\n', 1)

old_preview_else = '''        } else if (skinWorld != V097SkinWorld.NEUTRAL) {
            V097FallbackSkinMark(
                themeId = theme.id,
                label = theme.label,
                accent = themeAccent,
                compact = true
            )
        }
'''
if old_preview_else not in ts:
    raise SystemExit("V079 preview fallback anchor missing")
new_preview_else = '''        } else if (theme.logoUrl.isNotBlank()) {
            AsyncImage(
                model = theme.logoUrl,
                contentDescription = theme.label,
                modifier = Modifier.align(Alignment.Center)
                    .fillMaxHeight(.86f)
                    .fillMaxWidth(if (isTv) .52f else .58f)
                    .graphicsLayer { alpha = if (focused) .88f else .72f },
                contentScale = ContentScale.Fit
            )
        } else if (skinWorld != V097SkinWorld.NEUTRAL) {
            V097FallbackSkinMark(
                themeId = theme.id,
                label = theme.label,
                accent = environmentAccent,
                compact = true
            )
        }
'''
themes.write_text(ts.replace(old_preview_else, new_preview_else, 1))

# ---------------------------------------------------------------------------
# Live TV: denser receiver layout + active skin integrated into channel banner.
# ---------------------------------------------------------------------------
live = java / "ui/V076LiveTv.kt"
ls = live.read_text()
if 'import androidx.compose.foundation.Image' not in ls:
    ls = ls.replace('import androidx.compose.foundation.BorderStroke\n', 'import androidx.compose.foundation.BorderStroke\nimport androidx.compose.foundation.Image\n', 1)
if 'import androidx.compose.ui.graphics.graphicsLayer' not in ls:
    ls = ls.replace('import androidx.compose.ui.graphics.Color\n', 'import androidx.compose.ui.graphics.Color\nimport androidx.compose.ui.graphics.graphicsLayer\n', 1)
if 'import androidx.compose.ui.res.painterResource' not in ls:
    ls = ls.replace('import androidx.compose.ui.layout.ContentScale\n', 'import androidx.compose.ui.layout.ContentScale\nimport androidx.compose.ui.res.painterResource\n', 1)

# Receiver proportions on TV.
ls = ls.replace('Modifier.fillMaxSize().padding(horizontal = if (isTv) 14.dp else 8.dp, vertical = 8.dp)',
                'Modifier.fillMaxSize().padding(horizontal = if (isTv) 10.dp else 8.dp, vertical = 6.dp)', 1)
ls = ls.replace('horizontalArrangement = Arrangement.spacedBy(if (isTv) 10.dp else 7.dp)',
                'horizontalArrangement = Arrangement.spacedBy(if (isTv) 7.dp else 7.dp)', 1)
ls = ls.replace('Modifier.width(if (isTv) 250.dp else 205.dp).fillMaxHeight()',
                'Modifier.width(if (isTv) 220.dp else 205.dp).fillMaxHeight()', 1)
ls = ls.replace('Modifier.width(if (isTv) 350.dp else 285.dp).fillMaxHeight()',
                'Modifier.width(if (isTv) 318.dp else 285.dp).fillMaxHeight()', 1)

# Transparent receiver panes reveal the active skin environment.
ls = ls.replace('color = Color(0xE80A1019),', 'color = Color(0xC20A1019),')
ls = ls.replace('verticalArrangement = Arrangement.spacedBy(3.dp),', 'verticalArrangement = Arrangement.spacedBy(2.dp),')
ls = ls.replace('.padding(horizontal = 10.dp, vertical = 10.dp)', '.padding(horizontal = 9.dp, vertical = 7.dp)', 1)

# Compact channel rows.
ls = ls.replace('val epgHeight = if (isTv) 55.dp else 58.dp', 'val epgHeight = if (isTv) 43.dp else 52.dp', 1)
ls = ls.replace('Modifier.fillMaxWidth().height(epgHeight).padding(horizontal = 8.dp, vertical = 5.dp)',
                'Modifier.fillMaxWidth().height(epgHeight).padding(horizontal = 7.dp, vertical = 3.dp)', 1)
ls = ls.replace('modifier = Modifier.width(32.dp),', 'modifier = Modifier.width(if (isTv) 27.dp else 30.dp),', 1)
ls = ls.replace('modifier = Modifier.width(if (isTv) 52.dp else 58.dp).fillMaxHeight()',
                'modifier = Modifier.width(if (isTv) 40.dp else 52.dp).fillMaxHeight()', 1)
ls = ls.replace('modifier = Modifier.fillMaxSize().padding(4.dp),',
                'modifier = Modifier.fillMaxSize().padding(3.dp),', 1)
ls = ls.replace('Spacer(Modifier.width(9.dp))', 'Spacer(Modifier.width(if (isTv) 7.dp else 9.dp))', 1)
ls = ls.replace('fontSize = if (isTv) 15.sp else 14.sp,', 'fontSize = if (isTv) 13.sp else 14.sp,', 1)
ls = ls.replace('Text("LIVE", color = Color.White, fontSize = 9.sp, fontWeight = FontWeight.Black)',
                'Text("LIVE", color = Color.White, fontSize = 8.sp, fontWeight = FontWeight.Black)', 1)

# Active skin in the sender banner.
info_anchor = '''    val u by vm.ui.collectAsState()
    val epg = channel?.let { u.epg[it.id].orEmpty() }.orEmpty()
'''
if info_anchor not in ls:
    raise SystemExit("V076 InfoPane state anchor missing")
ls = ls.replace(
    info_anchor,
    '''    val u by vm.ui.collectAsState()
    val activeSkin = u.themeCatalog?.themes?.get(u.themeId)
    val activeSkinMark = remember(u.themeId) {
        vm.themeRepo().bannerMarkRes(u.themeId).takeIf { it != 0 }
            ?: vm.themeRepo().centerMarkRes(u.themeId).takeIf { it != 0 }
            ?: vm.themeRepo().markRes(u.themeId)
    }
    val epg = channel?.let { u.epg[it.id].orEmpty() }.orEmpty()
''',
    1,
)

banner_box_anchor = '''                    Box(Modifier.fillMaxSize()) {
                        if (channel.image.isNotBlank()) {
'''
if banner_box_anchor not in ls:
    raise SystemExit("V076 sender banner box anchor missing")
ls = ls.replace(
    banner_box_anchor,
    '''                    Box(Modifier.fillMaxSize()) {
                        if (activeSkinMark != 0) {
                            Image(
                                painter = painterResource(activeSkinMark),
                                contentDescription = null,
                                modifier = Modifier.align(Alignment.CenterEnd)
                                    .fillMaxHeight(.92f)
                                    .fillMaxWidth(.62f)
                                    .padding(end = 8.dp)
                                    .graphicsLayer { alpha = .14f },
                                contentScale = ContentScale.Fit
                            )
                        } else if (!activeSkin?.logoUrl.isNullOrBlank()) {
                            AsyncImage(
                                model = activeSkin?.logoUrl,
                                contentDescription = null,
                                modifier = Modifier.align(Alignment.CenterEnd)
                                    .fillMaxHeight(.90f)
                                    .fillMaxWidth(.58f)
                                    .padding(end = 10.dp)
                                    .graphicsLayer { alpha = .14f },
                                contentScale = ContentScale.Fit
                            )
                        }
                        if (channel.image.isNotBlank()) {
''',
    1,
)

# Add active skin name to info card without competing with EPG.
name_anchor = '''                Text(
                    channel.name,
                    color = Color.White,
'''
if name_anchor not in ls:
    raise SystemExit("V076 channel name anchor missing")
ls = ls.replace(
    name_anchor,
    '''                if (!activeSkin?.label.isNullOrBlank()) {
                    Text(
                        "SKIN · " + V097PrivateDisplayLabel(activeSkin?.label.orEmpty(), activeSkin?.family == true),
                        color = accent.copy(.76f),
                        fontSize = if (compact) 9.sp else 10.sp,
                        fontWeight = FontWeight.Black,
                        maxLines = 1
                    )
                }
                Text(
                    channel.name,
                    color = Color.White,
''',
    1,
)

live.write_text(ls)

checks = [
    (gradle, 'versionCode = 908'),
    (gradle, 'versionName = "0.9.8"'),
    (models, 'val logoUrl: String = ""'),
    (repo, 'private fun logoCandidates(id: String)'),
    (repo, '"f1_ferrari" -> listOf("ferrari")'),
    (common, 'V098EnvironmentAccent'),
    (common, 'model = theme?.logoUrl'),
    (themes, 'model = theme.logoUrl'),
    (live, 'val epgHeight = if (isTv) 43.dp else 52.dp'),
    (live, 'val activeSkinMark = remember(u.themeId)'),
    (live, '"SKIN · " + V097PrivateDisplayLabel'),
    (java / "ui/V097SkinEnvironment.kt", 'V097SkinWorld.LUXURY'),
    (java / "ui/V097SkinEnvironment.kt", 'V097SkinWorld.STANDARD_BLUE'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"Android 0.9.8 marker missing in {path}: {marker}")

print("Android 0.9.8 premium/private skin and receiver Live TV patch applied")
