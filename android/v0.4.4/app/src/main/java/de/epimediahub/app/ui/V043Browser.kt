package de.epimediahub.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.focusable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ChevronRight
import androidx.compose.material3.Icon
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.focus.onFocusChanged
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun V043CategoryRow(title:String,accent:Color,onClick:()->Unit){
    var focused by remember{mutableStateOf(false)}
    val shape=RoundedCornerShape(14.dp)
    Row(
        Modifier.fillMaxWidth().heightIn(min=64.dp)
            .onFocusChanged{focused=it.isFocused}.focusable()
            .background(if(focused)Color(0xB5101620)else Color(0x85070D15),shape)
            .border(if(focused)2.dp else 1.dp,if(focused)Color.White.copy(.34f)else Color.White.copy(.13f),shape)
            .clickable(onClick=onClick),
        verticalAlignment=Alignment.CenterVertically
    ){
        Box(Modifier.fillMaxHeight().width(if(focused)7.dp else 3.dp).background(if(focused)accent else accent.copy(.46f)))
        Spacer(Modifier.width(16.dp))
        Text(title,color=Color.White,fontSize=19.sp,fontWeight=FontWeight.Black,modifier=Modifier.weight(1f),maxLines=2)
        Icon(Icons.Default.ChevronRight,null,tint=if(focused)accent else Color.White.copy(.80f),modifier=Modifier.padding(end=16.dp))
    }
}
