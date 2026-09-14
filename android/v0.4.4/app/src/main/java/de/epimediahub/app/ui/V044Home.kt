package de.epimediahub.app.ui

import androidx.compose.animation.core.Spring
import androidx.compose.animation.core.animateFloatAsState
import androidx.compose.animation.core.spring
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.shadow
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.ParityMediathekHome
import de.epimediahub.app.R
import de.epimediahub.app.Screen
import de.epimediahub.app.model.MediaKind
import kotlinx.coroutines.delay
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

private data class V044Tile(val title:String,val subtitle:String,val icon:Int,val open:()->Unit)

@Composable
fun V044HomeScreen(vm:MainViewModel,isTv:Boolean,accent:Color){
    val u by vm.ui.collectAsState()
    val repo=vm.themeRepo()
    val motifRes=remember(u.themeId){repo.homeMotifRes(u.themeId).takeIf{it!=0}?:repo.markRes(u.themeId)}
    val centerRes=remember(u.themeId){repo.centerMarkRes(u.themeId).takeIf{it!=0}?:repo.markRes(u.themeId)}
    val bannerRes=remember(u.themeId){repo.bannerMarkRes(u.themeId).takeIf{it!=0}?:repo.markRes(u.themeId)}
    val firstFocus=remember{FocusRequester()}
    var now by remember{mutableLongStateOf(System.currentTimeMillis())}
    LaunchedEffect(Unit){while(true){now=System.currentTimeMillis();delay(1000L)}}

    val tiles=listOf(
        V044Tile("LIVE TV","Sender · Voll-EPG · Catch-up",R.drawable.icon_live){vm.openLibrary(MediaKind.LIVE)},
        V044Tile("FILME","Kategorien · Details · Resume",R.drawable.icon_movies){vm.openLibrary(MediaKind.MOVIE)},
        V044Tile("SERIEN","Kategorien · Staffeln · Episoden",R.drawable.icon_series){vm.openLibrary(MediaKind.SERIES)},
        V044Tile("MEDIATHEK","Sender · Sendungen · Details",R.drawable.icon_mediathek){vm.navigate(ParityMediathekHome)},
        V044Tile("PLAYLISTS",if(u.playlists.size>1)"${u.playlists.size} Profile · wechseln" else "Verwalten · hinzufügen",R.drawable.icon_playlist){vm.navigate(Screen.Playlists)},
        V044Tile("EINSTELLUNGEN","Design · QR-Websetup · Update",R.drawable.icon_settings){vm.navigate(Screen.Settings)}
    )
    LaunchedEffect(isTv){if(isTv)runCatching{firstFocus.requestFocus()}}

    BoxWithConstraints(Modifier.fillMaxSize()){
        val compact=!isTv&&maxHeight<430.dp
        val headerHeight=when{isTv->176.dp;compact->82.dp;else->100.dp}
        val cols=if(isTv)2 else 3
        val rows=if(isTv)3 else 2
        val gap=if(isTv)13.dp else if(compact)6.dp else 9.dp
        Column(Modifier.fillMaxSize()){
            V044Header(u.active?.name?:"EpiMediaHub",isTv,compact,accent,bannerRes,now,Modifier.fillMaxWidth().height(headerHeight))
            Box(Modifier.weight(1f).fillMaxWidth().padding(start=if(isTv)48.dp else 8.dp,end=if(isTv)48.dp else 8.dp,top=2.dp,bottom=if(isTv)18.dp else 7.dp)){
                if(motifRes!=0) Image(painterResource(motifRes),null,Modifier.fillMaxSize().alpha(if(isTv).58f else .49f),contentScale=ContentScale.Crop)
                if(centerRes!=0) Image(painterResource(centerRes),null,Modifier.align(Alignment.Center).fillMaxHeight(.92f).fillMaxWidth(.55f).alpha(if(isTv).21f else .17f),contentScale=ContentScale.Fit)
                Column(Modifier.fillMaxSize(),verticalArrangement=Arrangement.spacedBy(gap)){
                    for(row in 0 until rows){
                        Row(Modifier.fillMaxWidth().weight(1f),horizontalArrangement=Arrangement.spacedBy(gap)){
                            for(col in 0 until cols){
                                val index=row*cols+col
                                val tile=tiles[index]
                                V044TileCard(tile.title,tile.subtitle,tile.icon,accent,isTv,compact,Modifier.weight(1f).fillMaxHeight().then(if(index==0)Modifier.focusRequester(firstFocus)else Modifier),tile.open)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun V044Header(playlist:String,isTv:Boolean,compact:Boolean,accent:Color,bannerRes:Int,now:Long,modifier:Modifier=Modifier){
    val time=remember(now/1000L){SimpleDateFormat("HH:mm",Locale.getDefault()).format(Date(now))}
    val date=remember(now/60000L){SimpleDateFormat("EEE, dd.MM.yyyy",Locale.GERMANY).format(Date(now))}
    Box(modifier.padding(horizontal=if(isTv)36.dp else 9.dp,vertical=if(compact)3.dp else 7.dp)){
        if(bannerRes!=0) Image(painterResource(bannerRes),null,Modifier.align(Alignment.CenterEnd).fillMaxHeight().width(if(isTv)470.dp else 275.dp).alpha(if(isTv).34f else .29f),contentScale=ContentScale.Fit)
        Image(painterResource(R.drawable.brand_header),"EpiMediaHub",Modifier.align(Alignment.TopStart).width(if(isTv)340.dp else if(compact)174.dp else 216.dp).height(if(isTv)118.dp else if(compact)62.dp else 76.dp),contentScale=ContentScale.Fit)
        Column(Modifier.align(Alignment.TopEnd).padding(top=if(compact)3.dp else 7.dp),horizontalAlignment=Alignment.End){
            Text(playlist,color=Color.White,fontSize=if(isTv)22.sp else if(compact)14.sp else 16.sp,fontWeight=FontWeight.Black,maxLines=1)
            Text(if(isTv)"ANDROID TV · 0.4.4" else "MOBILE · 0.4.4",color=Color.White.copy(.92f),fontSize=if(isTv)14.sp else 11.sp,fontWeight=FontWeight.SemiBold)
        }
        if(!compact||isTv){
            Column(Modifier.align(Alignment.BottomCenter).padding(bottom=if(isTv)10.dp else 3.dp),horizontalAlignment=Alignment.CenterHorizontally){
                Text(time,color=Color.White,fontSize=if(isTv)35.sp else 20.sp,fontWeight=FontWeight.Black)
                Text(date,color=Color.White.copy(.90f),fontSize=if(isTv)14.sp else 11.sp,fontWeight=FontWeight.Medium)
            }
        }
        Box(Modifier.align(Alignment.BottomCenter).fillMaxWidth().height(2.dp).background(Brush.horizontalGradient(listOf(Color.Transparent,accent.copy(.92f),Color.Transparent))))
    }
}

@Composable
private fun V044TileCard(title:String,subtitle:String,iconRes:Int,accent:Color,isTv:Boolean,compact:Boolean,modifier:Modifier=Modifier,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val scale by animateFloatAsState(if(focused)1.022f else 1f,spring(dampingRatio=Spring.DampingRatioNoBouncy,stiffness=Spring.StiffnessMedium),label="v044Scale")
    val shape=RoundedCornerShape(if(isTv)17.dp else 13.dp)
    Box(modifier.graphicsLayer{scaleX=scale;scaleY=scale}.shadow(if(focused)19.dp else 2.dp,shape).onFocusChanged{focused=it.isFocused}.focusable().clip(shape)
        .background(if(focused)Color(0xAA101620)else Color(0x69070D15))
        .border(if(focused)2.dp else 1.dp,if(focused)Color.White.copy(.38f)else Color.White.copy(.15f),shape).clickable(onClick=onClick)){
        Box(Modifier.align(Alignment.CenterStart).fillMaxHeight().width(if(focused)8.dp else 3.dp).background(if(focused)accent else accent.copy(.48f)))
        Image(painterResource(iconRes),null,Modifier.align(Alignment.CenterStart).padding(start=if(compact)11.dp else if(isTv)26.dp else 14.dp).size(if(compact)34.dp else if(isTv)64.dp else 43.dp),contentScale=ContentScale.Fit)
        Column(Modifier.align(Alignment.Center).fillMaxWidth().padding(start=if(isTv)106.dp else if(compact)55.dp else 66.dp,end=if(compact)7.dp else 13.dp),horizontalAlignment=Alignment.CenterHorizontally){
            Text(title,color=Color.White,fontSize=if(compact)14.sp else if(isTv)27.sp else 17.sp,fontWeight=FontWeight.Black,textAlign=TextAlign.Center,maxLines=1)
            if(!compact){Spacer(Modifier.height(if(isTv)5.dp else 2.dp));Text(subtitle,color=Color.White.copy(.94f),fontSize=if(isTv)14.sp else 11.sp,fontWeight=FontWeight.SemiBold,textAlign=TextAlign.Center,maxLines=2)}
        }
    }
}
