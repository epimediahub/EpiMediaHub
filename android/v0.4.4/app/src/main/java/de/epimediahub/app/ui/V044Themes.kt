package de.epimediahub.app.ui

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import de.epimediahub.app.MainViewModel
import de.epimediahub.app.R

@Composable
fun V044ThemesScreen(vm:MainViewModel,accent:Color,isTv:Boolean){
    val u by vm.ui.collectAsState()
    val cat=u.themeCatalog?:return
    BackHandler{vm.back()}
    Column(Modifier.fillMaxSize()){
        EpiTopBar("DESIGNS",R.drawable.brand_header,{vm.back()},actions={
            Text("Skin wird sofort angewendet",color=Color.White.copy(.90f),fontSize=12.sp,fontWeight=FontWeight.SemiBold)
        })
        LazyColumn(
            Modifier.fillMaxSize().padding(horizontal=if(isTv)46.dp else 12.dp,vertical=4.dp),
            contentPadding=PaddingValues(bottom=28.dp),
            verticalArrangement=Arrangement.spacedBy(10.dp)
        ){
            cat.groups.forEach{group->
                item(key="group:${group.id}"){
                    Text(group.label,color=accent,fontSize=20.sp,fontWeight=FontWeight.Black,modifier=Modifier.padding(top=14.dp,bottom=2.dp))
                }
                items(group.themes,key={it}){id->
                    val theme=cat.themes[id]?:return@items
                    V044ThemePreview(
                        title=theme.label,
                        active=id==u.themeId,
                        accent=color(theme.accent),
                        backgroundRes=vm.themeRepo().backgroundRes(id),
                        motifRes=vm.themeRepo().homeMotifRes(id).takeIf{it!=0}?:vm.themeRepo().markRes(id),
                        onClick={vm.selectTheme(id)}
                    )
                }
            }
        }
    }
}

@Composable
private fun V044ThemePreview(title:String,active:Boolean,accent:Color,backgroundRes:Int,motifRes:Int,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val shape=RoundedCornerShape(18.dp)
    Box(
        Modifier.fillMaxWidth().height(126.dp)
            .onFocusChanged{focused=it.isFocused}.focusable().clip(shape)
            .background(Color(0xA8070D15))
            .border(if(active||focused)2.dp else 1.dp,if(active||focused)accent else Color.White.copy(.14f),shape)
            .clickable(onClick=onClick)
    ){
        if(backgroundRes!=0){
            Image(painterResource(backgroundRes),null,Modifier.fillMaxSize(),contentScale=ContentScale.Crop)
        }
        Box(Modifier.fillMaxSize().background(Brush.horizontalGradient(listOf(Color.Black.copy(.30f),Color.Black.copy(.10f),Color.Black.copy(.62f)))))
        if(motifRes!=0){
            Image(painterResource(motifRes),null,Modifier.align(Alignment.CenterEnd).fillMaxHeight().fillMaxWidth(.60f),contentScale=ContentScale.Fit)
        }
        Box(Modifier.align(Alignment.CenterStart).fillMaxHeight().width(if(active||focused)8.dp else 3.dp).background(if(active||focused)accent else accent.copy(.48f)))
        Column(Modifier.align(Alignment.CenterStart).padding(start=24.dp,end=16.dp)){
            Text(title,color=Color.White,fontSize=21.sp,fontWeight=FontWeight.Black,maxLines=1)
            Spacer(Modifier.height(5.dp))
            Text(if(active)"AKTIV · angewendet" else "Antippen zum Anwenden",color=if(active)accent else Color.White.copy(.90f),fontSize=13.sp,fontWeight=FontWeight.Bold)
        }
    }
}
