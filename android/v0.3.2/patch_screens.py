#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit("usage: patch_screens.py <Screens.kt>")

path = Path(sys.argv[1])
s = path.read_text()

home = r'''@Composable
fun HomeScreen(vm:MainViewModel,isTv:Boolean,accent:Color){
    val u by vm.ui.collectAsState()
    val cols=if(isTv)3 else 2
    Column(Modifier.fillMaxSize()){
        EpiTopBar(
            u.active?.name?:"EpiMediaHub",
            R.drawable.brand_header,
            actions={Text(if(isTv)"ANDROID TV" else "MOBILE",color=accent,fontWeight=FontWeight.Bold)}
        )
        LazyVerticalGrid(
            GridCells.Fixed(cols),
            Modifier.fillMaxSize().padding(18.dp),
            horizontalArrangement=Arrangement.spacedBy(14.dp),
            verticalArrangement=Arrangement.spacedBy(14.dp)
        ){
            item{FocusCard("LIVE-TV","Sender & EPG",R.drawable.icon_live,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.LIVE))})}
            item{FocusCard("FILME","VOD & Resume",R.drawable.icon_movies,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.MOVIE))})}
            item{FocusCard("SERIEN","Staffeln & Episoden",R.drawable.icon_series,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.SERIES))})}
            item{FocusCard("SUCHE","Sender, Filme, Serien",R.drawable.icon_search,accent=accent,onClick={vm.navigate(Screen.Search)})}
            if(u.continueWatching.isNotEmpty()) item{FocusCard("WEITERSCHAUEN","${u.continueWatching.size} Titel",R.drawable.icon_movies,accent=accent,onClick={vm.navigate(Screen.ContinueWatching)})}
            item{FocusCard("FAVORITEN","${u.favorites.size} gespeichert",R.drawable.icon_live,accent=accent,onClick={vm.navigate(Screen.Favorites)})}
            if(u.playlists.size>1) item{FocusCard("PLAYLIST WECHSELN","${u.playlists.size} Profile",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.Playlists)})}
            item{
                FocusCard(
                    "PC-EINRICHTUNG",
                    if(u.webAdminRunning) "Aktiv · ${u.webAdminUrl} · PIN ${u.webAdminPin}" else "Xtream oder M3U bequem am Computer eintragen",
                    R.drawable.icon_playlist,
                    accent=accent,
                    onClick={vm.navigate(Screen.WebAdmin)}
                )
            }
            item{
                FocusCard(
                    "DESIGNS",
                    u.themeCatalog?.themes?.get(u.themeId)?.label ?: "Design auswählen",
                    R.drawable.icon_settings,
                    accent=accent,
                    onClick={vm.navigate(Screen.Themes)}
                )
            }
            item{FocusCard("EINSTELLUNGEN","Playlists, Sprache & weitere Optionen",R.drawable.icon_settings,accent=accent,onClick={vm.navigate(Screen.Settings)})}
        }
    }
}
'''

add_playlist = r'''@Composable
fun AddPlaylistScreen(vm:MainViewModel,accent:Color){
    val u by vm.ui.collectAsState()
    var mode by remember{mutableStateOf("xtream")}
    var name by remember{mutableStateOf("")}
    var url by remember{mutableStateOf("")}
    var portal by remember{mutableStateOf("")}
    var user by remember{mutableStateOf("")}
    var pass by remember{mutableStateOf("")}
    val backAction:(()->Unit)?=if(u.playlists.isNotEmpty())({vm.back()})else null

    BackHandler(enabled=u.playlists.isNotEmpty()){vm.back()}

    Column(Modifier.fillMaxSize()){
        EpiTopBar("PLAYLIST EINRICHTEN",R.drawable.brand_header,onBack=backAction)
        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal=18.dp),
            contentPadding=PaddingValues(bottom=48.dp),
            horizontalAlignment=Alignment.CenterHorizontally,
            verticalArrangement=Arrangement.spacedBy(10.dp)
        ){
            item{
                GlassPanel(Modifier.fillMaxWidth(.94f).widthIn(max=820.dp)){
                    Column(Modifier.padding(24.dp)){
                        Text("Playlist hinzufügen",fontSize=30.sp,fontWeight=FontWeight.Black)
                        Text(
                            "Bei Xtream reichen Portal/Domain, Username und Passwort. Alle benötigten URLs erstellt EpiMediaHub automatisch.",
                            color=Color.White.copy(.68f),
                            modifier=Modifier.padding(top=6.dp)
                        )
                        Spacer(Modifier.height(16.dp))
                        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){
                            FilterChip(selected=mode=="xtream",onClick={mode="xtream"},label={Text("Xtream Codes")})
                            FilterChip(selected=mode=="m3u",onClick={mode="m3u"},label={Text("M3U / URL")})
                        }
                    }
                }
            }
            item{
                OutlinedTextField(
                    name,{name=it},label={Text("Name")},
                    modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp),singleLine=true
                )
            }
            if(mode=="xtream"){
                item{
                    OutlinedTextField(
                        portal,{portal=it},label={Text("Portal / Domain")},
                        placeholder={Text("http://server.tld:8080")},
                        keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Uri),
                        modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp),singleLine=true
                    )
                }
                item{
                    OutlinedTextField(
                        user,{user=it},label={Text("Username")},
                        modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp),singleLine=true
                    )
                }
                item{
                    OutlinedTextField(
                        pass,{pass=it},label={Text("Passwort")},
                        visualTransformation=PasswordVisualTransformation(),
                        modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp),singleLine=true
                    )
                }
            }else{
                item{
                    OutlinedTextField(
                        url,{url=it},label={Text("M3U / get.php URL")},
                        keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Uri),
                        modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp),minLines=2
                    )
                }
            }
            if(u.error.isNotBlank()){
                item{Text(u.error,color=MaterialTheme.colorScheme.error,modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp))}
            }
            item{
                Button(
                    onClick={
                        if(mode=="xtream") vm.addXtream(name,portal,user,pass)
                        else vm.addPlaylist(name,url)
                    },
                    modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp).height(54.dp),
                    shape=MaterialTheme.shapes.medium,
                    colors=ButtonDefaults.buttonColors(containerColor=accent)
                ){
                    Text(if(mode=="xtream")"Xtream verbinden" else "Playlist speichern",fontWeight=FontWeight.Bold)
                }
            }
            item{
                Text(
                    "Am TV noch bequemer: Startseite → PC-Einrichtung. Dort werden Adresse und temporärer PIN angezeigt.",
                    fontSize=12.sp,color=Color.White.copy(.58f),
                    modifier=Modifier.fillMaxWidth(.94f).widthIn(max=820.dp).padding(top=2.dp)
                )
            }
        }
    }
}
'''


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f"markers missing: {start_marker!r} -> {end_marker!r}")
    return text[:start] + replacement + "\n" + text[end:]

s = replace_between(s, "@Composable\nfun HomeScreen", "@Composable\nfun AddPlaylistScreen", home)
s = replace_between(s, "@Composable\nfun AddPlaylistScreen", "@Composable\nfun CategoryScreen", add_playlist)
s = s.replace("Android v0.3.0", "Android v0.3.2")
s = s.replace(
    "Modernisierte Oberfläche · Xtream-Eingabe · lokale Browser-Verwaltung",
    "PC-Einrichtung auf Startseite · scrollbare Xtream-Eingabe · optimierte Stream-Pufferung"
)

path.write_text(s)
print("Screens.kt patched for Android v0.3.2")
