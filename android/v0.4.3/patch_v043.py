#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def require_once(text: str, needle: str, label: str):
    count = text.count(needle)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")


# ---------------------------------------------------------------------------
# Navigation: explicit categories -> library -> details -> playback/episodes.
# ---------------------------------------------------------------------------
vm = java / "MainViewModel.kt"
s = vm.read_text()

screen_anchor = '    data class Episodes(val series: MediaEntry) : Screen\n'
require_once(s, screen_anchor, "Screen.Episodes")
s = s.replace(
    screen_anchor,
    screen_anchor + '    data class Details(val item: MediaEntry) : Screen\n',
    1,
)

navigate_anchor = '            is Screen.Episodes -> loadEpisodes(screen.series)\n'
require_once(s, navigate_anchor, "navigate Episodes")
s = s.replace(
    navigate_anchor,
    navigate_anchor + '            is Screen.Details -> ensureDetails(screen.item)\n',
    1,
)

old_open = '''    fun openLibrary(kind: MediaKind) {\n        pendingAutoOpenKind = kind\n        set { it.copy(contentFilterKind = kind) }\n        navigate(Screen.Categories(kind))\n    }'''
new_open = '''    fun openLibrary(kind: MediaKind) {\n        // v0.4.3 intentionally keeps the category screen visible.\n        pendingAutoOpenKind = null\n        set { it.copy(contentFilterKind = kind) }\n        navigate(Screen.Categories(kind))\n    }'''
require_once(s, old_open, "openLibrary auto-skip")
s = s.replace(old_open, new_open, 1)
vm.write_text(s)


# ---------------------------------------------------------------------------
# App router: generic VOD details + Mediathek details.
# ---------------------------------------------------------------------------
app = java / "EpiMediaHubApp.kt"
s = app.read_text()
player = '                is Screen.Player -> PlayerScreen(vm, s.item, s.episodeList, accent, isTv)\n'
require_once(s, player, "player route")
s = s.replace(
    player,
    '                is Screen.Details -> V043MediaDetailScreen(vm, s.item, accent, isTv)\n'
    '                is ParityMediathekDetail -> V043MediathekDetailScreen(vm, s.item, accent, isTv)\n'
    + player,
    1,
)
app.write_text(s)


# ---------------------------------------------------------------------------
# Main IPTV browser: category interstitial stays visible; item click opens detail.
# ---------------------------------------------------------------------------
screens = java / "ui/Screens.kt"
s = screens.read_text()

home_anchor = 'V041HomeScreen(vm,isTv,accent)'
require_once(s, home_anchor, "v0.4.1 home delegate")
s = s.replace(home_anchor, 'V043HomeScreen(vm,isTv,accent)', 1)

# Replace the category row with the slim-left-accent Enigma visual language.
cat_start = s.find('@Composable\nprivate fun CategoryListRow')
cat_end = s.find('@Composable\nfun ItemsScreen', cat_start)
if cat_start < 0 or cat_end < 0:
    raise SystemExit("CategoryListRow markers missing")
category_row = r'''@Composable
private fun CategoryListRow(title:String,accent:Color,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val shape=RoundedCornerShape(14.dp)
    Row(
        Modifier.fillMaxWidth().heightIn(min=64.dp)
            .onFocusChanged{focused=it.isFocused}.focusable()
            .background(if(focused)Color(0xEA101620)else Color(0xC90A111A),shape)
            .border(if(focused)2.dp else 1.dp,if(focused)Color.White.copy(.26f)else Color.White.copy(.10f),shape)
            .clickable(onClick=onClick),
        verticalAlignment=Alignment.CenterVertically
    ){
        Box(Modifier.fillMaxHeight().width(if(focused)7.dp else 3.dp).background(if(focused)accent else accent.copy(.36f)))
        Spacer(Modifier.width(16.dp))
        Text(title,color=Color.White,fontSize=19.sp,fontWeight=FontWeight.Black,modifier=Modifier.weight(1f),maxLines=2)
        Icon(Icons.Default.ChevronRight,null,tint=if(focused)accent else Color.White.copy(.76f),modifier=Modifier.padding(end=16.dp))
    }
}

'''
s = s[:cat_start] + category_row + s[cat_end:]

# Library selections now open a proper detail page instead of immediately playing.
replacements = {
    'if(kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(detail)) else vm.play(detail)': 'vm.navigate(Screen.Details(detail))',
    'if(kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(detail))else vm.play(detail)': 'vm.navigate(Screen.Details(detail))',
    'if(m.kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(d)) else vm.play(d)': 'vm.navigate(Screen.Details(d))',
    'if(m.kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(d))else vm.play(d)': 'vm.navigate(Screen.Details(d))',
}
for old, new in replacements.items():
    s = s.replace(old, new)

s = s.replace(
    'Text(if(media.kind==MediaKind.SERIES)"Öffnen →" else "Abspielen →",',
    'Text("Details →",',
)
s = s.replace('Android v0.4.2', 'Android v0.4.3')
s = s.replace(
    'Enigma-0.9.41-Parität · Mediathek · Voll-EPG · Catch-up · QR-Websetup',
    'Enigma-UI · sichtbare Kategorien · Detailansichten · Mediathek · Voll-EPG · Catch-up'
)
screens.write_text(s)


# ---------------------------------------------------------------------------
# Mediathek selection opens its new detail page.
# ---------------------------------------------------------------------------
parity = java / "ui/ParityScreens.kt"
s = parity.read_text()
old = 'V042MediathekCard(media, accent, isTv) { vm.play(media.media) }'
require_once(s, old, "Mediathek card action")
s = s.replace(old, 'V042MediathekCard(media, accent, isTv) { vm.navigate(ParityMediathekDetail(media)) }', 1)
parity.write_text(s)


# ---------------------------------------------------------------------------
# Shared chrome: reveal more of the Enigma skin and use its header proportions.
# ---------------------------------------------------------------------------
common = java / "ui/Common.kt"
s = common.read_text()
s = s.replace(
    'listOf(Color.Black.copy(alpha = .30f), Color(0xFF07101D).copy(alpha = .58f), Color.Black.copy(alpha = .78f))',
    'listOf(Color.Black.copy(alpha = .14f), Color(0xFF07101D).copy(alpha = .34f), Color.Black.copy(alpha = .60f))',
    1,
)
start = s.find('@Composable\nfun EpiTopBar')
if start < 0:
    raise SystemExit("EpiTopBar marker missing")
new_topbar = r'''@Composable
fun EpiTopBar(title: String, brandRes: Int, onBack: (() -> Unit)? = null, actions: @Composable RowScope.() -> Unit = {}) {
    Box(
        Modifier.fillMaxWidth().height(96.dp)
            .background(Brush.verticalGradient(listOf(Color(0x9C050A10),Color(0x60050A10),Color.Transparent)))
            .padding(horizontal=14.dp,vertical=7.dp)
    ){
        Row(Modifier.fillMaxSize(),verticalAlignment=Alignment.CenterVertically){
            if(onBack!=null){
                TextButton(onClick=onBack,shape=RoundedCornerShape(12.dp),contentPadding=PaddingValues(horizontal=8.dp,vertical=5.dp)){
                    Text("‹ Zurück",color=Color.White,fontWeight=FontWeight.Bold,fontSize=14.sp)
                }
                Spacer(Modifier.width(4.dp))
            }
            Image(
                painterResource(brandRes),null,
                Modifier.width(225.dp).height(78.dp),
                contentScale=ContentScale.Fit
            )
            Spacer(Modifier.weight(1f))
            Column(horizontalAlignment=Alignment.End){
                Text(title,color=Color.White,fontSize=24.sp,fontWeight=FontWeight.Black,maxLines=1)
                Spacer(Modifier.height(3.dp))
                Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)){actions()}
            }
        }
        Box(
            Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(2.dp)
                .background(Brush.horizontalGradient(listOf(Color.Transparent,MaterialTheme.colorScheme.primary.copy(.72f),Color.Transparent)))
        )
    }
}
'''
s = s[:start] + new_topbar + '\n'
common.write_text(s)

print("Android v0.4.3 categories/details/Enigma UI patch applied")
