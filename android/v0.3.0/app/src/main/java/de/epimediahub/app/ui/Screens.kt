package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items as gridItems
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import coil.compose.AsyncImage
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.model.*
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

@Composable
fun HomeScreen(vm:MainViewModel,isTv:Boolean,accent:Color){
    val u by vm.ui.collectAsState(); val cols=if(isTv)3 else 2
    Column(Modifier.fillMaxSize()){
        EpiTopBar(u.active?.name?:"EpiMediaHub",R.drawable.brand_header,actions={Text(if(isTv)"ANDROID TV" else "MOBILE",color=accent,fontWeight=FontWeight.Bold)})
        LazyVerticalGrid(GridCells.Fixed(cols),Modifier.fillMaxSize().padding(18.dp),horizontalArrangement=Arrangement.spacedBy(14.dp),verticalArrangement=Arrangement.spacedBy(14.dp)){
            item{FocusCard("LIVE-TV","Sender & EPG",R.drawable.icon_live,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.LIVE))})}
            item{FocusCard("FILME","VOD & Resume",R.drawable.icon_movies,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.MOVIE))})}
            item{FocusCard("SERIEN","Staffeln & Episoden",R.drawable.icon_series,accent=accent,onClick={vm.navigate(Screen.Categories(MediaKind.SERIES))})}
            item{FocusCard("SUCHE","Sender, Filme, Serien",R.drawable.icon_search,accent=accent,onClick={vm.navigate(Screen.Search)})}
            if(u.continueWatching.isNotEmpty()) item{FocusCard("WEITERSCHAUEN","${u.continueWatching.size} Titel",R.drawable.icon_movies,accent=accent,onClick={vm.navigate(Screen.ContinueWatching)})}
            item{FocusCard("FAVORITEN","${u.favorites.size} gespeichert",R.drawable.icon_live,accent=accent,onClick={vm.navigate(Screen.Favorites)})}
            if(u.playlists.size>1) item{FocusCard("PLAYLIST WECHSELN","${u.playlists.size} Profile",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.Playlists)})}
            item{FocusCard("EINSTELLUNGEN","Design, Sprache & PC-Verwaltung",R.drawable.icon_settings,accent=accent,onClick={vm.navigate(Screen.Settings)})}
        }
    }
}

@Composable
fun AddPlaylistScreen(vm:MainViewModel,accent:Color){
    val u by vm.ui.collectAsState(); var mode by remember{mutableStateOf("xtream")};var name by remember{mutableStateOf("")};var url by remember{mutableStateOf("")};var portal by remember{mutableStateOf("")};var user by remember{mutableStateOf("")};var pass by remember{mutableStateOf("")}
    BackHandler(enabled=u.playlists.isNotEmpty()){vm.back()}
    Box(Modifier.fillMaxSize().padding(18.dp),contentAlignment=Alignment.Center){GlassPanel(Modifier.fillMaxWidth(.94f).widthIn(max=820.dp)){Column(Modifier.padding(28.dp)){
        Text("Playlist hinzufügen",fontSize=30.sp,fontWeight=FontWeight.Black);Text("Xtream Codes: Portal, Benutzername und Passwort reichen aus.",color=Color.White.copy(.68f));Spacer(Modifier.height(18.dp))
        Row(horizontalArrangement=Arrangement.spacedBy(10.dp)){FilterChip(mode=="xtream",{mode="xtream"},{Text("Xtream Codes")});FilterChip(mode=="m3u",{mode="m3u"},{Text("M3U / URL")})}
        Spacer(Modifier.height(12.dp));OutlinedTextField(name,{name=it},label={Text("Name")},modifier=Modifier.fillMaxWidth(),singleLine=true);Spacer(Modifier.height(9.dp))
        if(mode=="xtream"){
            OutlinedTextField(portal,{portal=it},label={Text("Portal / Domain")},placeholder={Text("http://server.tld:8080")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Uri),modifier=Modifier.fillMaxWidth(),singleLine=true);Spacer(Modifier.height(9.dp))
            OutlinedTextField(user,{user=it},label={Text("Username")},modifier=Modifier.fillMaxWidth(),singleLine=true);Spacer(Modifier.height(9.dp));OutlinedTextField(pass,{pass=it},label={Text("Passwort")},visualTransformation=PasswordVisualTransformation(),modifier=Modifier.fillMaxWidth(),singleLine=true)
        } else OutlinedTextField(url,{url=it},label={Text("M3U / get.php URL")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Uri),modifier=Modifier.fillMaxWidth(),minLines=2)
        if(u.error.isNotBlank())Text(u.error,color=MaterialTheme.colorScheme.error,modifier=Modifier.padding(top=8.dp));Spacer(Modifier.height(16.dp))
        Button(onClick={if(mode=="xtream")vm.addXtream(name,portal,user,pass) else vm.addPlaylist(name,url)},modifier=Modifier.fillMaxWidth().height(52.dp),shape=MaterialTheme.shapes.medium,colors=ButtonDefaults.buttonColors(containerColor=accent)){Text(if(mode=="xtream")"Xtream verbinden" else "Playlist speichern",fontWeight=FontWeight.Bold)}
        Text("Am TV noch bequemer: Einstellungen → PC-Verwaltung.",fontSize=12.sp,color=Color.White.copy(.5f),modifier=Modifier.padding(top=9.dp))
    }}}
}

@Composable
fun CategoryScreen(vm:MainViewModel,kind:MediaKind,accent:Color,isTv:Boolean){val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar(if(kind==MediaKind.LIVE)"LIVE-TV" else if(kind==MediaKind.MOVIE)"FILME" else "SERIEN",R.drawable.brand_header,{vm.back()});LoadingOrError(u.loading,u.error);LazyVerticalGrid(GridCells.Fixed(if(isTv)4 else 2),Modifier.fillMaxSize().padding(16.dp),horizontalArrangement=Arrangement.spacedBy(11.dp),verticalArrangement=Arrangement.spacedBy(11.dp)){gridItems(u.categories,key={it.id}){c->FocusCard(c.name,accent=accent,onClick={vm.navigate(Screen.Items(kind,c))})}}}}

@Composable
fun ItemsScreen(vm:MainViewModel,kind:MediaKind,cat:MediaCategory,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar(cat.name,R.drawable.brand_header,{vm.back()},actions={if(kind==MediaKind.LIVE)TextButton(onClick={vm.navigate(Screen.Epg(cat))}){Text("EPG",color=accent,fontWeight=FontWeight.Bold)}});LoadingOrError(u.loading,u.error);if(u.epgLoading&&kind==MediaKind.LIVE)LinearProgressIndicator(Modifier.fillMaxWidth());LazyVerticalGrid(GridCells.Fixed(if(isTv)5 else 2),Modifier.fillMaxSize().padding(14.dp),horizontalArrangement=Arrangement.spacedBy(10.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){gridItems(u.items,key={it.kind.name+it.id}){m->val now=nowEvent(u.epg[m.id].orEmpty());MediaCard(m,accent,if(kind==MediaKind.LIVE)now?.let{"${clock(it.start)}–${clock(it.end)} · ${it.title}"}.orEmpty() else m.plot,onClick={if(kind==MediaKind.SERIES){{vm.navigate(Screen.Episodes(m))}}else{{vm.play(m)}}})}}}}

@Composable
fun EpisodesScreen(vm:MainViewModel,series:MediaEntry,accent:Color,isTv:Boolean){val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar(series.name,R.drawable.brand_header,{vm.back()});LoadingOrError(u.loading,u.error);LazyVerticalGrid(GridCells.Fixed(if(isTv)5 else 2),Modifier.fillMaxSize().padding(14.dp),horizontalArrangement=Arrangement.spacedBy(10.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){gridItems(u.items,key={it.id}){e->MediaCard(e,accent,"S${e.season} · E${e.episode}",onClick={vm.play(e,u.items)})}}}}

@Composable
fun MediaCard(media:MediaEntry,accent:Color,subtitle:String="",progress:Float?=null,onClick:()->Unit){
    var focus by remember{mutableStateOf(false)};val shape=RoundedCornerShape(24.dp)
    Column(Modifier.height(245.dp).onFocusChanged{focus=it.isFocused}.focusable().border(if(focus)2.dp else 1.dp,if(focus)accent else Color.White.copy(.1f),shape).background(Brush.verticalGradient(listOf(Color(0xE8172A43),Color(0xEE09131F))),shape).clickable(onClick=onClick)){
        if(media.image.isNotBlank())AsyncImage(media.image,null,Modifier.fillMaxWidth().weight(1f),contentScale=ContentScale.Crop) else Box(Modifier.fillMaxWidth().weight(1f).background(accent.copy(.14f)),contentAlignment=Alignment.Center){Icon(Icons.Default.PlayArrow,null,Modifier.size(48.dp),tint=Color.White.copy(.85f))}
        Column(Modifier.padding(12.dp)){Text(media.name,fontWeight=FontWeight.ExtraBold,maxLines=2);if(subtitle.isNotBlank())Text(subtitle,color=Color.White.copy(.62f),fontSize=12.sp,maxLines=2);if(media.rating.isNotBlank())Text("★ ${media.rating}",color=accent,fontSize=12.sp);progress?.let{LinearProgressIndicator({it},Modifier.fillMaxWidth().padding(top=6.dp))}}
    }
}

@Composable
fun SearchScreen(vm:MainViewModel,accent:Color,isTv:Boolean){val u by vm.ui.collectAsState();var q by remember{mutableStateOf("")};BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar("SUCHE",R.drawable.brand_header,{vm.back()});OutlinedTextField(q,{q=it;vm.search(it)},label={Text("Suchen")},leadingIcon={Icon(Icons.Default.Search,null)},singleLine=true,modifier=Modifier.fillMaxWidth().padding(14.dp));LoadingOrError(u.loading,u.error);LazyVerticalGrid(GridCells.Fixed(if(isTv)5 else 2),Modifier.fillMaxSize().padding(14.dp),horizontalArrangement=Arrangement.spacedBy(10.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){gridItems(u.searchResults,key={it.kind.name+it.id}){m->MediaCard(m,accent,m.kind.name,onClick={if(m.kind==MediaKind.SERIES){{vm.navigate(Screen.Episodes(m))}}else{{vm.play(m)}}})}}}}

@Composable
fun FavoritesScreen(vm:MainViewModel,accent:Color,isTv:Boolean){val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar("FAVORITEN",R.drawable.brand_header,{vm.back()});if(u.favorites.isEmpty())EmptyState("Keine Favoriten","Speichere Sender, Filme oder Episoden als Favorit.") else LazyVerticalGrid(GridCells.Fixed(if(isTv)5 else 2),Modifier.fillMaxSize().padding(14.dp),horizontalArrangement=Arrangement.spacedBy(10.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){gridItems(u.favorites,key={it.resumeKey}){m->MediaCard(m,accent,m.kind.name,onClick={if(m.kind==MediaKind.SERIES){{vm.navigate(Screen.Episodes(m))}}else{{vm.play(m)}}})}}}}

@Composable
fun ContinueWatchingScreen(vm:MainViewModel,accent:Color,isTv:Boolean){val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar("WEITERSCHAUEN",R.drawable.brand_header,{vm.back()});if(u.continueWatching.isEmpty())EmptyState("Nichts offen","Angefangene Filme und Episoden erscheinen hier.") else LazyVerticalGrid(GridCells.Fixed(if(isTv)5 else 2),Modifier.fillMaxSize().padding(14.dp),horizontalArrangement=Arrangement.spacedBy(10.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){gridItems(u.continueWatching,key={it.media.resumeKey}){c->MediaCard(c.media,accent,"Fortsetzen",c.progress){vm.play(c.media)}}}}}

@Composable
fun EpgScreen(vm:MainViewModel,cat:MediaCategory,accent:Color,isTv:Boolean){val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar("EPG · ${cat.name}",R.drawable.brand_header,{vm.back()});LazyColumn(Modifier.fillMaxSize().padding(14.dp),verticalArrangement=Arrangement.spacedBy(9.dp)){items(u.items,key={it.id}){m->val epg=u.epg[m.id].orEmpty();if(epg.isEmpty())vm.ensureEpg(m);GlassPanel(Modifier.fillMaxWidth()){Column(Modifier.padding(15.dp)){Text(m.name,fontWeight=FontWeight.ExtraBold,color=accent);epg.take(3).forEach{e->Text("${clock(e.start)}–${clock(e.end)}  ${e.title}",fontWeight=FontWeight.SemiBold);if(e.description.isNotBlank())Text(e.description,color=Color.White.copy(.58f),fontSize=12.sp,maxLines=2);Spacer(Modifier.height(6.dp))}}}}}}}

@Composable
fun PlaylistsScreen(vm:MainViewModel,accent:Color){val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar("PLAYLISTS",R.drawable.brand_header,{vm.back()},actions={TextButton(onClick={vm.navigate(Screen.AddPlaylist)}){Text("+ Hinzufügen",color=accent)}});LazyColumn(Modifier.fillMaxSize().padding(16.dp),verticalArrangement=Arrangement.spacedBy(10.dp)){items(u.playlists,key={it.id}){p->GlassPanel(Modifier.fillMaxWidth()){Row(Modifier.padding(16.dp),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(p.name,fontWeight=FontWeight.Bold);Text(p.type.name,color=Color.White.copy(.6f))};Button(onClick={vm.selectPlaylist(p.id)},colors=ButtonDefaults.buttonColors(containerColor=accent),shape=MaterialTheme.shapes.small){Text(if(p.id==u.active?.id)"Aktiv" else "Wählen")};TextButton(onClick={vm.removePlaylist(p.id)}){Text("Löschen",color=Color(0xFFFF8585))}}}}}}}

@Composable
fun SettingsScreen(vm:MainViewModel,accent:Color){val u by vm.ui.collectAsState();BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar("EINSTELLUNGEN",R.drawable.brand_header,{vm.back()});LazyColumn(Modifier.fillMaxSize().padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)){item{FocusCard("Skin / Design",u.themeCatalog?.themes?.get(u.themeId)?.label.orEmpty(),R.drawable.icon_settings,accent=accent,onClick={vm.navigate(Screen.Themes)})};item{FocusCard("Playlists verwalten","${u.playlists.size} gespeichert",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.Playlists)})};item{FocusCard("PC-Verwaltung im Browser",if(u.webAdminRunning)"Aktiv · ${u.webAdminUrl}" else "Xtream/M3U bequem am Computer eingeben",R.drawable.icon_playlist,accent=accent,onClick={vm.navigate(Screen.WebAdmin)})};item{FocusCard("Bevorzugte Audiosprache",lang(u.preferredAudioLanguage),R.drawable.icon_settings,accent=accent,onClick={vm.setAudioLanguage(nextAudio(u.preferredAudioLanguage))})};item{FocusCard("Bevorzugte Untertitelsprache",lang(u.preferredSubtitleLanguage),R.drawable.icon_settings,accent=accent,onClick={vm.setSubtitleLanguage(nextSub(u.preferredSubtitleLanguage))})};item{GlassPanel(Modifier.fillMaxWidth()){Column(Modifier.padding(20.dp)){Text("Android v0.3.0",fontWeight=FontWeight.Bold);Text("Modernisierte Oberfläche · Xtream-Eingabe · lokale Browser-Verwaltung",color=Color.White.copy(.62f))}}}}}}

@Composable
fun WebAdminScreen(vm:MainViewModel,accent:Color){val u by vm.ui.collectAsState();BackHandler{vm.back()};LaunchedEffect(Unit){if(!u.webAdminRunning)vm.startWebAdmin()};Column(Modifier.fillMaxSize()){EpiTopBar("PC-VERWALTUNG",R.drawable.brand_header,{vm.back()});Box(Modifier.fillMaxSize().padding(18.dp),contentAlignment=Alignment.TopCenter){GlassPanel(Modifier.fillMaxWidth().widthIn(max=820.dp)){Column(Modifier.padding(28.dp)){Icon(Icons.Default.Computer,null,tint=accent,modifier=Modifier.size(48.dp));Text("Playlist am Computer einrichten",fontSize=28.sp,fontWeight=FontWeight.Black,modifier=Modifier.padding(top=12.dp));Text("Computer und Gerät müssen im selben lokalen Netzwerk sein. Der Zugriff ist zusätzlich mit einem temporären PIN geschützt.",color=Color.White.copy(.67f),modifier=Modifier.padding(vertical=12.dp));if(u.webAdminRunning){Text("ADRESSE",color=accent,fontWeight=FontWeight.Bold);SelectionContainer{Text(u.webAdminUrl,fontSize=22.sp,fontWeight=FontWeight.Bold)};Spacer(Modifier.height(18.dp));Text("PIN",color=accent,fontWeight=FontWeight.Bold);Text(u.webAdminPin,fontSize=38.sp,fontWeight=FontWeight.Black,letterSpacing=6.sp);Spacer(Modifier.height(18.dp));Text("Im Browser: Xtream Codes mit Portal + Username + Passwort oder M3U/get.php. EpiMediaHub baut die benötigten Xtream-URLs automatisch.",color=Color.White.copy(.7f));OutlinedButton(onClick={vm.stopWebAdmin()},modifier=Modifier.padding(top=20.dp),shape=MaterialTheme.shapes.medium){Text("PC-Verwaltung stoppen")}}else{if(u.error.isNotBlank())Text(u.error,color=MaterialTheme.colorScheme.error);Button(onClick={vm.startWebAdmin()},colors=ButtonDefaults.buttonColors(containerColor=accent),shape=MaterialTheme.shapes.medium){Text("PC-Verwaltung starten")}}}}}}}

@Composable
fun ThemesScreen(vm:MainViewModel,accent:Color,isTv:Boolean){val u by vm.ui.collectAsState();val cat=u.themeCatalog?:return;BackHandler{vm.back()};Column(Modifier.fillMaxSize()){EpiTopBar("DESIGNS",R.drawable.brand_header,{vm.back()});LazyColumn(Modifier.fillMaxSize().padding(14.dp)){cat.groups.forEach{g->item{Text(g.label,color=accent,fontSize=20.sp,fontWeight=FontWeight.Bold,modifier=Modifier.padding(top=15.dp,bottom=8.dp))};items(g.themes){id->val t=cat.themes[id]?:return@items;FocusCard(t.label,if(id==u.themeId)"Aktiv" else "",vm.themeRepo().markRes(id),accent=color(t.accent),onClick={vm.selectTheme(id)},modifier=Modifier.fillMaxWidth().padding(bottom=8.dp))}}}}}

@Composable fun EmptyState(title:String,subtitle:String){Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center){GlassPanel(Modifier.fillMaxWidth(.82f).widthIn(max=620.dp)){Column(Modifier.padding(28.dp),horizontalAlignment=Alignment.CenterHorizontally){Text(title,fontSize=24.sp,fontWeight=FontWeight.Bold);Text(subtitle,color=Color.White.copy(.65f),modifier=Modifier.padding(top=8.dp))}}}}
@Composable fun LoadingOrError(loading:Boolean,error:String){if(loading)LinearProgressIndicator(Modifier.fillMaxWidth());if(error.isNotBlank())Text(error,color=Color(0xFFFF8A80),modifier=Modifier.padding(16.dp))}
private fun nowEvent(list:List<EpgItem>):EpgItem?{val n=System.currentTimeMillis()/1000;return list.firstOrNull{n>=it.start&&n<it.end}}
private fun clock(s:Long)=SimpleDateFormat("HH:mm",Locale.getDefault()).format(Date(s*1000))
private fun lang(c:String)=when(c){"de"->"Deutsch";"it"->"Italiano";"tr"->"Türkçe";"en"->"English";"none"->"Aus";else->c}
private fun nextAudio(c:String):String{val l=listOf("de","it","tr","en");val i=l.indexOf(c).coerceAtLeast(0);return l[(i+1)%l.size]}
private fun nextSub(c:String):String{val l=listOf("de","it","tr","en","none");val i=l.indexOf(c).coerceAtLeast(0);return l[(i+1)%l.size]}
