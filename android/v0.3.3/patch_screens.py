#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_screens.py <Screens.kt>')

path = Path(sys.argv[1])
s = path.read_text()


def replace_between(text: str, start_marker: str, end_marker: str, replacement: str) -> str:
    start = text.find(start_marker)
    end = text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f'markers missing: {start_marker!r} -> {end_marker!r}')
    return text[:start] + replacement + '\n' + text[end:]

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
            item{FocusCard("FILME","Poster, Infos & Resume",R.drawable.icon_movies,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.MOVIE))})}
            item{FocusCard("SERIEN","Infos, Staffeln & Episoden",R.drawable.icon_series,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.SERIES))})}
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
            item{
                FocusCard(
                    "APP-UPDATE",
                    "24h-Automatik + manuell jetzt prüfen",
                    R.drawable.icon_settings,
                    accent=accent,
                    onClick={vm.navigate(Screen.Updates)}
                )
            }
            item{FocusCard("EINSTELLUNGEN","Playlists, Sprache & weitere Optionen",R.drawable.icon_settings,accent=accent,onClick={vm.navigate(Screen.Settings)})}
        }
    }
}
'''

category_and_items = r'''@Composable
fun CategoryScreen(vm:MainViewModel,kind:MediaKind,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar(
            if(kind==MediaKind.LIVE)"LIVE-TV" else if(kind==MediaKind.MOVIE)"FILME" else "SERIEN",
            R.drawable.brand_header,
            {vm.back()}
        )
        LoadingOrError(u.loading,u.error)
        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal=16.dp),
            contentPadding=PaddingValues(top=4.dp,bottom=28.dp),
            verticalArrangement=Arrangement.spacedBy(9.dp)
        ){
            items(u.categories,key={it.id}){c->
                CategoryListRow(c.name,accent){vm.navigate(Screen.Items(kind,c))}
            }
        }
    }
}

@Composable
private fun CategoryListRow(title:String,accent:Color,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val shape=RoundedCornerShape(18.dp)
    Surface(
        modifier=Modifier.fillMaxWidth().onFocusChanged{focused=it.isFocused}.focusable().clickable(onClick=onClick),
        color=if(focused) Color(0xFF17283A) else Color(0xF20A111B),
        contentColor=Color.White,
        shape=shape,
        border=androidx.compose.foundation.BorderStroke(if(focused)2.dp else 1.dp,if(focused)accent else Color.White.copy(.08f)),
        shadowElevation=if(focused)8.dp else 1.dp
    ){
        Row(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=17.dp),verticalAlignment=Alignment.CenterVertically){
            Box(Modifier.size(9.dp).background(accent,RoundedCornerShape(99.dp)))
            Spacer(Modifier.width(15.dp))
            Text(title,fontSize=19.sp,fontWeight=FontWeight.Bold,modifier=Modifier.weight(1f),maxLines=2)
            Icon(Icons.Default.ChevronRight,null,tint=Color.White.copy(.58f))
        }
    }
}

@Composable
fun ItemsScreen(vm:MainViewModel,kind:MediaKind,cat:MediaCategory,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar(
            cat.name,
            R.drawable.brand_header,
            {vm.back()},
            actions={if(kind==MediaKind.LIVE)TextButton(onClick={vm.navigate(Screen.Epg(cat))}){Text("EPG",color=accent,fontWeight=FontWeight.Bold)}}
        )
        LoadingOrError(u.loading,u.error)
        if(u.epgLoading&&kind==MediaKind.LIVE)LinearProgressIndicator(modifier=Modifier.fillMaxWidth())
        if(kind==MediaKind.LIVE){
            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal=14.dp),
                contentPadding=PaddingValues(top=4.dp,bottom=30.dp),
                verticalArrangement=Arrangement.spacedBy(8.dp)
            ){
                items(u.items,key={it.kind.name+it.id}){m->
                    val now=nowEvent(u.epg[m.id].orEmpty())
                    LiveChannelRow(
                        media=m,
                        nowText=now?.let{"${clock(it.start)}–${clock(it.end)}  ${it.title}"}.orEmpty(),
                        accent=accent,
                        onClick={vm.play(m)}
                    )
                }
            }
        }else{
            LazyColumn(
                Modifier.fillMaxSize().padding(horizontal=14.dp),
                contentPadding=PaddingValues(top=4.dp,bottom=34.dp),
                verticalArrangement=Arrangement.spacedBy(12.dp)
            ){
                items(u.items,key={it.kind.name+it.id}){m->
                    LaunchedEffect(m.resumeKey){vm.ensureDetails(m)}
                    val detail=u.details[m.resumeKey]?:m
                    MediaInfoRow(
                        media=detail,
                        loading=u.detailLoading.contains(m.resumeKey),
                        accent=accent,
                        isTv=isTv,
                        onClick={if(kind==MediaKind.SERIES)({vm.navigate(Screen.Episodes(detail))}) else ({vm.play(detail)})}
                    )
                }
            }
        }
    }
}

@Composable
private fun LiveChannelRow(media:MediaEntry,nowText:String,accent:Color,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val shape=RoundedCornerShape(18.dp)
    Surface(
        modifier=Modifier.fillMaxWidth().onFocusChanged{focused=it.isFocused}.focusable().clickable(onClick=onClick),
        color=if(focused) Color(0xFF17283A) else Color(0xF50A111A),
        contentColor=Color.White,
        shape=shape,
        border=androidx.compose.foundation.BorderStroke(if(focused)2.dp else 1.dp,if(focused)accent else Color.White.copy(.08f)),
        shadowElevation=if(focused)8.dp else 1.dp
    ){
        Row(Modifier.fillMaxWidth().padding(horizontal=15.dp,vertical=11.dp),verticalAlignment=Alignment.CenterVertically){
            Surface(shape=RoundedCornerShape(14.dp),color=Color.White.copy(.08f),modifier=Modifier.size(66.dp)){
                if(media.image.isNotBlank())AsyncImage(media.image,null,Modifier.fillMaxSize().padding(7.dp),contentScale=ContentScale.Fit)
                else Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){Icon(Icons.Default.LiveTv,null,tint=accent,modifier=Modifier.size(32.dp))}
            }
            Spacer(Modifier.width(16.dp))
            Column(Modifier.weight(1f)){
                Text(media.name,color=Color.White,fontSize=19.sp,fontWeight=FontWeight.ExtraBold,maxLines=2)
                if(nowText.isNotBlank())Text(nowText,color=Color.White.copy(.68f),fontSize=13.sp,maxLines=2,modifier=Modifier.padding(top=4.dp))
                else Text("Live-TV",color=Color.White.copy(.45f),fontSize=12.sp,modifier=Modifier.padding(top=4.dp))
            }
            Icon(Icons.Default.PlayArrow,null,tint=if(focused)accent else Color.White.copy(.6f),modifier=Modifier.size(34.dp))
        }
    }
}

@Composable
private fun MediaInfoRow(media:MediaEntry,loading:Boolean,accent:Color,isTv:Boolean,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val shape=RoundedCornerShape(22.dp)
    val posterWidth=if(isTv)142.dp else 108.dp
    val posterHeight=if(isTv)205.dp else 162.dp
    Surface(
        modifier=Modifier.fillMaxWidth().onFocusChanged{focused=it.isFocused}.focusable().clickable(onClick=onClick),
        color=if(focused) Color(0xFF17283A) else Color(0xF50A111A),
        contentColor=Color.White,
        shape=shape,
        border=androidx.compose.foundation.BorderStroke(if(focused)2.dp else 1.dp,if(focused)accent else Color.White.copy(.09f)),
        shadowElevation=if(focused)10.dp else 2.dp
    ){
        Row(Modifier.fillMaxWidth().padding(14.dp),verticalAlignment=Alignment.Top){
            Surface(shape=RoundedCornerShape(17.dp),color=Color.White.copy(.07f),modifier=Modifier.width(posterWidth).height(posterHeight)){
                if(media.image.isNotBlank())AsyncImage(media.image,null,Modifier.fillMaxSize(),contentScale=ContentScale.Crop)
                else Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){Icon(if(media.kind==MediaKind.SERIES)Icons.Default.Tv else Icons.Default.Movie,null,tint=accent,modifier=Modifier.size(46.dp))}
            }
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f).padding(vertical=3.dp)){
                Row(verticalAlignment=Alignment.CenterVertically){
                    Text(media.name,fontSize=if(isTv)22.sp else 18.sp,fontWeight=FontWeight.Black,modifier=Modifier.weight(1f),maxLines=2)
                    if(loading)CircularProgressIndicator(Modifier.size(18.dp),strokeWidth=2.dp,color=accent)
                }
                val meta=buildList{
                    if(media.year.isNotBlank())add(media.year)
                    if(media.duration.isNotBlank())add(media.duration)
                    if(media.genre.isNotBlank())add(media.genre)
                    if(media.rating.isNotBlank())add("★ ${media.rating}")
                }.joinToString("  ·  ")
                if(meta.isNotBlank())Text(meta,color=accent,fontSize=13.sp,fontWeight=FontWeight.Bold,maxLines=2,modifier=Modifier.padding(top=6.dp))
                if(media.cast.isNotBlank()){
                    Text("Schauspieler: ${media.cast}",color=Color.White.copy(.76f),fontSize=13.sp,maxLines=2,modifier=Modifier.padding(top=8.dp))
                }
                if(media.director.isNotBlank()){
                    Text("Regie: ${media.director}",color=Color.White.copy(.62f),fontSize=12.sp,maxLines=1,modifier=Modifier.padding(top=3.dp))
                }
                if(media.plot.isNotBlank()){
                    Text(media.plot,color=Color.White.copy(.72f),fontSize=13.sp,maxLines=if(isTv)5 else 4,modifier=Modifier.padding(top=9.dp))
                }else if(loading){
                    Text("Filminformationen werden geladen …",color=Color.White.copy(.48f),fontSize=12.sp,modifier=Modifier.padding(top=9.dp))
                }
                Spacer(Modifier.weight(1f))
                Text(if(media.kind==MediaKind.SERIES)"Öffnen →" else "Abspielen →",color=if(focused)accent else Color.White.copy(.62f),fontWeight=FontWeight.Bold,modifier=Modifier.padding(top=8.dp))
            }
        }
    }
}
'''

settings = r'''@Composable
fun SettingsScreen(vm:MainViewModel,accent:Color){
    val u by vm.ui.collectAsState()
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar("EINSTELLUNGEN",R.drawable.brand_header,{vm.back()})
        LazyColumn(Modifier.fillMaxSize().padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){
            item{FocusCard("Skin / Design",u.themeCatalog?.themes?.get(u.themeId)?.label.orEmpty(),R.drawable.icon_settings,accent=accent,onClick={vm.navigate(Screen.Themes)})}
            item{FocusCard("Playlists verwalten","${u.playlists.size} gespeichert",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.Playlists)})}
            item{FocusCard("PC-Verwaltung im Browser",if(u.webAdminRunning)"Aktiv · ${u.webAdminUrl}" else "Xtream/M3U bequem am Computer eingeben",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.WebAdmin)})}
            item{FocusCard("App-Update","Automatisch alle 24h oder jetzt manuell prüfen",R.drawable.icon_settings,accent=accent,onClick={vm.navigate(Screen.Updates)})}
            item{FocusCard("Bevorzugte Audiosprache",lang(u.preferredAudioLanguage),R.drawable.icon_settings,accent=accent,onClick={vm.setAudioLanguage(nextAudio(u.preferredAudioLanguage))})}
            item{FocusCard("Bevorzugte Untertitelsprache",lang(u.preferredSubtitleLanguage),R.drawable.icon_settings,accent=accent,onClick={vm.setSubtitleLanguage(nextSub(u.preferredSubtitleLanguage))})}
            item{GlassPanel(Modifier.fillMaxWidth()){Column(Modifier.padding(20.dp)){Text("Android v0.3.3",fontWeight=FontWeight.Bold);Text("Listenansicht · Xtream-Metadaten · sichtbarer App-Updater",color=Color.White.copy(.62f))}}}
        }
    }
}
'''

s = replace_between(s, '@Composable\nfun HomeScreen', '@Composable\nfun AddPlaylistScreen', home)
s = replace_between(s, '@Composable\nfun CategoryScreen', '@Composable\nfun EpisodesScreen', category_and_items)
s = replace_between(s, '@Composable\nfun SettingsScreen', '@Composable\nfun WebAdminScreen', settings)
s = s.replace('Android v0.3.2','Android v0.3.3')
path.write_text(s)
print('Screens.kt patched for Android v0.3.3')
