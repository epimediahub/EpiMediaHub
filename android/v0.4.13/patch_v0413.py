#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"
gradle = root / "app/build.gradle.kts"
s = gradle.read_text()
if 'versionCode = 52' not in s or 'versionName = "0.4.12"' not in s: raise SystemExit("v0.4.12 version anchors missing")
gradle.write_text(s.replace('versionCode = 52','versionCode = 53',1).replace('versionName = "0.4.12"','versionName = "0.4.13"',1))
for rel in ["ui/V044Home.kt","ui/Screens.kt","data/MediathekClient.kt"]:
    p=java/rel
    if p.exists(): p.write_text(p.read_text().replace("0.4.12","0.4.13"))

(java/"data/SetupCodeProvisioning.kt").write_text(r'''package de.epimediahub.app.data

import android.content.Context
import android.provider.Settings
import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL
import java.util.Locale
import java.util.UUID

sealed class SetupCodeResult { data class Success(val payload: JSONObject):SetupCodeResult(); data class Error(val message:String):SetupCodeResult() }
sealed class DeviceSyncResult { data class Success(val changed:Boolean,val configVersion:Int,val playlistUrl:String?):DeviceSyncResult(); data class Error(val message:String):DeviceSyncResult() }
object SetupCodeProvisioning {
 private const val PREFS="epimediahub_provisioning"; private const val KEY_PAYLOAD="provisioning_payload"; private const val KEY_DEVICE_ID="stable_device_id"; private const val KEY_BASE_URL="provisioning_base_url"
 fun normalize(raw:String)=raw.trim().uppercase(Locale.ROOT).replace(Regex("[^A-Z0-9]"),"").chunked(4).joinToString("-")
 fun isValid(code:String)=normalize(code).replace("-","").length in 8..16
 fun deviceId(context:Context):String {
  val androidId=Settings.Secure.getString(context.contentResolver,Settings.Secure.ANDROID_ID)?.trim().orEmpty()
  if(androidId.isNotBlank() && androidId.lowercase(Locale.ROOT)!="9774d56d682e549c") return "android-$androidId"
  val prefs=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE)
  prefs.getString(KEY_DEVICE_ID,null)?.takeIf{it.isNotBlank()}?.let{return it}
  val generated="android-"+UUID.randomUUID().toString()
  prefs.edit().putString(KEY_DEVICE_ID,generated).commit()
  return generated
 }
 private fun connection(url:String,method:String,sessionToken:String?=null)= (URL(url).openConnection() as HttpURLConnection).apply{
  requestMethod=method;connectTimeout=10000;readTimeout=15000;setRequestProperty("Accept","application/json")
  if(method=="POST"){doOutput=true;setRequestProperty("Content-Type","application/json; charset=utf-8")}
  if(!sessionToken.isNullOrBlank())setRequestProperty("Authorization","Bearer $sessionToken")
 }
 private fun read(conn:HttpURLConnection,status:Int)= (if(status in 200..299)conn.inputStream else conn.errorStream)?.bufferedReader()?.use{it.readText()}.orEmpty()
 private fun post(context:Context,baseUrl:String,path:String,key:String,value:String):SetupCodeResult {
  if(!baseUrl.startsWith("https://") && !baseUrl.startsWith("http://100.")) return SetupCodeResult.Error("Provisionierungsserver nicht sicher konfiguriert")
  return try {
   val cleanBase=baseUrl.trimEnd('/'); val conn=connection(cleanBase+path,"POST")
   val body=JSONObject().put(key,value).put("device_id",deviceId(context)).put("platform","android")
   conn.outputStream.use{it.write(body.toString().toByteArray(Charsets.UTF_8))}
   val status=conn.responseCode; val text=read(conn,status)
   when(status){in 200..299->{val payload=JSONObject(text);context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_PAYLOAD,payload.toString()).putString(KEY_BASE_URL,cleanBase).apply();SetupCodeResult.Success(payload)};404->SetupCodeResult.Error("Einrichtungscode ungültig");409->SetupCodeResult.Error("Einrichtung wurde bereits verwendet");410->SetupCodeResult.Error("Einrichtungscode ist abgelaufen");else->SetupCodeResult.Error("Serverfehler ($status)")}
  }catch(_:Exception){SetupCodeResult.Error("Provisionierungsserver nicht erreichbar")}
 }
 fun redeem(context:Context,baseUrl:String,rawCode:String):SetupCodeResult { val code=normalize(rawCode); if(!isValid(code))return SetupCodeResult.Error("Einrichtungscode ungültig"); return post(context,baseUrl,"/v1/setup/redeem","code",code) }
 fun redeemToken(context:Context,baseUrl:String,token:String):SetupCodeResult { if(token.isBlank())return SetupCodeResult.Error("Aktivierungslink ungültig"); return post(context,baseUrl,"/v1/setup/redeem-token","token",token) }
 fun savedPayload(context:Context):JSONObject?=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(KEY_PAYLOAD,null)?.let{runCatching{JSONObject(it)}.getOrNull()}
 fun playlistUrl(context:Context):String?=savedPayload(context)?.optJSONObject("config")?.optString("playlist_url")?.takeIf{it.isNotBlank()}
 fun sessionToken(context:Context):String?=savedPayload(context)?.optString("session_token")?.takeIf{it.isNotBlank()}
 fun provisioningBaseUrl(context:Context):String?=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(KEY_BASE_URL,null)?.takeIf{it.isNotBlank()}
 fun configVersion(context:Context):Int=savedPayload(context)?.optInt("config_version",0)?:0
 fun sync(context:Context):DeviceSyncResult {
  val base=provisioningBaseUrl(context)?:return DeviceSyncResult.Error("Gerät ist noch nicht eingerichtet")
  val token=sessionToken(context)?:return DeviceSyncResult.Error("Geräteschlüssel fehlt")
  return try {
   val conn=connection(base.trimEnd('/')+"/v1/device/config","GET",token); val status=conn.responseCode; val text=read(conn,status)
   if(status !in 200..299) return DeviceSyncResult.Error(if(status==401)"Gerät ist nicht mehr freigegeben" else "Sync-Serverfehler ($status)")
   val remote=JSONObject(text); val version=remote.optInt("config_version",0); val changed=remote.optBoolean("changed",false); val config=remote.optJSONObject("config")?:JSONObject(); val playlist=config.optString("playlist_url").takeIf{it.isNotBlank()}
   val old=savedPayload(context)?:JSONObject(); val merged=JSONObject(old.toString()).put("config_version",version).put("config",config)
   context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_PAYLOAD,merged.toString()).commit()
   reportSync(context,base,token,version,"ok","")
   DeviceSyncResult.Success(changed,version,playlist)
  }catch(e:Exception){DeviceSyncResult.Error(e.message?:"Synchronisierung fehlgeschlagen")}
 }
 private fun reportSync(context:Context,base:String,token:String,version:Int,statusValue:String,error:String){
  try{val conn=connection(base.trimEnd('/')+"/v1/device/sync-result","POST",token);val body=JSONObject().put("config_version",version).put("status",statusValue).put("error",error);conn.outputStream.use{it.write(body.toString().toByteArray(Charsets.UTF_8))};conn.responseCode;conn.disconnect()}catch(_:Exception){}
 }
}
''')

(java/"ui/SetupCodeLogin.kt").write_text(r'''package de.epimediahub.app.ui
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.unit.dp
import de.epimediahub.app.data.*
import kotlinx.coroutines.*
@Composable fun SetupCodeLogin(provisioningBaseUrl:String,onProvisioned:()->Unit,modifier:Modifier=Modifier){val context=LocalContext.current;val scope=rememberCoroutineScope();var code by remember{mutableStateOf("")};var error by remember{mutableStateOf<String?>(null)};var busy by remember{mutableStateOf(false)};Column(modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(10.dp)){Text("Oder mit Einrichtungscode anmelden",style=MaterialTheme.typography.titleMedium);OutlinedTextField(value=code,onValueChange={code=SetupCodeProvisioning.normalize(it);error=null},label={Text("Einrichtungscode")},placeholder={Text("z. B. EPI7-K4M9-2ABC")},singleLine=true,enabled=!busy,modifier=Modifier.fillMaxWidth());Button(enabled=!busy&&SetupCodeProvisioning.isValid(code),modifier=Modifier.fillMaxWidth(),onClick={busy=true;error=null;scope.launch{val r=withContext(Dispatchers.IO){SetupCodeProvisioning.redeem(context,provisioningBaseUrl,code)};busy=false;when(r){is SetupCodeResult.Success->onProvisioned();is SetupCodeResult.Error->error=r.message}}}){Text(if(busy)"Wird eingerichtet …" else "Mit Einrichtungscode anmelden")};error?.let{Text(it,color=MaterialTheme.colorScheme.error)}}}
''')
print("Android v0.4.13 setup provisioning and device config sync installed")
