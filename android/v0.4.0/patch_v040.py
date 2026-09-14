#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly 1 anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


# MediaEntry keeps Xtream archive capability so catch-up is provider-gated.
models = java / "model/Models.kt"
replace_once(
    models,
    '    val epgId: String = ""\n)',
    '    val epgId: String = "",\n    val tvArchive: Boolean = false,\n    val tvArchiveDurationDays: Int = 0\n)',
    "MediaEntry archive fields"
)

# Preserve Xtream archive flags on live channels.
xtream = java / "data/XtreamClient.kt"
replace_once(
    xtream,
    'epgId=o.optString("epg_channel_id")))',
    'epgId=o.optString("epg_channel_id"),tvArchive=o.optInt("tv_archive",0)==1,tvArchiveDurationDays=o.optInt("tv_archive_duration",0)))',
    "Xtream live archive metadata"
)

# Route new parity screens and safely auto-open QR web setup on Android TV when no playlist exists.
app = java / "EpiMediaHubApp.kt"
text = app.read_text()
anchor = '    val u by vm.ui.collectAsState()\n'
if text.count(anchor) != 1:
    raise SystemExit("EpiMediaHubApp state anchor missing")
text = text.replace(
    anchor,
    anchor + '    androidx.compose.runtime.LaunchedEffect(isTv, u.playlists.size, u.screen) {\n'
             '        if (isTv && u.playlists.isEmpty() && u.screen == Screen.AddPlaylist) {\n'
             '            vm.navigate(Screen.WebAdmin, remember = false)\n'
             '        }\n'
             '    }\n',
    1
)
player = '                is Screen.Player -> PlayerScreen(vm, s.item, s.episodeList, accent, isTv)\n'
if text.count(player) != 1:
    raise SystemExit("EpiMediaHubApp player route anchor missing")
text = text.replace(
    player,
    '                ParityMediathekHome -> ParityMediathekHomeScreen(vm, accent, isTv)\n'
    '                is ParityMediathekDirectory -> ParityMediathekDirectoryScreen(vm, s.countryId, accent, isTv)\n'
    '                is ParityMediathekList -> ParityMediathekListScreen(vm, s.providerId, accent, isTv)\n'
    '                is ParityEpgGrid -> ParityEpgGridScreen(vm, s.category, accent, isTv)\n'
    + player,
    1
)
app.write_text(text)

# Upgrade the current v0.3.6 home delegate, expose EPG grid from every Live category,
# and replace browser setup with QR-assisted setup.
screens = java / "ui/Screens.kt"
s = screens.read_text()
if 'V036HomeScreen(vm,isTv,accent)' not in s:
    raise SystemExit("v0.3.6 home delegate missing")
s = s.replace('V036HomeScreen(vm,isTv,accent)', 'V040HomeScreen(vm,isTv,accent)', 1)

old_top = 'EpiTopBar(sectionTitle(kind),R.drawable.brand_header,{vm.back()},actions={Text(cat.name,color=accent,fontWeight=FontWeight.Bold,maxLines=1)})'
new_top = 'EpiTopBar(sectionTitle(kind),R.drawable.brand_header,{vm.back()},actions={Row(verticalAlignment=Alignment.CenterVertically){if(kind==MediaKind.LIVE)TextButton(onClick={vm.navigate(ParityEpgGrid(cat))}){Text("EPG",color=accent,fontWeight=FontWeight.Black)};Text(cat.name,color=accent,fontWeight=FontWeight.Bold,maxLines=1)}})'
if s.count(old_top) != 1:
    raise SystemExit(f"Items topbar anchor missing: {s.count(old_top)}")
s = s.replace(old_top, new_top, 1)

start = s.find('@Composable\nfun WebAdminScreen')
end = s.find('@Composable\nfun ThemesScreen', start)
if start < 0 or end < 0:
    raise SystemExit("WebAdminScreen markers missing")
web = r'''@Composable
fun WebAdminScreen(vm:MainViewModel,accent:Color){
    val u by vm.ui.collectAsState()
    BackHandler{vm.back()}
    LaunchedEffect(Unit){if(!u.webAdminRunning)vm.startWebAdmin()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar("QR-WEBSETUP",R.drawable.brand_header,{vm.back()})
        Box(Modifier.fillMaxSize().padding(18.dp),contentAlignment=Alignment.TopCenter){
            GlassPanel(Modifier.fillMaxWidth().widthIn(max=900.dp)){
                Column(Modifier.fillMaxWidth().padding(26.dp),horizontalAlignment=Alignment.CenterHorizontally){
                    Icon(Icons.Default.Computer,null,tint=accent,modifier=Modifier.size(46.dp))
                    Text("Playlist bequem im Browser einrichten",fontSize=27.sp,fontWeight=FontWeight.Black,modifier=Modifier.padding(top=10.dp))
                    Text("Handy oder Computer und dieses Gerät müssen im selben lokalen Netzwerk sein. Der Zugriff ist mit einem temporären PIN geschützt.",color=Color.White.copy(.67f),modifier=Modifier.padding(vertical=10.dp))
                    if(u.webAdminRunning){
                        ParityQrCode(u.webAdminUrl,Modifier.padding(vertical=10.dp))
                        Text("QR-CODE SCANNEN ODER ADRESSE ÖFFNEN",color=accent,fontWeight=FontWeight.Bold,fontSize=12.sp)
                        SelectionContainer{Text(u.webAdminUrl,fontSize=20.sp,fontWeight=FontWeight.Bold,modifier=Modifier.padding(top=4.dp))}
                        Spacer(Modifier.height(14.dp))
                        Text("PIN",color=accent,fontWeight=FontWeight.Bold)
                        Text(u.webAdminPin,fontSize=36.sp,fontWeight=FontWeight.Black,letterSpacing=6.sp)
                        Text("Dort kannst du Xtream Codes oder M3U/get.php hinzufügen. Änderungen werden direkt in EpiMediaHub übernommen.",color=Color.White.copy(.66f),modifier=Modifier.padding(top=12.dp))
                        OutlinedButton(onClick={vm.stopWebAdmin()},modifier=Modifier.padding(top=18.dp),shape=MaterialTheme.shapes.medium){Text("Websetup stoppen")}
                    }else{
                        if(u.error.isNotBlank())Text(u.error,color=MaterialTheme.colorScheme.error,modifier=Modifier.padding(vertical=8.dp))
                        Button(onClick={vm.startWebAdmin()},colors=ButtonDefaults.buttonColors(containerColor=accent),shape=MaterialTheme.shapes.medium){Text("QR-Websetup starten")}
                    }
                }
            }
        }
    }
}

'''
s = s[:start] + web + s[end:]
s = s.replace('Android v0.3.6', 'Android v0.4.0')
s = s.replace('Android v0.3.5', 'Android v0.4.0')
s = s.replace('IBO-inspirierter Browser · Kategorien links · Positionsspeicher', 'Enigma-0.9.41-Parität · Mediathek · Voll-EPG · Catch-up · QR-Websetup')
screens.write_text(s)

print("Android v0.4.0 parity patch applied")
