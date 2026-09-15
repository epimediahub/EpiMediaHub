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

sealed class SetupCodeResult { data class Success(val payload: JSONObject):SetupCodeResult(); data class Error(val message:String):SetupCodeResult() }
object SetupCodeProvisioning {
 private const val PREFS="epimediahub_provisioning"; private const val KEY_PAYLOAD="provisioning_payload"
 fun normalize(raw:String)=raw.trim().uppercase(Locale.ROOT).replace(Regex("[^A-Z0-9]"),"").chunked(4).joinToString("-")
 fun isValid(code:String)=normalize(code).replace("-","").length in 8..16
 fun deviceId(context:Context):String = Settings.Secure.getString(context.contentResolver,Settings.Secure.ANDROID_ID)?.takeIf{it.isNotBlank()} ?: "android-unknown"
 private fun post(context:Context,baseUrl:String,path:String,key:String,value:String):SetupCodeResult {
  if(!baseUrl.startsWith("https://")) return SetupCodeResult.Error("Provisionierungsserver nicht sicher konfiguriert")
  return try {
   val conn=(URL(baseUrl.trimEnd('/')+path).openConnection() as HttpURLConnection).apply{requestMethod="POST";connectTimeout=10000;readTimeout=15000;doOutput=true;setRequestProperty("Content-Type","application/json; charset=utf-8");setRequestProperty("Accept","application/json")}
   val body=JSONObject().put(key,value).put("device_id",deviceId(context)).put("platform","android")
   conn.outputStream.use{it.write(body.toString().toByteArray(Charsets.UTF_8))}
   val status=conn.responseCode; val text=(if(status in 200..299)conn.inputStream else conn.errorStream)?.bufferedReader()?.use{it.readText()}.orEmpty()
   when(status){in 200..299->{val payload=JSONObject(text);context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().putString(KEY_PAYLOAD,payload.toString()).apply();SetupCodeResult.Success(payload)};404->SetupCodeResult.Error("Einrichtungscode ungültig");409->SetupCodeResult.Error("Einrichtung wurde bereits verwendet");410->SetupCodeResult.Error("Einrichtungscode ist abgelaufen");else->SetupCodeResult.Error("Serverfehler ($status)")}
  }catch(_:Exception){SetupCodeResult.Error("Provisionierungsserver nicht erreichbar")}
 }
 fun redeem(context:Context,baseUrl:String,rawCode:String):SetupCodeResult { val code=normalize(rawCode); if(!isValid(code))return SetupCodeResult.Error("Einrichtungscode ungültig"); return post(context,baseUrl,"/v1/setup/redeem","code",code) }
 fun redeemToken(context:Context,baseUrl:String,token:String):SetupCodeResult { if(token.isBlank())return SetupCodeResult.Error("Aktivierungslink ungültig"); return post(context,baseUrl,"/v1/setup/redeem-token","token",token) }
 fun savedPayload(context:Context):JSONObject?=context.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString(KEY_PAYLOAD,null)?.let{runCatching{JSONObject(it)}.getOrNull()}
 fun playlistUrl(context:Context):String?=savedPayload(context)?.optJSONObject("config")?.optString("playlist_url")?.takeIf{it.isNotBlank()}
 fun sessionToken(context:Context):String?=savedPayload(context)?.optString("session_token")?.takeIf{it.isNotBlank()}
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
print("Android v0.4.13 device-aware setup provisioning installed")
