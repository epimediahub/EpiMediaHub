#!/usr/bin/env python3
from pathlib import Path
import os

root = Path(os.environ.get("PROJECT_ROOT", "."))
java = root / "app/src/main/java/de/epimediahub/app"


def replace_once(path: Path, old: str, new: str, label: str):
    text = path.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one anchor, found {count}")
    path.write_text(text.replace(old, new, 1))


gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 706', 'versionCode = 707', 'versionCode')
replace_once(gradle, 'versionName = "0.7.6"', 'versionName = "0.7.7"', 'versionName')

home = java / "ui/V070Home.kt"
home.write_text(home.read_text().replace("0.7.6", "0.7.7"))

weather = java / "data/V070WeatherClient.kt"
if weather.exists():
    weather.write_text(weather.read_text().replace("EpiMediaHub-Android/0.7.6", "EpiMediaHub-Android/0.7.7"))

screens = java / "ui/Screens.kt"
if screens.exists():
    screens.write_text(screens.read_text().replace("Android v0.7.6", "Android v0.7.7"))

setup = java / "data/SetupCodeProvisioning.kt"
s = setup.read_text()

old_result = 'sealed class DeviceSyncResult { data class Success(val changed:Boolean,val configVersion:Int,val playlistUrl:String?):DeviceSyncResult(); data class Error(val message:String):DeviceSyncResult() }'
new_result = 'sealed class DeviceSyncResult { data class Success(val changed:Boolean,val configVersion:Int,val playlistUrl:String?):DeviceSyncResult(); data object Revoked:DeviceSyncResult(); data class Error(val message:String):DeviceSyncResult() }'
if old_result not in s:
    raise SystemExit("DeviceSyncResult anchor missing")
s = s.replace(old_result, new_result, 1)

old_apply = ''' private fun applyConfigToApp(context:Context,config:JSONObject){
  val type=config.optString("playlist_type","").uppercase(Locale.ROOT)
  val name=config.optString("playlist_name","EpiMediaHub Dashboard").ifBlank{"EpiMediaHub Dashboard"}
  val url=config.optString("playlist_url","").trim()
  val server=config.optString("xtream_server","").trim().trimEnd('/')
  val username=config.optString("xtream_username","").trim()
  val password=config.optString("xtream_password","")
  val output=config.optString("xtream_output","ts").ifBlank{"ts"}
  val profile=runCatching {
   when {
    type=="XTREAM" && server.isNotBlank() && username.isNotBlank() && password.isNotBlank() ->
     PlaylistParser.fromXtream(name,server,username,password,output).copy(id="managed-dashboard")
    url.isNotBlank() -> PlaylistParser.parse(name,url).copy(id="managed-dashboard")
    else -> null
   }
  }.getOrNull() ?: return
  val repo=PrefsRepository(context)
  val local=repo.loadPlaylists().filterNot{it.id=="managed-dashboard"}
  repo.savePlaylists(listOf(profile)+local)
  repo.activePlaylistId=profile.id
 }
'''
new_apply = ''' private fun dashboardProfile(config:JSONObject,fallbackId:String):PlaylistProfile? {
  val type=config.optString("playlist_type","").uppercase(Locale.ROOT)
  val name=config.optString("playlist_name","EpiMediaHub Dashboard").ifBlank{"EpiMediaHub Dashboard"}
  val url=config.optString("playlist_url","").trim()
  val server=config.optString("xtream_server","").trim().trimEnd('/')
  val username=config.optString("xtream_username","").trim()
  val password=config.optString("xtream_password","")
  val output=config.optString("xtream_output","ts").ifBlank{"ts"}
  val remoteId=config.optString("id","").trim()
  val managedId=when {
   remoteId.startsWith("managed-dashboard") -> remoteId
   remoteId.isNotBlank() -> "managed-dashboard-$remoteId"
   else -> fallbackId
  }
  return runCatching {
   when {
    type=="XTREAM" && server.isNotBlank() && username.isNotBlank() && password.isNotBlank() ->
     PlaylistParser.fromXtream(name,server,username,password,output).copy(id=managedId)
    url.isNotBlank() -> PlaylistParser.parse(name,url).copy(id=managedId)
    else -> null
   }
  }.getOrNull()
 }

 private fun applyConfigToApp(context:Context,config:JSONObject){
  val managed=mutableListOf<PlaylistProfile>()
  val remote=config.optJSONArray("playlists")
  if(remote!=null){
   for(index in 0 until remote.length()){
    val item=remote.optJSONObject(index)?:continue
    dashboardProfile(item,"managed-dashboard-${index+1}")?.let{managed+=it}
   }
  } else {
   dashboardProfile(config,"managed-dashboard")?.let{managed+=it}
  }

  val repo=PrefsRepository(context)
  val existing=repo.loadPlaylists()
  val local=existing.filterNot{it.id=="managed-dashboard" || it.id.startsWith("managed-dashboard-")}
  repo.savePlaylists(managed+local)

  val current=repo.activePlaylistId
  if(current=="managed-dashboard" || current.startsWith("managed-dashboard-") || current.isBlank()){
   repo.activePlaylistId=managed.firstOrNull()?.id ?: local.firstOrNull()?.id.orEmpty()
  }
 }

 fun clearDeviceConfiguration(context:Context){
  context.getSharedPreferences(PREFS,Context.MODE_PRIVATE)
   .edit()
   .remove(KEY_PAYLOAD)
   .remove(KEY_BASE_URL)
   .remove(KEY_PAIRING)
   .commit()

  val repo=PrefsRepository(context)
  repo.savePlaylists(emptyList())
  repo.activePlaylistId=""
 }
'''
if old_apply not in s:
    raise SystemExit("applyConfigToApp anchor missing")
s = s.replace(old_apply, new_apply, 1)

old_status = '   if(status !in 200..299) return DeviceSyncResult.Error(if(status==401)"Gerät ist nicht mehr freigegeben" else "Sync-Serverfehler ($status)")\n'
new_status = '''   if(status==401 || status==403){
    clearDeviceConfiguration(context)
    return DeviceSyncResult.Revoked
   }
   if(status !in 200..299) return DeviceSyncResult.Error("Sync-Serverfehler ($status)")
'''
if old_status not in s:
    raise SystemExit("sync authorization anchor missing")
s = s.replace(old_status, new_status, 1)
setup.write_text(s)

app = java / "EpiMediaHubApp.kt"
s = app.read_text()

old_poll = '''            val sync = withContext(Dispatchers.IO) { SetupCodeProvisioning.sync(context.applicationContext) }
            if (sync is DeviceSyncResult.Success) vm.refreshProfiles()
            delay(30_000L)
'''
new_poll = '''            val sync = withContext(Dispatchers.IO) { SetupCodeProvisioning.sync(context.applicationContext) }
            when(sync){
                is DeviceSyncResult.Success -> vm.refreshProfiles()
                DeviceSyncResult.Revoked -> {
                    vm.refreshProfiles()
                    vm.navigate(Screen.WebAdmin)
                }
                is DeviceSyncResult.Error -> Unit
            }
            delay(30_000L)
'''
if old_poll not in s:
    raise SystemExit("dashboard polling anchor missing")
s = s.replace(old_poll, new_poll, 1)

context_anchor = '    val context = LocalContext.current\n'
if s.count(context_anchor) != 1:
    raise SystemExit(f"context anchor expected once, found {s.count(context_anchor)}")
startup = '''    var initialDashboardRedirectDone by remember { mutableStateOf(false) }
    LaunchedEffect(u.screen, u.playlists.size) {
        if (!initialDashboardRedirectDone &&
            SetupCodeProvisioning.sessionToken(context.applicationContext) == null
        ) {
            initialDashboardRedirectDone = true
            vm.navigate(Screen.WebAdmin)
        }
    }
'''
s = s.replace(context_anchor, context_anchor + startup, 1)
app.write_text(s)

checks = [
    (gradle, 'versionName = "0.7.7"'),
    (gradle, 'versionCode = 707'),
    (setup, 'data object Revoked'),
    (setup, 'config.optJSONArray("playlists")'),
    (setup, 'fun clearDeviceConfiguration(context:Context)'),
    (setup, 'repo.savePlaylists(emptyList())'),
    (setup, 'if(status==401 || status==403)'),
    (app, 'SetupCodeProvisioning.sessionToken(context.applicationContext) == null'),
    (app, 'vm.navigate(Screen.WebAdmin)'),
    (app, 'DeviceSyncResult.Revoked'),
]
for path, marker in checks:
    if marker not in path.read_text():
        raise SystemExit(f"missing v0.7.7 marker {marker} in {path}")

print("Android v0.7.7 mobile first-run pairing, full customer playlists and remote device wipe applied")
