#!/usr/bin/env python3
from pathlib import Path
import os

root=Path(os.environ.get("PROJECT_ROOT","."))
java=root/"app/src/main/java/de/epimediahub/app"

# Theme selection: validate, persist and force a clean state update.
vm=java/"MainViewModel.kt"
s=vm.read_text()
old='''    fun selectTheme(id: String) {\n        prefs.themeId = id\n        set { it.copy(themeId = id) }\n    }'''
new='''    fun selectTheme(id: String) {\n        if (_ui.value.themeCatalog?.themes?.containsKey(id) != true) return\n        prefs.themeId = id\n        set { it.copy(themeId = id, error = "") }\n    }'''
if old not in s:
    raise SystemExit("selectTheme anchor missing")
s=s.replace(old,new,1)
vm.write_text(s)

# Browser hierarchy: category screen must be part of the Android back stack.
screens=java/"ui/Screens.kt"
s=screens.read_text()
old='items(u.categories,key={it.id}){c->V043CategoryRow(c.name,accent){vm.switchLibraryCategory(kind,c)}}'
new='items(u.categories,key={it.id}){c->V043CategoryRow(c.name,accent){vm.navigate(Screen.Items(kind,c))}}'
if old not in s:
    raise SystemExit("v0.4.3 category navigation anchor missing")
s=s.replace(old,new,1)
# The explicit mobile Categories button should pop back to the stored category screen,
# not replace the current screen while leaving a duplicate category entry in history.
s=s.replace(
    'OutlinedButton(onClick={vm.navigate(Screen.Categories(kind),remember=false)},modifier=Modifier.weight(1f)){Text("Kategorien")}',
    'OutlinedButton(onClick={vm.back()},modifier=Modifier.weight(1f)){Text("Kategorien")}',
    1
)
# More transparent browser surfaces so the selected skin remains visible.
s=s.replace('Color(0xF20A0F17)','Color(0xB20A0F17)')
s=s.replace('Color(0xF50A111A)','Color(0xC20A111A)')
s=s.replace('Android v0.4.3','Android v0.4.4')
# Use the stronger skin-forward home.
if 'V043HomeScreen(vm,isTv,accent)' not in s:
    raise SystemExit("v0.4.3 home delegate missing")
s=s.replace('V043HomeScreen(vm,isTv,accent)','V044HomeScreen(vm,isTv,accent)',1)
screens.write_text(s)

# Route the designs screen to a live-preview selector.
app=java/"EpiMediaHubApp.kt"
s=app.read_text()
old='Screen.Themes -> ThemesScreen(vm, accent, isTv)'
if old not in s:
    raise SystemExit("Themes route missing")
s=s.replace(old,'Screen.Themes -> V044ThemesScreen(vm, accent, isTv)',1)
app.write_text(s)

# Global skin chrome: guarantee recreation on theme ID changes and reveal more artwork.
common=java/"ui/Common.kt"
s=common.read_text()
start=s.find('@Composable\nfun ThemeBackdrop')
end=s.find('@Composable\nfun GlassPanel',start)
if start<0 or end<0:
    raise SystemExit("ThemeBackdrop markers missing")
backdrop=r'''@Composable
fun ThemeBackdrop(repo: ThemeRepository, theme: ThemeInfo?, themeId: String, content: @Composable BoxScope.() -> Unit) {
    key(themeId) {
        val bg = remember(themeId) { repo.backgroundRes(themeId) }
        val center = remember(themeId) { repo.centerMarkRes(themeId).takeIf { it != 0 } ?: repo.markRes(themeId) }
        val banner = remember(themeId) { repo.bannerMarkRes(themeId).takeIf { it != 0 } ?: repo.markRes(themeId) }
        Box(Modifier.fillMaxSize().background(Color(0xFF05080E))) {
            if (bg != 0) Image(painterResource(bg), null, Modifier.fillMaxSize(), contentScale = ContentScale.Crop)
            Box(
                Modifier.fillMaxSize().background(
                    Brush.verticalGradient(
                        listOf(Color.Black.copy(alpha = .06f), Color(0xFF07101D).copy(alpha = .18f), Color.Black.copy(alpha = .38f))
                    )
                )
            )
            if (center != 0) {
                Image(
                    painterResource(center), null,
                    Modifier.align(Alignment.CenterEnd).fillMaxHeight(.82f).fillMaxWidth(.52f).graphicsLayer { alpha = .15f },
                    contentScale = ContentScale.Fit
                )
            }
            if (banner != 0) {
                Image(
                    painterResource(banner), null,
                    Modifier.align(Alignment.TopEnd).fillMaxWidth(.40f).heightIn(max = 190.dp).graphicsLayer { alpha = .11f },
                    contentScale = ContentScale.Fit
                )
            }
            content()
        }
    }
}

'''
s=s[:start]+backdrop+s[end:]
s=s.replace('listOf(Color(0xE815263C), Color(0xDA091522))','listOf(Color(0xC815263C), Color(0xB5091522))')
common.write_text(s)

# Mediathek/provider cards also stop hiding the selected skin.
parity=java/"ui/ParityScreens.kt"
s=parity.read_text().replace('Color(0xE80B1624)','Color(0xAE0B1624)')
parity.write_text(s)

# Details: make the theme watermark easier to see.
details=java/"ui/V043Details.kt"
s=details.read_text().replace('.alpha(.10f)','.alpha(.18f)')
details.write_text(s)

# Versioned network identity only; behavior stays unchanged.
med=java/"data/MediathekClient.kt"
s=med.read_text().replace('EpiMediaHub-Android/0.4.2','EpiMediaHub-Android/0.4.4').replace('EpiMediaHub/0.4.2','EpiMediaHub/0.4.4')
med.write_text(s)

print("Android v0.4.4 theme switching, skin visibility and back-stack patch applied")
