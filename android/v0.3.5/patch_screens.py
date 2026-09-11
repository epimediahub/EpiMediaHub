#!/usr/bin/env python3
from pathlib import Path
import sys

if len(sys.argv) != 2:
    raise SystemExit('usage: patch_screens.py <Screens.kt>')

path = Path(sys.argv[1])
s = path.read_text()

def replace_between(text, start_marker, end_marker, replacement):
    start=text.find(start_marker); end=text.find(end_marker)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit(f'markers missing: {start_marker!r} -> {end_marker!r}')
    return text[:start] + replacement + '\n' + text[end:]

s=s.replace('import androidx.compose.foundation.lazy.items\n','import androidx.compose.foundation.lazy.items\nimport androidx.compose.foundation.lazy.itemsIndexed\nimport androidx.compose.foundation.lazy.rememberLazyListState\n',1)

home=r'''@Composable
fun HomeScreen(vm:MainViewModel,isTv:Boolean,accent:Color){
    val u by vm.ui.collectAsState()
    val cols=if(isTv)4 else 2
    Column(Modifier.fillMaxSize()){
        EpiTopBar(u.active?.name?:"EpiMediaHub",R.drawable.brand_header,actions={Text(if(isTv)"ANDROID TV" else "MOBILE",color=Color.White.copy(.62f),fontWeight=FontWeight.SemiBold)})
        Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){
            LazyVerticalGrid(GridCells.Fixed(cols),Modifier.fillMaxWidth(if(isTv)0.92f else 0.96f).padding(18.dp),horizontalArrangement=Arrangement.spacedBy(16.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){
                item{FocusCard("LIVE TV","Sender & EPG",R.drawable.icon_live,accent=accent,onClick={vm.openLibrary(MediaKind.LIVE)},modifier=Modifier.heightIn(min=138.dp))}
                item{FocusCard("FILME","VOD-Mediathek",R.drawable.icon_movies,accent=accent,onClick={vm.openLibrary(MediaKind.MOVIE)},modifier=Modifier.heightIn(min=138.dp))}
                item{FocusCard("SERIEN","Staffeln & Episoden",R.drawable.icon_series,accent=accent,onClick={vm.openLibrary(MediaKind.SERIES)},modifier=Modifier.heightIn(min=138.dp))}
                item{FocusCard("EINSTELLUNGEN","Playlist · Design · Update",R.drawable.icon_settings,accent=accent,onClick={vm.navigate(Screen.Settings)},modifier=Modifier.heightIn(min=138.dp))}
            }
        }
    }
}
'''

browser=r'''@Composable
fun CategoryScreen(vm:MainViewModel,kind:MediaKind,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar(sectionTitle(kind),R.drawable.brand_header,{vm.back()})
        LoadingOrError(u.loading,u.error)
        LazyColumn(Modifier.fillMaxSize().padding(horizontal=if(isTv)80.dp else 16.dp,vertical=10.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
            items(u.categories,key={it.id}){c->CategoryListRow(c.name,accent){vm.switchLibraryCategory(kind,c)}}
        }
    }
}

@Composable
fun ItemsScreen(vm:MainViewModel,kind:MediaKind,cat:MediaCategory,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    BackHandler{vm.back()}
    val initial=remember(kind,cat.id,u.active?.id){vm.browserPosition(kind,cat.id)}
    val listState=rememberLazyListState(initialFirstVisibleItemIndex=initial)
    Column(Modifier.fillMaxSize()){
        EpiTopBar(sectionTitle(kind),R.drawable.brand_header,{vm.back()},actions={Text(cat.name,color=accent,fontWeight=FontWeight.Bold,maxLines=1)})
        LoadingOrError(u.loading,u.error)
        if(u.epgLoading&&kind==MediaKind.LIVE)LinearProgressIndicator(modifier=Modifier.fillMaxWidth())
        if(isTv){
            Row(Modifier.fillMaxSize().padding(horizontal=14.dp,vertical=8.dp),horizontalArrangement=Arrangement.spacedBy(12.dp)){
                LibrarySideBar(vm,kind,cat,accent,Modifier.width(265.dp).fillMaxHeight())
                Surface(Modifier.weight(1f).fillMaxHeight(),color=Color(0xF20A0F17),shape=RoundedCornerShape(18.dp),border=androidx.compose.foundation.BorderStroke(1.dp,Color.White.copy(.08f))){
                    LazyColumn(state=listState,modifier=Modifier.fillMaxSize().padding(10.dp),contentPadding=PaddingValues(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(if(kind==MediaKind.LIVE)7.dp else 11.dp)){
                        itemsIndexed(u.items,key={_,m->m.kind.name+m.id}){index,m->
                            if(kind==MediaKind.LIVE){
                                val now=nowEvent(u.epg[m.id].orEmpty())
                                LiveChannelRow(m,now?.let{"${clock(it.start)}–${clock(it.end)}  ${it.title}"}.orEmpty(),accent){
                                    vm.rememberBrowserPosition(kind,cat.id,index,m.id);vm.play(m)
                                }
                            }else{
                                LaunchedEffect(m.resumeKey){vm.ensureDetails(m)}
                                val detail=u.details[m.resumeKey]?:m
                                MediaInfoRow(detail,u.detailLoading.contains(m.resumeKey),accent,true){
                                    vm.rememberBrowserPosition(kind,cat.id,index,m.id)
                                    if(kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(detail)) else vm.play(detail)
                                }
                            }
                        }
                    }
                }
            }
        }else{
            Column(Modifier.fillMaxSize()){
                Row(Modifier.fillMaxWidth().padding(horizontal=10.dp,vertical=6.dp),horizontalArrangement=Arrangement.spacedBy(6.dp)){
                    OutlinedButton(onClick={vm.navigate(Screen.Categories(kind),remember=false),modifier=Modifier.weight(1f)){Text("Kategorien")}
                    OutlinedButton(onClick={vm.openKindSearch(kind)},modifier=Modifier.weight(1f)){Text("Suche")}
                    OutlinedButton(onClick={vm.openKindFavorites(kind)},modifier=Modifier.weight(1f)){Text("Favoriten")}
                }
                LazyColumn(state=listState,modifier=Modifier.fillMaxSize().padding(horizontal=10.dp),contentPadding=PaddingValues(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                    itemsIndexed(u.items,key={_,m->m.kind.name+m.id}){index,m->
                        if(kind==MediaKind.LIVE){
                            val now=nowEvent(u.epg[m.id].orEmpty())
                            LiveChannelRow(m,now?.title.orEmpty(),accent){vm.rememberBrowserPosition(kind,cat.id,index,m.id);vm.play(m)}
                        }else{
                            LaunchedEffect(m.resumeKey){vm.ensureDetails(m)}
                            val detail=u.details[m.resumeKey]?:m
                            MediaInfoRow(detail,u.detailLoading.contains(m.resumeKey),accent,false){vm.rememberBrowserPosition(kind,cat.id,index,m.id);if(kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(detail))else vm.play(detail)}
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun LibrarySideBar(vm:MainViewModel,kind:MediaKind,cat:MediaCategory,accent:Color,modifier:Modifier=Modifier){
    val u by vm.ui.collectAsState()
    val favCount=u.favorites.count{matchesSection(it,kind)}
    val favLabel=if(favCount>0) "Favoriten ($favCount)" else "Favoriten"
    Surface(modifier=modifier,color=Color(0xF20A0F17),shape=RoundedCornerShape(18.dp),border=androidx.compose.foundation.BorderStroke(1.dp,Color.White.copy(.08f))){
        LazyColumn(Modifier.fillMaxSize().padding(9.dp),verticalArrangement=Arrangement.spacedBy(5.dp)){
            item{SideBarRow("Suche",false,accent,Icons.Default.Search){vm.openKindSearch(kind)}}
            item{SideBarRow(favLabel,false,accent,Icons.Default.FavoriteBorder){vm.openKindFavorites(kind)}}
            item{Box(Modifier.fillMaxWidth().padding(vertical=5.dp).height(1.dp).background(Color.White.copy(.08f)))}
            items(u.categories,key={it.id}){c->SideBarRow(c.name,c.id==cat.id,accent,Icons.Default.Folder){if(c.id!=cat.id)vm.switchLibraryCategory(kind,c)}}
        }
    }
}

@Composable
private fun SideBarRow(title:String,selected:Boolean,accent:Color,icon:androidx.compose.ui.graphics.vector.ImageVector,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val shape=RoundedCornerShape(12.dp)
    Row(Modifier.fillMaxWidth().onFocusChanged{focused=it.isFocused}.focusable().background(if(selected||focused)accent.copy(if(focused)0.30f else 0.18f)else Color.Transparent,shape).border(1.dp,if(focused)accent else Color.Transparent,shape).clickable(onClick=onClick).padding(horizontal=11.dp,vertical=11.dp),verticalAlignment=Alignment.CenterVertically){
        Icon(icon,null,tint=if(selected||focused)accent else Color.White.copy(.58f),modifier=Modifier.size(20.dp));Spacer(Modifier.width(9.dp));Text(title,color=Color.White,fontWeight=if(selected||focused)FontWeight.Bold else FontWeight.Medium,fontSize=14.sp,maxLines=2)
    }
}

private fun sectionTitle(kind:MediaKind)=when(kind){MediaKind.LIVE->"LIVE TV";MediaKind.MOVIE->"FILME";MediaKind.SERIES->"SERIEN";MediaKind.EPISODE->"EPISODEN"}
private fun matchesSection(media:MediaEntry,kind:MediaKind)=media.kind==kind||(kind==MediaKind.SERIES&&media.kind==MediaKind.EPISODE)
'''

search_favorites=r'''@Composable
fun SearchScreen(vm:MainViewModel,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    val kind=u.contentFilterKind
    var q by remember{mutableStateOf("")}
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar("${kind?.let{sectionTitle(it)+" · "}.orEmpty()}SUCHE",R.drawable.brand_header,{vm.back()})
        OutlinedTextField(q,{q=it;vm.search(it)},label={Text("Suchen")},leadingIcon={Icon(Icons.Default.Search,null)},singleLine=true,modifier=Modifier.fillMaxWidth().padding(horizontal=if(isTv)70.dp else 14.dp,vertical=10.dp))
        LoadingOrError(u.loading,u.error)
        LazyColumn(Modifier.fillMaxSize().padding(horizontal=if(isTv)70.dp else 14.dp),contentPadding=PaddingValues(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
            items(u.searchResults,key={it.resumeKey}){m->
                if(m.kind==MediaKind.LIVE){
                    LiveChannelRow(m,"Live TV",accent){vm.play(m)}
                }else{
                    LaunchedEffect(m.resumeKey){vm.ensureDetails(m)}
                    val d=u.details[m.resumeKey]?:m
                    MediaInfoRow(d,u.detailLoading.contains(m.resumeKey),accent,isTv){
                        if(m.kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(d)) else vm.play(d)
                    }
                }
            }
        }
    }
}

@Composable
fun FavoritesScreen(vm:MainViewModel,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    val kind=u.contentFilterKind
    val list=if(kind==null)u.favorites else u.favorites.filter{matchesSection(it,kind)}
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar("${kind?.let{sectionTitle(it)+" · "}.orEmpty()}FAVORITEN",R.drawable.brand_header,{vm.back()})
        if(list.isEmpty()){
            EmptyState("Keine Favoriten","Favoriten aus diesem Bereich erscheinen hier.")
        }else{
            LazyColumn(Modifier.fillMaxSize().padding(horizontal=if(isTv)70.dp else 14.dp,vertical=8.dp),contentPadding=PaddingValues(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(8.dp)){
                items(list,key={it.resumeKey}){m->
                    if(m.kind==MediaKind.LIVE){
                        LiveChannelRow(m,"Live TV",accent){vm.play(m)}
                    }else{
                        LaunchedEffect(m.resumeKey){vm.ensureDetails(m)}
                        val d=u.details[m.resumeKey]?:m
                        MediaInfoRow(d,u.detailLoading.contains(m.resumeKey),accent,isTv){
                            if(m.kind==MediaKind.SERIES)vm.navigate(Screen.Episodes(d)) else vm.play(d)
                        }
                    }
                }
            }
        }
    }
}
'''

s=replace_between(s,'@Composable\nfun HomeScreen','@Composable\nfun AddPlaylistScreen',home)
s=replace_between(s,'@Composable\nfun CategoryScreen','@Composable\nfun EpisodesScreen',browser)
s=replace_between(s,'@Composable\nfun SearchScreen','@Composable\nfun ContinueWatchingScreen',search_favorites)
s=s.replace('Android v0.3.4','Android v0.3.5')
s=s.replace('Update-Test · Listenansicht · Xtream-Metadaten · sichtbarer App-Updater','IBO-inspirierter Browser · Kategorien links · Positionsspeicher')
path.write_text(s)
print('Screens.kt patched for Android v0.3.5')
