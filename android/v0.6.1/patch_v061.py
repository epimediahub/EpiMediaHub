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


def replace_block(path: Path, start: str, end: str, new: str, label: str):
    text = path.read_text()
    if text.count(start) != 1 or text.count(end) < 1:
        raise SystemExit(f"{label}: block anchors missing")
    a = text.index(start)
    b = text.index(end, a)
    path.write_text(text[:a] + new + text[b:])


# Version metadata.
gradle = root / "app/build.gradle.kts"
replace_once(gradle, 'versionCode = 600', 'versionCode = 601', 'versionCode')
replace_once(gradle, 'versionName = "0.6.0"', 'versionName = "0.6.1"', 'versionName')
home = java / "ui/V044Home.kt"
home.write_text(home.read_text().replace("0.6.0", "0.6.1"))


# Dashboard/Raspberry profiles use the same normalization as manual Xtream entries.
parser = java / "data/PlaylistParser.kt"
replace_once(
    parser,
    '''            val path = uri.path.orEmpty()
            val suffix = when {
                path.endsWith("/get.php") -> "/get.php"
                path.endsWith("/player_api.php") -> "/player_api.php"
                else -> ""
            }
            val prefixPath = path.removeSuffix(suffix).trimEnd('/')
            val base = buildString {
                append(uri.scheme ?: "http").append("://").append(uri.encodedAuthority)
                if (prefixPath.isNotBlank()) append(prefixPath)
            }
''',
    '''            val base = normalizeXtreamServer(url)
''',
    'Xtream URL parsing',
)
replace_once(parser, 'val server = normalizeServer(rawServer)', 'val server = normalizeXtreamServer(rawServer)', 'manual server normalization')
replace_once(
    parser,
    '''    private fun normalizeServer(raw: String): String {
        var value = raw.trim().trimEnd('/')
        if (value.isBlank()) return ""
        if (!value.startsWith("http://", true) && !value.startsWith("https://", true)) value = "http://$value"
        val uri = Uri.parse(value)
        require(!uri.host.isNullOrBlank()) { "Portal / Domain ist ungültig." }
        return value
    }
''',
    '''    fun normalizeXtreamServer(raw: String): String {
        var value = raw.trim().trimEnd('/')
        if (value.isBlank()) return ""
        if (!value.startsWith("http://", true) && !value.startsWith("https://", true)) value = "http://$value"
        val uri = Uri.parse(value)
        require(!uri.host.isNullOrBlank()) { "Portal / Domain ist ungültig." }
        val endpoint = Regex("/(?i:get|player_api|panel_api|xmltv)\\.php$")
        val cleanPath = uri.path.orEmpty().replace(endpoint, "").trimEnd('/')
        return buildString {
            append(uri.scheme ?: "http").append("://").append(uri.encodedAuthority)
            if (cleanPath.isNotBlank()) append(cleanPath)
        }
    }
''',
    'normalized Xtream server helper',
)

provision = java / "data/SetupCodeProvisioning.kt"
replace_once(
    provision,
    '''  val profile=when {
   type=="XTREAM" && server.isNotBlank() && username.isNotBlank() && password.isNotBlank() -> PlaylistProfile("managed-dashboard",name,"",PlaylistType.XTREAM,server,username,password,output)
   url.isNotBlank() -> PlaylistProfile("managed-dashboard",name,url,PlaylistType.M3U)
   else -> null
  } ?: return
''',
    '''  val profile=runCatching {
   when {
    type=="XTREAM" && server.isNotBlank() && username.isNotBlank() && password.isNotBlank() ->
     PlaylistParser.fromXtream(name,server,username,password,output).copy(id="managed-dashboard")
    url.isNotBlank() -> PlaylistParser.parse(name,url).copy(id="managed-dashboard")
    else -> null
   }
  }.getOrNull() ?: return
''',
    'managed playlist parsing',
)


# Provider-compatible stream URL candidates and proper path escaping.
xtream = java / "data/XtreamClient.kt"
replace_once(xtream, 'import android.util.Base64\n', 'import android.util.Base64\nimport android.net.Uri\n', 'Xtream Uri import')
replace_once(
    xtream,
    '    private fun array(url: String) = JSONArray(text(url))\n',
    '''    private fun array(url: String) = JSONArray(text(url))

    private fun path(value: String) = Uri.encode(value)

    fun streamCandidates(item: MediaEntry): List<String> {
        val server = p.server.trimEnd('/')
        val user = path(p.username)
        val pass = path(p.password)
        val id = path(item.id)
        val configured = p.output.trim().trimStart('.').ifBlank { "ts" }
        val extension = item.extension.trim().trimStart('.').ifBlank { configured }
        val urls = mutableListOf<String>()
        if (item.streamUrl.isNotBlank()) urls += item.streamUrl
        when (item.kind) {
            MediaKind.LIVE -> {
                val extensions = listOf(configured, "ts", "m3u8").distinct()
                extensions.forEach { ext ->
                    urls += "$server/live/$user/$pass/$id.$ext"
                    urls += "$server/$user/$pass/$id.$ext"
                }
            }
            MediaKind.MOVIE -> urls += "$server/movie/$user/$pass/$id.$extension"
            MediaKind.EPISODE -> urls += "$server/series/$user/$pass/$id.$extension"
            else -> Unit
        }
        return urls.filter { it.isNotBlank() }.distinct()
    }
''',
    'stream candidate helper',
)
text = xtream.read_text()
text = text.replace('${p.server}/live/${enc(p.username)}/${enc(p.password)}/$id.${p.output}', '${p.server}/live/${path(p.username)}/${path(p.password)}/${path(id)}.${p.output.trimStart(\'.\')}')
text = text.replace('${p.server}/movie/${enc(p.username)}/${enc(p.password)}/$id.$ext', '${p.server}/movie/${path(p.username)}/${path(p.password)}/${path(id)}.$ext')
text = text.replace('${p.server}/series/${enc(p.username)}/${enc(p.password)}/$id.$ext', '${p.server}/series/${path(p.username)}/${path(p.password)}/${path(id)}.$ext')
if text.count('path(p.username)') < 4:
    raise SystemExit('Xtream stream URL replacements missing')
xtream.write_text(text)

vm = java / "MainViewModel.kt"
replace_once(
    vm,
    '    fun skipEpisode(current: MediaEntry, episodeList: List<MediaEntry>, direction: Int) {\n',
    '''    fun playbackUrls(item: MediaEntry): List<String> {
        val profile = _ui.value.active
        return if (profile?.type == PlaylistType.XTREAM) {
            XtreamClient(profile).streamCandidates(item)
        } else {
            listOf(item.streamUrl).filter { it.isNotBlank() }
        }
    }

    fun skipEpisode(current: MediaEntry, episodeList: List<MediaEntry>, direction: Int) {
''',
    'playback candidates view model',
)

player = java / "ui/PlayerScreen.kt"
replace_once(player, 'import androidx.media3.common.MediaItem\n', 'import androidx.media3.common.MediaItem\nimport androidx.media3.common.PlaybackException\n', 'playback exception import')
replace_once(
    player,
    '''    val player = remember(item.id) { ExoPlayer.Builder(context).build() }
    var controls by remember { mutableStateOf(true) }
''',
    '''    val player = remember(item.id) { ExoPlayer.Builder(context).build() }
    val playbackUrls = remember(item.resumeKey, item.streamUrl, u.active?.id) { vm.playbackUrls(item) }
    var controls by remember { mutableStateOf(true) }
    var playbackError by remember(item.resumeKey) { mutableStateOf("") }
''',
    'player candidate state',
)
replace_once(
    player,
    '''        player.trackSelectionParameters = params
        player.setMediaItem(MediaItem.fromUri(item.streamUrl))
        player.prepare()
        val resume = vm.resume(item)
        if (resume > 10_000 && item.kind != MediaKind.LIVE) player.seekTo(resume)
        player.playWhenReady = true
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) save()
            }
        }
''',
    '''        player.trackSelectionParameters = params
        var activeUrl = 0
        fun openUrl(index: Int) {
            activeUrl = index
            playbackError = ""
            player.setMediaItem(MediaItem.fromUri(playbackUrls[index]))
            player.prepare()
            player.playWhenReady = true
        }
        if (playbackUrls.isNotEmpty()) openUrl(0)
        else playbackError = "Für diesen Eintrag wurde keine Stream-Adresse geliefert."
        val resume = vm.resume(item)
        if (resume > 10_000 && item.kind != MediaKind.LIVE) player.seekTo(resume)
        val listener = object : Player.Listener {
            override fun onPlaybackStateChanged(state: Int) {
                if (state == Player.STATE_ENDED) save()
            }
            override fun onPlayerError(error: PlaybackException) {
                val next = activeUrl + 1
                if (next < playbackUrls.size) {
                    openUrl(next)
                } else {
                    playbackError = "Der Anbieter hat alle kompatiblen Stream-Adressen abgelehnt (${error.errorCodeName})."
                }
            }
        }
''',
    'player automatic fallback',
)
replace_once(
    player,
    '''        }

    }
}
''',
    '''        }

        if (playbackError.isNotBlank()) {
            Surface(
                modifier = Modifier.align(Alignment.BottomCenter).padding(24.dp),
                color = Color(0xE8151A22),
                shape = MaterialTheme.shapes.medium,
                border = androidx.compose.foundation.BorderStroke(1.dp, accent)
            ) {
                Text(playbackError, color = Color.White, modifier = Modifier.padding(horizontal = 18.dp, vertical = 13.dp))
            }
        }

    }
}
''',
    'player error panel',
)


# Prominent station banners; logos fall back to channel initials if the provider image fails.
rows = java / "ui/BrowserRows.kt"
text = rows.read_text()
text = text.replace('import androidx.compose.foundation.Image\n', '')
text = text.replace('import androidx.compose.ui.draw.alpha\n', '')
text = text.replace('import androidx.compose.ui.res.painterResource\n', '')
text = text.replace('import coil.compose.AsyncImage\n', 'import coil.compose.AsyncImage\nimport coil.compose.AsyncImagePainter\nimport coil.compose.SubcomposeAsyncImage\nimport coil.compose.SubcomposeAsyncImageContent\n')
rows.write_text(text)
live = r'''@Composable
fun LiveChannelRow(
    media: MediaEntry,
    nowText: String,
    accent: Color,
    modifier: Modifier = Modifier,
    isTv: Boolean = false,
    onClick: () -> Unit
) {
    var focused by remember { mutableStateOf(false) }
    val scale by animateFloatAsState(if (focused) 1.045f else 1f, spring(stiffness = 390f), label = "liveBannerFocus")
    val shape = RoundedCornerShape(if (isTv) 18.dp else 14.dp)
    val initials = remember(media.name) {
        media.name.split(Regex("\\s+")).filter { it.isNotBlank() }.take(2)
            .joinToString("") { it.take(1).uppercase() }.ifBlank { "TV" }
    }
    Surface(
        modifier = modifier.fillMaxWidth().graphicsLayer { scaleX = scale; scaleY = scale }
            .shadow(if (focused) 26.dp else 3.dp, shape)
            .onFocusChanged { focused = it.isFocused }.focusable().clickable(onClick = onClick),
        color = Color.Transparent,
        contentColor = Color.White,
        shape = shape,
        border = androidx.compose.foundation.BorderStroke(if (focused) 3.dp else 1.dp, if (focused) accent else Color.White.copy(.14f))
    ) {
        Box(
            Modifier.fillMaxWidth().height(if (isTv) 108.dp else 86.dp)
                .background(Brush.horizontalGradient(listOf(accent.copy(if (focused) .32f else .18f), Color(0xF20B1420), Color(0xFA070B12))))
        ) {
            Box(Modifier.align(Alignment.CenterStart).fillMaxHeight().width(if (focused) 8.dp else 4.dp).background(accent))
            Row(Modifier.fillMaxSize().padding(start = if (isTv) 20.dp else 14.dp, end = 20.dp, top = 10.dp, bottom = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                Surface(
                    shape = RoundedCornerShape(13.dp),
                    color = Color.White.copy(.95f),
                    modifier = Modifier.width(if (isTv) 154.dp else 112.dp).fillMaxHeight()
                ) {
                    if (media.image.isNotBlank()) {
                        SubcomposeAsyncImage(
                            model = media.image,
                            contentDescription = media.name,
                            modifier = Modifier.fillMaxSize().padding(if (isTv) 10.dp else 8.dp),
                            contentScale = ContentScale.Fit
                        ) {
                            if (painter.state is AsyncImagePainter.State.Success) SubcomposeAsyncImageContent()
                            else Box(Modifier.fillMaxSize().background(accent.copy(.13f)), contentAlignment = Alignment.Center) {
                                Text(initials, color = accent, fontSize = if (isTv) 26.sp else 20.sp, fontWeight = FontWeight.Black)
                            }
                        }
                    } else {
                        Box(Modifier.fillMaxSize().background(accent.copy(.13f)), contentAlignment = Alignment.Center) {
                            Text(initials, color = accent, fontSize = if (isTv) 26.sp else 20.sp, fontWeight = FontWeight.Black)
                        }
                    }
                }
                Spacer(Modifier.width(if (isTv) 22.dp else 14.dp))
                Column(Modifier.weight(1f)) {
                    Text(media.name, color = Color.White, fontSize = if (isTv) 23.sp else 18.sp, fontWeight = FontWeight.Black, maxLines = 1)
                    Text(if (nowText.isNotBlank()) nowText else "Jetzt live", color = if (focused) Color.White else Color.White.copy(.75f), fontSize = if (isTv) 14.sp else 12.sp, maxLines = 2, modifier = Modifier.padding(top = 5.dp))
                }
                Text(if (focused) "OK · ÖFFNEN" else "LIVE", color = if (focused) accent else Color.White.copy(.62f), fontSize = 12.sp, fontWeight = FontWeight.Black)
                Spacer(Modifier.width(8.dp))
                Icon(Icons.Default.PlayArrow, null, tint = if (focused) accent else Color.White.copy(.55f), modifier = Modifier.size(31.dp))
            }
        }
    }
}

'''
replace_block(rows, '@Composable\nfun LiveChannelRow(', '@Composable\nfun MediaInfoRow(', live, 'live channel banner')

screens = java / "ui/Screens.kt"
replace_once(screens, '    val liveBannerRes=remember(u.themeId){vm.themeRepo().bannerMarkRes(u.themeId).takeIf{it!=0}?:vm.themeRepo().markRes(u.themeId)}\n', '', 'old live skin mark')
text = screens.read_text()
text = text.replace(',accent,skinMarkRes=liveBannerRes,isTv=true){', ',accent,isTv=true){')
text = text.replace(',accent,skinMarkRes=liveBannerRes,isTv=false){', ',accent,isTv=false){')
if 'skinMarkRes=liveBannerRes' in text:
    raise SystemExit('old live banner calls remain')
screens.write_text(text)


# Keep only the theme artwork that is already part of the background image.
common = java / "ui/Common.kt"
replace_once(common, '        val center = remember(themeId) { repo.centerMarkRes(themeId).takeIf { it != 0 } ?: repo.markRes(themeId) }\n        val banner = remember(themeId) { repo.bannerMarkRes(themeId).takeIf { it != 0 } ?: repo.markRes(themeId) }\n', '', 'duplicate backdrop resources')
replace_once(
    common,
    '''            if (center != 0) {
                Image(
                    painterResource(center), null,
                    Modifier.align(Alignment.CenterEnd).fillMaxHeight(.82f).fillMaxWidth(.52f).graphicsLayer { alpha = .15f },
                    contentScale = ContentScale.Fit
                )
            }
            if (banner != 0) {
                Image(
                    painterResource(banner), null,
                    Modifier.align(Alignment.TopEnd).fillMaxWidth(.40f).heightIn(max = 190.dp).graphicsLayer { alpha = .11f },
                    contentScale = ContentScale.Fit
                )
            }
''',
    '',
    'duplicate backdrop images',
)

home = java / "ui/V044Home.kt"
replace_once(
    home,
    '''    val repo=vm.themeRepo()
    val motifRes=remember(u.themeId){repo.homeMotifRes(u.themeId).takeIf{it!=0}?:repo.markRes(u.themeId)}
    val centerRes=remember(u.themeId){repo.centerMarkRes(u.themeId).takeIf{it!=0}?:repo.markRes(u.themeId)}
    val bannerRes=remember(u.themeId){repo.bannerMarkRes(u.themeId).takeIf{it!=0}?:repo.markRes(u.themeId)}
''',
    '',
    'duplicate home resources',
)
text = home.read_text()
text = text.replace('accent,bannerRes,now,', 'accent,now,')
text = text.replace('    val time=', '    val time=', 1)
text = text.replace('private fun V044Header(playlist:String,isTv:Boolean,compact:Boolean,accent:Color,bannerRes:Int,now:Long,modifier:Modifier=Modifier){', 'private fun V044Header(playlist:String,isTv:Boolean,compact:Boolean,accent:Color,now:Long,modifier:Modifier=Modifier){')
for line in [
    '                if(motifRes!=0) Image(painterResource(motifRes),null,Modifier.fillMaxSize().alpha(if(isTv).58f else .49f),contentScale=ContentScale.Crop)\n',
    '                if(centerRes!=0) Image(painterResource(centerRes),null,Modifier.align(Alignment.Center).fillMaxHeight(.92f).fillMaxWidth(.55f).alpha(if(isTv).21f else .17f),contentScale=ContentScale.Fit)\n',
    '        if(bannerRes!=0) Image(painterResource(bannerRes),null,Modifier.align(Alignment.CenterEnd).fillMaxHeight().width(if(isTv)470.dp else 275.dp).alpha(if(isTv).34f else .29f),contentScale=ContentScale.Fit)\n',
]:
    if line not in text:
        raise SystemExit('duplicate home image anchor missing')
    text = text.replace(line, '', 1)
home.write_text(text)


# Explicit home-screen exit dialog and shutdown of active background components.
updates = java / "data/UpdateManager.kt"
replace_once(
    updates,
    '    fun pending(context: Context): AppUpdateInfo? {\n',
    '''    fun cancelScheduled(context: Context) {
        WorkManager.getInstance(context.applicationContext).cancelUniqueWork(WORK_NAME)
    }

    fun pending(context: Context): AppUpdateInfo? {
''',
    'cancel update worker',
)

app = java / "EpiMediaHubApp.kt"
replace_once(app, 'package de.epimediahub.app\n\n', 'package de.epimediahub.app\n\nimport android.app.Activity\n', 'Activity import')
replace_once(app, '    var updateError by remember { mutableStateOf<String?>(null) }\n', '    var updateError by remember { mutableStateOf<String?>(null) }\n    var showExitDialog by remember { mutableStateOf(false) }\n', 'exit dialog state')
replace_once(app, '    BackHandler(enabled = hasInternalBackTarget) { vm.back() }\n', '    BackHandler(enabled = hasInternalBackTarget) { vm.back() }\n    BackHandler(enabled = u.screen == Screen.Home) { showExitDialog = true }\n', 'home back handler')
replace_once(
    app,
    '''        updateError?.let { message ->
            AlertDialog(
                onDismissRequest = { updateError = null },
                title = { Text("Update fehlgeschlagen") },
                text = { Text(message) },
                confirmButton = {
                    TextButton(onClick = { updateError = null }) { Text("OK") }
                }
            )
        }
''',
    '''        updateError?.let { message ->
            AlertDialog(
                onDismissRequest = { updateError = null },
                title = { Text("Update fehlgeschlagen") },
                text = { Text(message) },
                confirmButton = {
                    TextButton(onClick = { updateError = null }) { Text("OK") }
                }
            )
        }

        if (showExitDialog) {
            AlertDialog(
                onDismissRequest = { showExitDialog = false },
                title = { Text("EpiMediaHub beenden?", fontWeight = FontWeight.Bold) },
                text = { Text("Die Wiedergabe, Fernwartung und Hintergrundaufgaben werden beendet.") },
                confirmButton = {
                    TextButton(onClick = {
                        showExitDialog = false
                        vm.stopWebAdmin()
                        RemoteTailscaleManager.disconnect()
                        AppUpdateManager.cancelScheduled(context.applicationContext)
                        (context as? Activity)?.finishAndRemoveTask()
                    }) { Text("Beenden") }
                },
                dismissButton = {
                    TextButton(onClick = { showExitDialog = false }) { Text("Abbrechen") }
                }
            )
        }
''',
    'exit dialog',
)

print("Android v0.6.1 live/playback/skin patch applied")
