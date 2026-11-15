#!/usr/bin/env python3
"""Upper-body-only windows, era badges and the active provider account expiry."""
import os, shutil
from pathlib import Path
root=Path(os.environ['PROJECT_ROOT']);here=Path(__file__).resolve().parent
java=root/'app/src/main/java/de/epimediahub/app'
def replace(path,old,new,count=1):
    text=path.read_text();assert text.count(old)==count,f'{path}: expected {count} anchors for {old[:90]}'
    path.write_text(text.replace(old,new))
replace(root/'app/build.gradle.kts','versionCode = 1031','versionCode = 1032')
replace(root/'app/build.gradle.kts','versionName = "1.0.31"','versionName = "1.0.32"')
for path in java.rglob('*.kt'):
    text=path.read_text()
    if '1.0.31' in text:path.write_text(text.replace('1.0.31','1.0.32'))
for path in here.glob('V132*.kt'):
    if path.name.endswith('Test.kt'):
        dest=root/'app/src/test/java/de/epimediahub/app'/('data'if 'ExpiryTest'in path.name else 'ui')
    else:dest=java/('data'if path.name=='V132PlaylistExpiry.kt'else 'ui')
    dest.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest/path.name)
art=java/'ui/V131SkinArtwork.kt'
replace(art,'import androidx.compose.ui.draw.clip','import androidx.compose.ui.draw.clip\nimport androidx.compose.ui.draw.clipToBounds\nimport androidx.compose.ui.platform.testTag')
replace(art,'import coil.ImageLoader','import coil.ImageLoader\nimport coil.request.ImageRequest\nimport coil.size.Size\nimport androidx.compose.runtime.remember')
replace(art,'.maxSizeBytes(8 * 1024 * 1024)','.maxSizeBytes(12 * 1024 * 1024)')
replace(art,'internal data class V131Portrait(val name: String, val asset: String, val transparent: Boolean)',
    'internal data class V131Portrait(val name: String, val asset: String, val transparent: Boolean, val window: V132PortraitWindow = V132PortraitWindow())')
replace(art,'V131Portrait(portrait.getString("name"), portrait.getString("asset"), portrait.optBoolean("transparent"))',
    '''val crop = portrait.optJSONArray("window")
                                val window = if (crop != null && crop.length() == 4) V132PortraitWindow(
                                    crop.getDouble(0).toFloat(), crop.getDouble(1).toFloat(),
                                    crop.getDouble(2).toFloat(), crop.getDouble(3).toFloat(), portrait.optDouble("aspectRatio", .7).toFloat()) else V132PortraitWindow()
                                V131Portrait(portrait.getString("name"), portrait.getString("asset"), portrait.optBoolean("transparent"), window)''')
s=art.read_text();start=s.index('    Box(modifier.fillMaxSize()) {');end=s.index('        if (!preview) {',start)
s=s[:start]+'''    BoxWithConstraints(modifier.fillMaxSize()) {
        val portraitHeight = maxHeight * if (preview) .86f else .59f
        val portraitTop = maxHeight * if (preview) .05f else if (maxWidth > maxHeight) .16f else .13f
        variant.portraits.take(2).forEachIndexed { index, portrait ->
            val inset = if (preview) 6.dp else 16.dp
            val availableWidth = (maxWidth * if (preview) .36f else .28f) - inset * 2
            val displayHeight = minOf(portraitHeight, availableWidth / portrait.window.aspectRatio)
            val displayWidth = displayHeight * portrait.window.aspectRatio
            val request = remember(context, portrait.asset) {
                ImageRequest.Builder(context).data("file:///android_asset/" + portrait.asset).size(Size.ORIGINAL).build()
            }
            AsyncImage(request, null, imageLoader = loader,
                contentScale = portrait.window.scale, alignment = portrait.window.alignment,
                modifier = Modifier.align(if (index == 0) Alignment.TopStart else Alignment.TopEnd)
                    .offset(x = if (index == 0) inset else -inset, y = portraitTop)
                    .width(displayWidth).height(displayHeight)
                    .testTag("portrait-" + themeId + "-" + index).clipToBounds()
                    .graphicsLayer { alpha = .96f })
        }
''' + s[end:];art.write_text(s)
repo=java/'data/ThemeRepository.kt'
replace(repo,'    fun officialMarkRes(id: String): Int = drawable("official_${safe(V131BaseTheme(id))}")',
    '''    fun officialMarkRes(id: String): Int {
        if (id.endsWith("__legends")) {
            val historical = drawable("historical_${safe(V131BaseTheme(id))}")
            if (historical != 0) return historical
        }
        return drawable("official_${safe(V131BaseTheme(id))}")
    }''')
replace(java/'ui/V131TeamCarousel.kt','officialMarkRes(team.id)','officialMarkRes(variant.id)')
home=java/'ui/V083Home.kt'
replace(home,'import de.epimediahub.app.model.MediaKind','import de.epimediahub.app.model.MediaKind\nimport de.epimediahub.app.data.V132PlaylistExpiry\nimport androidx.compose.ui.text.style.TextOverflow\nimport androidx.compose.ui.platform.testTag')
replace(home,'    val u by vm.ui.collectAsState()\n    val context = LocalContext.current',
    '    val u by vm.ui.collectAsState()\n    val context = LocalContext.current\n    val expiry = v132RememberPlaylistExpiry(u.active, System.currentTimeMillis())')
replace(home,'''            isTv -> 176.dp
            compact -> 94.dp
            else -> 102.dp''','''            isTv -> maxHeight * .36f
            compact -> maxHeight * .33f
            else -> maxHeight * .27f''')
replace(home,'                playlist = u.active?.name ?: "EpiMediaHub",','                playlist = u.active?.name ?: "EpiMediaHub",\n                expiry = expiry,')
replace(home,'    playlist: String,','    playlist: String,\n    expiry: V132PlaylistExpiry,')
replace(home,'''                playlist,
                color = Color.White,''','''                playlist,
                modifier = Modifier.widthIn(max = if (isTv) 280.dp else if (compact) 164.dp else 180.dp),
                overflow = TextOverflow.Ellipsis,
                color = Color.White,''')
replace(home,'.padding(top = if (isTv) 10.dp else 2.dp)', '.padding(top = if (isTv) 10.dp else 86.dp)')
replace(home,'''            Text(
                if (isTv) "ANDROID TV · 1.0.32"''','''            Text(
                expiry.label(menuLocale, now),
                modifier = Modifier.widthIn(max = if (isTv) 280.dp else if (compact) 164.dp else 180.dp).testTag("playlist-expiry"),
                color = if (expiry.untilMs?.let { it <= now } == true) Color(0xFFFFB2A8) else Color.White.copy(.9f),
                fontSize = if (isTv) 13.sp else if (compact) 9.sp else 10.sp,
                fontWeight = FontWeight.Medium, maxLines = 1, overflow = TextOverflow.Ellipsis
            )
            Text(
                if (isTv) "ANDROID TV · 1.0.32"''')
test=root/'app/src/test/java/de/epimediahub/app/ui/V131SkinCatalogueTest.kt'
replace(test,'                assertEquals(repo.officialMarkRes(base), repo.officialMarkRes(variant.id))',
    '''                val historical = app.resources.getIdentifier("historical_$base", "drawable", app.packageName)
                assertEquals(if (variant.id.endsWith("__legends") && historical != 0) historical else repo.officialMarkRes(base), repo.officialMarkRes(variant.id))''')
replace(root/'app/src/main/res/raw/keep.xml','@drawable/official_*','@drawable/official_*,@drawable/historical_*')
print('Installed Android 1.0.32: upper-body windows, historical marks and playlist expiry')
